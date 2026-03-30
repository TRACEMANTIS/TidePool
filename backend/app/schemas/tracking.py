"""Pydantic schemas for the real-time monitoring and tracking APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LiveCampaignStats(BaseModel):
    """Snapshot of real-time campaign metrics (sourced from Redis)."""

    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    submitted: int = 0
    reported: int = 0
    send_rate_per_minute: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None
    status: str = "unknown"


class EventFeedItem(BaseModel):
    """Single event in the real-time feed."""

    event_type: str
    recipient_token: str
    timestamp: str
    metadata: dict[str, Any] | None = None


class EventFeedResponse(BaseModel):
    """Paginated list of recent tracking events."""

    events: list[EventFeedItem]
    next_cursor: str | None = None
    has_more: bool = False


class SendRatePoint(BaseModel):
    """A single data point in a send-rate time series."""

    timestamp: str
    rate: float


class ActiveCampaignSummary(BaseModel):
    """Summary stats for a currently running campaign."""

    campaign_id: int
    name: str
    status: str
    progress_percent: float = 0.0
    send_rate: float = 0.0
    started_at: str | None = None
