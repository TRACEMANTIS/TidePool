"""Tests for campaign management endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus


class TestCampaignCRUD:
    """Tests for campaign create, read, update operations."""

    async def test_create_campaign(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_smtp_profile,
        sample_template,
        sample_addressbook,
    ):
        """POST /campaigns/campaigns creates a campaign in DRAFT status."""
        payload = {
            "name": "Q1 Phishing Test",
            "description": "Quarterly security assessment",
            "template_id": sample_template.id,
            "smtp_profile_id": sample_smtp_profile.id,
            "addressbook_id": sample_addressbook.id,
        }
        resp = await client.post(
            "/api/v1/campaigns/campaigns",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 201

        body = resp.json()
        assert body["name"] == "Q1 Phishing Test"
        assert body["description"] == "Quarterly security assessment"
        assert body["status"] in ("draft", "DRAFT")
        assert "id" in body

    async def test_list_campaigns(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """GET /campaigns/campaigns returns a paginated response."""
        resp = await client.get(
            "/api/v1/campaigns/campaigns",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "per_page" in body
        assert isinstance(body["items"], list)

    async def test_campaign_detail(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """GET /campaigns/campaigns/{id} returns the campaign detail."""
        resp = await client.get(
            "/api/v1/campaigns/campaigns/1",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["id"] == 1
        assert "name" in body
        assert "status" in body
        assert "created_at" in body


class TestCampaignStatusTransitions:
    """Tests for campaign lifecycle state transitions."""

    async def test_start_campaign(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """POST /campaigns/{id}/start returns a success message."""
        resp = await client.post(
            "/api/v1/campaigns/campaigns/1/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body

    async def test_pause_campaign(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """POST /campaigns/{id}/pause returns a success message."""
        resp = await client.post(
            "/api/v1/campaigns/campaigns/1/pause",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body

    async def test_complete_campaign(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """POST /campaigns/{id}/complete returns a success message."""
        resp = await client.post(
            "/api/v1/campaigns/campaigns/1/complete",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body


class TestCampaignScheduling:
    """Tests for campaign scheduling constraints."""

    async def test_schedule_campaign(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sample_smtp_profile,
        sample_template,
        sample_addressbook,
    ):
        """Creating a campaign with a future scheduled_at sets it correctly."""
        payload = {
            "name": "Scheduled Campaign",
            "template_id": sample_template.id,
            "smtp_profile_id": sample_smtp_profile.id,
            "addressbook_id": sample_addressbook.id,
            "scheduled_at": "2027-06-01T09:00:00Z",
        }
        resp = await client.post(
            "/api/v1/campaigns/campaigns",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["scheduled_at"] is not None

    async def test_campaign_requires_auth(
        self,
        client: AsyncClient,
    ):
        """Unauthenticated campaign requests return 401."""
        resp = await client.get("/api/v1/campaigns/campaigns")
        assert resp.status_code == 401
