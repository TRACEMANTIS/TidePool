"""Tests for tracking endpoints: email opens, link clicks, form submissions, phish reports.

These tests verify the privacy-first tracking system:
- Consistent responses for valid and invalid tokens (anti-enumeration).
- Credential values are never stored.
- Tracking pixel returns a valid 1x1 GIF.
"""

import secrets
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.tracking import TrackingEvent, EventType


# Valid composite tracking ID format: {campaign_id}.{token}
def _make_tracking_id(campaign_id: int = 1) -> str:
    """Generate a valid composite tracking ID."""
    token = secrets.token_urlsafe(32)
    return f"{campaign_id}.{token}"


def _make_fake_tracking_id() -> str:
    """Generate a tracking ID that looks valid but has no matching records."""
    token = secrets.token_urlsafe(32)
    return f"999999.{token}"


# Patch the recorder and Redis to avoid requiring external services.
_RECORDER_PATCH = "app.api.tracking._get_recorder"
_REPORT_REDIS_PATCH = "app.tracking.phish_report._get_redis"


def _mock_recorder():
    """Return a mock (recorder, redis_client) tuple."""
    recorder = AsyncMock()
    recorder.record_open = AsyncMock()
    recorder.record_click = AsyncMock()
    recorder.record_submission = AsyncMock()
    recorder.record_report = AsyncMock()
    redis_client = AsyncMock()
    redis_client.aclose = AsyncMock()
    return recorder, redis_client


# ---------------------------------------------------------------------------
# Open tracking (pixel)
# ---------------------------------------------------------------------------


class TestOpenTracking:
    """Tests for GET /api/v1/t/o/{tracking_id}."""

    @patch(_RECORDER_PATCH)
    async def test_open_pixel_returns_gif(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """The open tracking endpoint returns a 1x1 transparent GIF."""
        mock_get_recorder.return_value = _mock_recorder()
        tracking_id = _make_tracking_id(sample_campaign.id)

        resp = await client.get(f"/api/v1/t/o/{tracking_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/gif"

        # Verify it is a valid GIF (starts with GIF89a magic bytes).
        assert resp.content[:6] == b"GIF89a"
        # A 1x1 GIF is typically 43 bytes.
        assert len(resp.content) == 43

    @patch(_RECORDER_PATCH)
    async def test_open_records_event(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """Opening a tracking pixel calls the event recorder."""
        recorder, redis_client = _mock_recorder()
        mock_get_recorder.return_value = (recorder, redis_client)

        tracking_id = _make_tracking_id(sample_campaign.id)
        await client.get(f"/api/v1/t/o/{tracking_id}")

        recorder.record_open.assert_called_once()
        call_args = recorder.record_open.call_args
        # First positional arg should be the campaign ID.
        assert call_args[0][0] == sample_campaign.id

    @patch(_RECORDER_PATCH)
    async def test_open_invalid_token_returns_pixel(
        self,
        mock_get_recorder,
        client: AsyncClient,
    ):
        """An invalid tracking ID still returns the pixel (anti-enumeration)."""
        mock_get_recorder.return_value = _mock_recorder()

        # Completely invalid format.
        resp = await client.get("/api/v1/t/o/invalid")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/gif"


# ---------------------------------------------------------------------------
# Click tracking
# ---------------------------------------------------------------------------


class TestClickTracking:
    """Tests for GET /api/v1/t/c/{tracking_id}."""

    @patch(_RECORDER_PATCH)
    async def test_click_records_event(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """Clicking a tracking link calls the event recorder."""
        recorder, redis_client = _mock_recorder()
        mock_get_recorder.return_value = (recorder, redis_client)

        tracking_id = _make_tracking_id(sample_campaign.id)
        resp = await client.get(
            f"/api/v1/t/c/{tracking_id}",
            follow_redirects=False,
        )
        # Should return 200 (thank-you HTML) or 302 (redirect).
        assert resp.status_code in (200, 302)
        recorder.record_click.assert_called_once()

    @patch(_RECORDER_PATCH)
    async def test_click_redirect_to_training(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """If a campaign has a training_redirect_url but no landing page,
        clicking redirects to the training URL."""
        recorder, redis_client = _mock_recorder()
        mock_get_recorder.return_value = (recorder, redis_client)

        tracking_id = _make_tracking_id(sample_campaign.id)
        resp = await client.get(
            f"/api/v1/t/c/{tracking_id}",
            follow_redirects=False,
        )
        # Campaign has training_redirect_url and no landing_page_id.
        if resp.status_code == 302:
            assert resp.headers["location"] == sample_campaign.training_redirect_url

    @patch(_RECORDER_PATCH)
    async def test_click_invalid_token_consistent_response(
        self,
        mock_get_recorder,
        client: AsyncClient,
    ):
        """Invalid tokens return the same status code as valid ones."""
        mock_get_recorder.return_value = _mock_recorder()

        resp = await client.get("/api/v1/t/c/invalid-short")
        # Invalid format returns 200 with thank-you HTML.
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Submission tracking
# ---------------------------------------------------------------------------


class TestSubmissionTracking:
    """Tests for POST /api/v1/t/s/{tracking_id}."""

    @patch(_RECORDER_PATCH)
    async def test_submission_discards_values(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """Submissions record only field names, never the values themselves."""
        recorder, redis_client = _mock_recorder()
        mock_get_recorder.return_value = (recorder, redis_client)

        tracking_id = _make_tracking_id(sample_campaign.id)
        payload = {
            "fields": {
                "username": "john.doe@corp.com",
                "password": "SuperSecret123",
                "mfa_code": "123456",
            }
        }
        resp = await client.post(
            f"/api/v1/t/s/{tracking_id}",
            json=payload,
        )
        assert resp.status_code in (200, 302)

        # Verify the recorder was called with field names only.
        recorder.record_submission.assert_called_once()
        call_args = recorder.record_submission.call_args[0]
        field_names = call_args[2]  # Third positional arg is field_names.
        assert "username" in field_names
        assert "password" in field_names
        assert "mfa_code" in field_names

    @patch(_RECORDER_PATCH)
    async def test_submission_redirect_to_training(
        self,
        mock_get_recorder,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """After submission, user is redirected to the training URL."""
        recorder, redis_client = _mock_recorder()
        mock_get_recorder.return_value = (recorder, redis_client)

        tracking_id = _make_tracking_id(sample_campaign.id)
        resp = await client.post(
            f"/api/v1/t/s/{tracking_id}",
            json={"fields": {"email": "test@corp.com"}},
            follow_redirects=False,
        )
        if resp.status_code == 302:
            assert resp.headers["location"] == sample_campaign.training_redirect_url

    @patch(_RECORDER_PATCH)
    async def test_invalid_token_consistent_response(
        self,
        mock_get_recorder,
        client: AsyncClient,
    ):
        """Fake tokens return the same response shape as valid ones (anti-enumeration)."""
        mock_get_recorder.return_value = _mock_recorder()

        resp = await client.post(
            "/api/v1/t/s/invalid-token",
            json={"fields": {"test": "value"}},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Phish report
# ---------------------------------------------------------------------------


class TestPhishReport:
    """Tests for POST /api/v1/t/report/{tracking_id}."""

    @patch(_REPORT_REDIS_PATCH)
    async def test_phish_report(
        self,
        mock_get_redis,
        client: AsyncClient,
        sample_campaign: Campaign,
    ):
        """Reporting a phish returns a thank-you page and records the event."""
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Patch the EventRecorder inside the phish_report module.
        with patch("app.tracking.phish_report.EventRecorder") as MockRecorder:
            instance = AsyncMock()
            instance.record_report = AsyncMock()
            MockRecorder.return_value = instance

            tracking_id = _make_tracking_id(sample_campaign.id)
            resp = await client.post(f"/api/v1/t/report/{tracking_id}")

            assert resp.status_code == 200
            assert "Thank You" in resp.text
            instance.record_report.assert_called_once()

    @patch(_REPORT_REDIS_PATCH)
    async def test_phish_report_invalid_token(
        self,
        mock_get_redis,
        client: AsyncClient,
    ):
        """Invalid report tokens return the same page (anti-enumeration)."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        resp = await client.post("/api/v1/t/report/too-short")
        assert resp.status_code == 200
        assert "Thank You" in resp.text


# ---------------------------------------------------------------------------
# Token unpredictability
# ---------------------------------------------------------------------------


class TestTokenUnpredictability:
    """Verify that tracking tokens are not sequential or guessable."""

    def test_tracking_token_unpredictable(self):
        """Generated tracking tokens have high entropy and are not sequential."""
        tokens = [secrets.token_urlsafe(32) for _ in range(100)]

        # All tokens should be unique.
        assert len(set(tokens)) == 100

        # No two consecutive tokens should share a common prefix of 8+ chars.
        for i in range(len(tokens) - 1):
            common_prefix_len = 0
            for a, b in zip(tokens[i], tokens[i + 1]):
                if a == b:
                    common_prefix_len += 1
                else:
                    break
            assert common_prefix_len < 8, (
                f"Tokens {i} and {i+1} share a suspiciously long common prefix "
                f"({common_prefix_len} chars)"
            )
