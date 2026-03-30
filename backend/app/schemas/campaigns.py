"""Campaign Pydantic schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class CampaignStatus(str, Enum):
    """Possible states of a phishing campaign."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class _TrainingRedirectMixin(BaseModel):
    """Shared validation for training redirect fields."""

    @field_validator("training_redirect_url")
    @classmethod
    def _validate_training_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("training_redirect_url must start with http:// or https://")
        return v


class CampaignCreate(_TrainingRedirectMixin):
    """Payload for creating a new campaign."""

    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    template_id: int
    smtp_profile_id: int
    addressbook_id: int
    landing_page_id: int | None = None
    scheduled_at: datetime | None = None
    training_redirect_url: str | None = None
    training_redirect_delay_seconds: int = 0


class CampaignUpdate(_TrainingRedirectMixin):
    """Payload for updating an existing campaign."""

    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    template_id: int | None = None
    smtp_profile_id: int | None = None
    addressbook_id: int | None = None
    landing_page_id: int | None = None
    scheduled_at: datetime | None = None
    training_redirect_url: str | None = None
    training_redirect_delay_seconds: int = 0


class CampaignResponse(BaseModel):
    """Campaign data returned by the API."""

    id: int
    name: str
    description: str | None = None
    status: CampaignStatus
    template_id: int
    smtp_profile_id: int
    addressbook_id: int
    landing_page_id: int | None = None
    training_redirect_url: str | None = None
    training_redirect_delay_seconds: int = 0
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduleRequest(BaseModel):
    """Payload for scheduling a campaign."""

    send_window_start: datetime = Field(
        ..., description="When to begin sending emails (must be in the future).",
    )
    send_window_end: datetime = Field(
        ..., description="When to stop sending emails (must be after send_window_start).",
    )

    @field_validator("send_window_start")
    @classmethod
    def _start_must_be_future(cls, v: datetime) -> datetime:
        from datetime import timezone as _tz

        # Ensure timezone-aware for comparison.
        now = datetime.now(_tz.utc)
        compare = v if v.tzinfo else v.replace(tzinfo=_tz.utc)
        if compare <= now:
            raise ValueError("send_window_start must be in the future")
        return v

    @field_validator("send_window_end")
    @classmethod
    def _end_must_be_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("send_window_start")
        if start is not None and v <= start:
            raise ValueError("send_window_end must be after send_window_start")
        return v


class ScheduleResponse(BaseModel):
    """Response after scheduling a campaign."""

    campaign_id: int
    status: CampaignStatus
    send_window_start: datetime
    send_window_end: datetime
    estimated_completion: datetime | None = None
    total_recipients: int = 0

    model_config = {"from_attributes": True}
