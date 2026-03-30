"""Pydantic schemas for the campaign automation API."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class LureCategory(str, Enum):
    """Lure template categories matching EmailTemplate.TemplateCategory."""

    IT = "IT"
    HR = "HR"
    FINANCE = "FINANCE"
    EXECUTIVE = "EXECUTIVE"
    VENDOR = "VENDOR"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class QuickLaunchRequest(BaseModel):
    """Non-file fields accepted by the quick-launch endpoint.

    These are submitted alongside the uploaded file as multipart form data,
    so they are not used as a JSON body -- they serve as a validation layer
    inside the route handler.
    """

    @field_validator("training_redirect_url")
    @classmethod
    def _validate_training_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("training_redirect_url must start with http:// or https://")
        return v

    email_column: str = Field(..., min_length=1, max_length=128)
    first_name_column: str | None = Field(None, max_length=128)
    last_name_column: str | None = Field(None, max_length=128)
    department_column: str | None = Field(None, max_length=128)
    lure_category: LureCategory
    lure_subject: str = Field(..., min_length=1, max_length=998)
    lure_body: str = Field(..., min_length=1)
    from_name: str = Field(..., min_length=1, max_length=256)
    from_address: str = Field(..., min_length=3, max_length=320)
    smtp_profile_id: int
    landing_page_id: int | None = None
    training_module_id: int | None = None
    training_redirect_url: str | None = None
    training_redirect_delay_seconds: int = Field(default=0, ge=0)
    send_window_hours: int = Field(default=24, ge=1, le=720)
    campaign_name: str | None = Field(None, max_length=256)
    start_immediately: bool = False


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class QuickLaunchResponse(BaseModel):
    """Response returned after a successful quick-launch."""

    campaign_id: int
    name: str
    total_recipients: int
    status: str
    estimated_completion: datetime | None = None

    model_config = {"from_attributes": True}


class CampaignStatusResponse(BaseModel):
    """Detailed status breakdown for a running or completed campaign."""

    campaign_id: int
    name: str
    status: str
    sent: int = 0
    pending: int = 0
    failed: int = 0
    total: int = 0
    rate_per_minute: float = 0.0
    eta: datetime | None = None

    model_config = {"from_attributes": True}


class EmailPreview(BaseModel):
    """A single rendered email preview."""

    to: str
    subject: str
    body_preview: str


class PreviewResponse(BaseModel):
    """Preview of what a quick-launch would produce."""

    emails: list[EmailPreview]
    total_recipients: int
    estimated_duration_hours: float


class ColumnSuggestion(BaseModel):
    """Detected column with sample values and a suggested mapping."""

    name: str
    sample_values: list[str]
    suggested_mapping: str | None = None


class ColumnDetectionResponse(BaseModel):
    """Auto-detected columns from an uploaded file."""

    columns: list[ColumnSuggestion]
