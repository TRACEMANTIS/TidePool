"""Pydantic schemas for training redirect tracking."""

from datetime import datetime

from pydantic import BaseModel


class TrainingRedirectResponse(BaseModel):
    """Response schema for a single training redirect record."""

    id: int
    campaign_id: int
    recipient_token: str
    redirected_at: datetime

    model_config = {"from_attributes": True}


class TrainingRedirectListResponse(BaseModel):
    """Paginated list of training redirect records."""

    items: list[TrainingRedirectResponse]
    total: int
