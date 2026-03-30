"""Campaign management router."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus as ModelStatus
from app.models.tracking import CampaignRecipient
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignResponse,
    CampaignStatus,
    CampaignUpdate,
    ScheduleRequest,
    ScheduleResponse,
)
from app.schemas.common import PaginatedResponse, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns")

# ---------------------------------------------------------------------------
# Status transition rules
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[ModelStatus, set[ModelStatus]] = {
    ModelStatus.DRAFT: {ModelStatus.SCHEDULED, ModelStatus.RUNNING, ModelStatus.CANCELLED},
    ModelStatus.SCHEDULED: {ModelStatus.RUNNING, ModelStatus.DRAFT, ModelStatus.CANCELLED},
    ModelStatus.RUNNING: {ModelStatus.PAUSED, ModelStatus.COMPLETED, ModelStatus.CANCELLED},
    ModelStatus.PAUSED: {ModelStatus.RUNNING, ModelStatus.COMPLETED, ModelStatus.CANCELLED},
    ModelStatus.COMPLETED: {ModelStatus.CANCELLED},
    ModelStatus.CANCELLED: set(),
}


def _validate_transition(current: ModelStatus, target: ModelStatus) -> None:
    """Raise 409 Conflict if the status transition is not allowed."""
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition from {current.value} to {target.value}. "
                f"Allowed transitions: {', '.join(s.value for s in allowed) or 'none'}."
            ),
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/campaigns", response_model=PaginatedResponse[CampaignResponse])
async def list_campaigns(
    page: int = 1,
    per_page: int = 25,
    status: CampaignStatus | None = None,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a paginated list of campaigns, optionally filtered by status."""
    stmt = select(Campaign)
    count_stmt = select(func.count()).select_from(Campaign)

    if status is not None:
        model_status = ModelStatus(status.value.upper())
        stmt = stmt.where(Campaign.status == model_status)
        count_stmt = count_stmt.where(Campaign.status == model_status)

    total = (await db.execute(count_stmt)).scalar() or 0
    pages = max(1, -(-total // per_page))
    offset = (page - 1) * per_page

    stmt = stmt.offset(offset).limit(per_page).order_by(Campaign.id.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post(
    "/campaigns",
    response_model=CampaignResponse,
    status_code=201,
)
async def create_campaign(
    payload: CampaignCreate,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    """Create a new phishing campaign."""
    campaign = Campaign(
        name=payload.name,
        description=payload.description,
        status=ModelStatus.DRAFT,
        email_template_id=payload.template_id,
        smtp_profile_id=payload.smtp_profile_id,
        landing_page_id=payload.landing_page_id,
        training_redirect_url=payload.training_redirect_url,
        training_redirect_delay_seconds=payload.training_redirect_delay_seconds,
        created_by=_user.get("id", 1),
    )
    if payload.scheduled_at:
        campaign.send_window_start = payload.scheduled_at

    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    """Return details for a single campaign."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    return campaign


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdate,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    """Update an existing campaign (draft or paused only)."""
    campaign = await _get_campaign_or_404(campaign_id, db)

    if campaign.status not in (ModelStatus.DRAFT, ModelStatus.PAUSED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot update campaign in {campaign.status.value} status.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        if field_name == "template_id":
            setattr(campaign, "email_template_id", value)
        elif hasattr(campaign, field_name):
            setattr(campaign, field_name, value)

    await db.flush()
    await db.refresh(campaign)
    return campaign


# ---------------------------------------------------------------------------
# Campaign lifecycle actions
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/start", response_model=SuccessResponse)
async def start_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Begin sending emails for the specified campaign."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.RUNNING)

    campaign.status = ModelStatus.RUNNING
    await db.flush()

    # Dispatch via Celery.
    from app.engine.dispatcher import dispatch_campaign
    dispatch_campaign.apply_async(args=[campaign_id])

    return {"message": f"Campaign {campaign_id} started."}


@router.post("/campaigns/{campaign_id}/pause", response_model=SuccessResponse)
async def pause_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pause an active campaign."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.PAUSED)

    campaign.status = ModelStatus.PAUSED
    await db.flush()

    return {"message": f"Campaign {campaign_id} paused."}


@router.post("/campaigns/{campaign_id}/resume", response_model=SuccessResponse)
async def resume_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resume a paused campaign."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.RUNNING)

    campaign.status = ModelStatus.RUNNING
    await db.flush()

    from app.engine.dispatcher import dispatch_campaign
    dispatch_campaign.apply_async(args=[campaign_id])

    return {"message": f"Campaign {campaign_id} resumed."}


@router.post("/campaigns/{campaign_id}/complete", response_model=SuccessResponse)
async def complete_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a campaign as completed."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.COMPLETED)

    campaign.status = ModelStatus.COMPLETED
    await db.flush()

    return {"message": f"Campaign {campaign_id} marked complete."}


@router.post("/campaigns/{campaign_id}/cancel", response_model=SuccessResponse)
async def cancel_campaign(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a campaign (allowed from any non-cancelled state)."""
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.CANCELLED)

    campaign.status = ModelStatus.CANCELLED
    await db.flush()

    return {"message": f"Campaign {campaign_id} cancelled."}


# ---------------------------------------------------------------------------
# Schedule endpoints
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/schedule", response_model=ScheduleResponse)
async def schedule_campaign(
    campaign_id: int,
    payload: ScheduleRequest,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Schedule a campaign for future launch.

    Validates that the campaign has an SMTP profile, email template, and
    recipients configured.  Tests SMTP connectivity before confirming.
    """
    campaign = await _get_campaign_or_404(campaign_id, db)
    _validate_transition(campaign.status, ModelStatus.SCHEDULED)

    # -- Prerequisite checks --------------------------------------------------

    if not campaign.smtp_profile_id:
        raise HTTPException(status_code=400, detail="Campaign has no SMTP profile configured.")

    if not campaign.email_template_id:
        raise HTTPException(status_code=400, detail="Campaign has no email template configured.")

    # Check recipients exist.
    recip_count_stmt = (
        select(func.count())
        .select_from(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
    )
    recipient_count = (await db.execute(recip_count_stmt)).scalar() or 0
    if recipient_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Campaign has no recipients. Add contacts before scheduling.",
        )

    # Test SMTP connectivity.
    try:
        smtp_profile = campaign.smtp_profile
        if smtp_profile is not None:
            from app.engine.smtp_backends import get_backend
            backend = get_backend(smtp_profile)
            connected = await backend.test_connection()
            if not connected:
                raise HTTPException(
                    status_code=400,
                    detail="SMTP profile connectivity test failed. Check SMTP settings.",
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("SMTP connectivity test raised: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"SMTP connectivity test error: {exc}",
        )

    # -- Apply schedule -------------------------------------------------------
    campaign.send_window_start = payload.send_window_start
    campaign.send_window_end = payload.send_window_end
    campaign.status = ModelStatus.SCHEDULED
    await db.flush()

    # Estimate completion based on send window and throttle rate.
    estimated = payload.send_window_end

    return {
        "campaign_id": campaign.id,
        "status": CampaignStatus.SCHEDULED,
        "send_window_start": payload.send_window_start,
        "send_window_end": payload.send_window_end,
        "estimated_completion": estimated,
        "total_recipients": recipient_count,
    }


@router.get("/campaigns/{campaign_id}/schedule", response_model=ScheduleResponse)
async def get_schedule(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the schedule details for a campaign."""
    campaign = await _get_campaign_or_404(campaign_id, db)

    if campaign.status not in (ModelStatus.SCHEDULED, ModelStatus.RUNNING):
        raise HTTPException(
            status_code=404,
            detail="Campaign is not scheduled.",
        )

    recip_count_stmt = (
        select(func.count())
        .select_from(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
    )
    recipient_count = (await db.execute(recip_count_stmt)).scalar() or 0

    return {
        "campaign_id": campaign.id,
        "status": CampaignStatus(campaign.status.value.lower()),
        "send_window_start": campaign.send_window_start,
        "send_window_end": campaign.send_window_end,
        "estimated_completion": campaign.send_window_end,
        "total_recipients": recipient_count,
    }


@router.delete("/campaigns/{campaign_id}/schedule", response_model=SuccessResponse)
async def cancel_schedule(
    campaign_id: int,
    _user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a campaign's schedule, reverting it to DRAFT."""
    campaign = await _get_campaign_or_404(campaign_id, db)

    if campaign.status != ModelStatus.SCHEDULED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel schedule for campaign in {campaign.status.value} status.",
        )

    _validate_transition(campaign.status, ModelStatus.DRAFT)

    campaign.status = ModelStatus.DRAFT
    campaign.send_window_start = None
    campaign.send_window_end = None
    await db.flush()

    return {"message": f"Campaign {campaign_id} schedule cancelled. Reverted to DRAFT."}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_campaign_or_404(campaign_id: int, db: AsyncSession) -> Campaign:
    """Load a campaign by ID or raise 404."""
    stmt = select(Campaign).where(Campaign.id == campaign_id)
    result = await db.execute(stmt)
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign
