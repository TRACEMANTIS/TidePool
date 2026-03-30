"""Pydantic schemas for reports and audit endpoints."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Campaign metrics
# ---------------------------------------------------------------------------

class CampaignMetricsResponse(BaseModel):
    """Aggregate metrics for a single campaign."""

    campaign_id: int
    total_recipients: int = 0
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    submitted: int = 0
    reported: int = 0

    open_rate: float = 0.0
    click_rate: float = 0.0
    submit_rate: float = 0.0
    report_rate: float = 0.0

    time_to_first_click_median_seconds: float | None = None
    time_to_first_click_p90_seconds: float | None = None

    sends_by_hour: dict[int, int] = Field(default_factory=dict)
    events_timeline: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Department metrics
# ---------------------------------------------------------------------------

class DepartmentMetricsResponse(BaseModel):
    """Per-department breakdown for a campaign."""

    name: str
    headcount: int = 0
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    submitted: int = 0
    reported: int = 0
    risk_score: float = 0.0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

class CampaignTrendPoint(BaseModel):
    """Single data point in a trend series."""

    campaign_id: int
    name: str
    date: datetime | None = None
    open_rate: float = 0.0
    click_rate: float = 0.0
    submit_rate: float = 0.0


class TrendResponse(BaseModel):
    """Trend analysis across multiple campaigns."""

    campaigns: list[CampaignTrendPoint] = Field(default_factory=list)
    trend_direction: str = "stable"  # improving / declining / stable

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Org risk score
# ---------------------------------------------------------------------------

class DepartmentRanking(BaseModel):
    """Department entry in org risk ranking."""

    name: str
    risk_score: float
    headcount: int


class OrgRiskResponse(BaseModel):
    """Organisation-wide risk assessment."""

    org_risk_score: float = 0.0
    risk_level: str = "Low"
    department_rankings: list[DepartmentRanking] = Field(default_factory=list)
    improvement_delta: float | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class AuditLogFilter(BaseModel):
    """Query filters for audit log listing."""

    actor: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=50, ge=1, le=200)


class AuditLogEntry(BaseModel):
    """Single audit log record."""

    id: int
    actor: str
    action: str
    resource_type: str
    resource_id: str
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    ip_address: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogEntry] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 50
    pages: int = 0

    model_config = {"from_attributes": True}
