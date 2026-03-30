"""Tests for campaign automation endpoints: quick-launch, preview, abort."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.helpers import create_test_csv, create_test_xlsx


# Patch targets for orchestrator and rate limiter.
_ORCHESTRATOR_PATCH = "app.api.automation.CampaignOrchestrator"
_SAVE_UPLOAD_PATCH = "app.api.automation._save_upload"


# ---------------------------------------------------------------------------
# Quick launch
# ---------------------------------------------------------------------------


class TestQuickLaunch:
    """Tests for POST /api/v1/automation/quick-launch."""

    @patch(_SAVE_UPLOAD_PATCH)
    @patch(_ORCHESTRATOR_PATCH)
    async def test_quick_launch_with_csv(
        self,
        MockOrchestrator,
        mock_save_upload,
        client: AsyncClient,
        auth_headers: dict,
        sample_smtp_profile,
    ):
        """Uploading a CSV creates a campaign with the correct recipient count."""
        mock_save_upload.return_value = "/tmp/test_upload.csv"

        # Set up orchestrator mock.
        mock_orch = AsyncMock()
        mock_book = MagicMock()
        mock_book.id = 1
        mock_orch.ingest_file.return_value = (mock_book, 50, 2)
        mock_template = MagicMock()
        mock_template.id = 1
        mock_orch.create_template.return_value = mock_template
        mock_campaign = MagicMock()
        mock_campaign.id = 42
        mock_orch.create_campaign.return_value = mock_campaign
        MockOrchestrator.return_value = mock_orch

        csv_bytes = create_test_csv(50)

        resp = await client.post(
            "/api/v1/automation/quick-launch",
            files={"file": ("contacts.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={
                "email_column": "email",
                "first_name_column": "first_name",
                "last_name_column": "last_name",
                "department_column": "department",
                "lure_category": "IT",
                "lure_subject": "Password Reset Required",
                "lure_body": "Hello {{first_name}}, reset your password.",
                "from_name": "IT Support",
                "from_address": "it@company.test",
                "smtp_profile_id": str(sample_smtp_profile.id),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["campaign_id"] == 42
        assert body["total_recipients"] == 50
        assert body["status"] == "DRAFT"

    @patch(_SAVE_UPLOAD_PATCH)
    @patch(_ORCHESTRATOR_PATCH)
    async def test_quick_launch_with_xlsx(
        self,
        MockOrchestrator,
        mock_save_upload,
        client: AsyncClient,
        auth_headers: dict,
        sample_smtp_profile,
    ):
        """Uploading an XLSX file creates a campaign successfully."""
        mock_save_upload.return_value = "/tmp/test_upload.xlsx"

        mock_orch = AsyncMock()
        mock_book = MagicMock()
        mock_book.id = 1
        mock_orch.ingest_file.return_value = (mock_book, 25, 0)
        mock_template = MagicMock()
        mock_template.id = 1
        mock_orch.create_template.return_value = mock_template
        mock_campaign = MagicMock()
        mock_campaign.id = 43
        mock_orch.create_campaign.return_value = mock_campaign
        MockOrchestrator.return_value = mock_orch

        xlsx_bytes = create_test_xlsx(25)

        resp = await client.post(
            "/api/v1/automation/quick-launch",
            files={"file": ("contacts.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={
                "email_column": "email",
                "lure_category": "HR",
                "lure_subject": "Benefits Update",
                "lure_body": "Dear {{first_name}}, review your benefits.",
                "from_name": "HR Department",
                "from_address": "hr@company.test",
                "smtp_profile_id": str(sample_smtp_profile.id),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["campaign_id"] == 43
        assert body["total_recipients"] == 25

    async def test_quick_launch_invalid_file_type(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_smtp_profile,
    ):
        """Uploading a .txt file returns 400."""
        resp = await client.post(
            "/api/v1/automation/quick-launch",
            files={"file": ("contacts.txt", io.BytesIO(b"plain text data"), "text/plain")},
            data={
                "email_column": "email",
                "lure_category": "IT",
                "lure_subject": "Test",
                "lure_body": "Test body",
                "from_name": "Test",
                "from_address": "test@test.com",
                "smtp_profile_id": str(sample_smtp_profile.id),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "unsupported" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestPreview:
    """Tests for POST /api/v1/automation/preview."""

    @patch(_SAVE_UPLOAD_PATCH)
    @patch(_ORCHESTRATOR_PATCH)
    async def test_preview_renders_emails(
        self,
        MockOrchestrator,
        mock_save_upload,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Preview returns rendered email samples without creating DB records."""
        mock_save_upload.return_value = "/tmp/test_preview.csv"

        # Mock the orchestrator's preview method.
        mock_orch = MagicMock()
        mock_orch.preview.return_value = (
            [
                {"to": "user1@test.com", "subject": "Reset", "body_preview": "Hello First1"},
                {"to": "user2@test.com", "subject": "Reset", "body_preview": "Hello First2"},
            ],
            50,
        )
        MockOrchestrator.__new__ = MagicMock(return_value=mock_orch)

        csv_bytes = create_test_csv(50)

        resp = await client.post(
            "/api/v1/automation/preview",
            files={"file": ("contacts.csv", io.BytesIO(csv_bytes), "text/csv")},
            data={
                "email_column": "email",
                "lure_category": "IT",
                "lure_subject": "Password Reset",
                "lure_body": "Hello {{first_name}}",
                "from_name": "IT",
                "from_address": "it@test.com",
                "smtp_profile_id": "1",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "emails" in body
        assert "total_recipients" in body
        assert len(body["emails"]) > 0
        assert "to" in body["emails"][0]
        assert "subject" in body["emails"][0]
        assert "body_preview" in body["emails"][0]


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------


class TestColumnDetection:
    """Tests for POST /api/v1/automation/detect-columns."""

    @patch(_SAVE_UPLOAD_PATCH)
    @patch("app.api.automation.detect_columns")
    async def test_detect_columns(
        self,
        mock_detect,
        mock_save_upload,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Upload a file and verify column auto-detection."""
        mock_save_upload.return_value = "/tmp/test_detect.csv"
        mock_detect.return_value = [
            {"name": "email", "sample_values": ["a@b.com"], "suggested_mapping": "email"},
            {"name": "First Name", "sample_values": ["John"], "suggested_mapping": "first_name"},
        ]

        csv_bytes = create_test_csv(5)
        resp = await client.post(
            "/api/v1/automation/detect-columns",
            files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "columns" in body
        assert len(body["columns"]) == 2
        assert body["columns"][0]["name"] == "email"
        assert body["columns"][0]["suggested_mapping"] == "email"


# ---------------------------------------------------------------------------
# Campaign abort
# ---------------------------------------------------------------------------


class TestCampaignAbort:
    """Tests for POST /api/v1/automation/campaigns/{id}/abort."""

    @patch(_ORCHESTRATOR_PATCH)
    async def test_campaign_abort(
        self,
        MockOrchestrator,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Aborting a running campaign returns the final status."""
        mock_orch = AsyncMock()
        mock_orch.get_status.return_value = {
            "campaign_id": 1,
            "name": "Test Campaign",
            "status": "CANCELLED",
            "sent": 10,
            "pending": 0,
            "failed": 0,
            "total": 50,
            "rate_per_minute": 0.0,
            "eta": None,
            "created_by": None,
        }
        mock_orch.abort = AsyncMock()
        MockOrchestrator.return_value = mock_orch

        resp = await client.post(
            "/api/v1/automation/campaigns/1/abort",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["campaign_id"] == 1
        assert body["status"] == "CANCELLED"
        mock_orch.abort.assert_called_once_with(1)
