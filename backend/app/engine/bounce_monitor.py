"""Bounce rate monitoring for campaign email delivery.

Tracks bounce rates per campaign and auto-pauses campaigns that exceed
the configurable bounce rate threshold to protect sender reputation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus
from app.models.tracking import CampaignRecipient, RecipientStatus, TrackingEvent, EventType

logger = logging.getLogger(__name__)

# Bounce rate threshold (percentage).  Campaigns exceeding this are paused.
BOUNCE_RATE_THRESHOLD = 5.0

# Minimum emails sent before bounce rate monitoring takes effect.
# Prevents false positives on small batches.
MIN_SENT_FOR_MONITORING = 100


@dataclass
class BounceRateStatus:
    """Current bounce rate metrics for a campaign."""

    campaign_id: int
    total_sent: int = 0
    total_bounced: int = 0
    bounce_rate: float = 0.0
    hard_bounces: int = 0
    soft_bounces: int = 0
    complaints: int = 0


class BounceMonitor:
    """Monitor bounce rates and auto-pause campaigns when thresholds are exceeded."""

    async def check_bounce_rate(
        self,
        campaign_id: int,
        db: AsyncSession,
        redis=None,
    ) -> BounceRateStatus:
        """Calculate current bounce rate metrics for a campaign.

        Parameters
        ----------
        campaign_id:
            The campaign to check.
        db:
            Async database session.
        redis:
            Optional Redis client for counter-based fast path.

        Returns
        -------
        BounceRateStatus
            Current bounce metrics.
        """
        status = BounceRateStatus(campaign_id=campaign_id)

        # Try Redis counters first for speed.
        if redis is not None:
            try:
                redis_status = await self._check_from_redis(campaign_id, redis)
                if redis_status is not None:
                    return redis_status
            except Exception:
                logger.debug("Redis bounce check failed, falling back to DB")

        # Fall back to database queries.
        sent_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status.in_([
                    RecipientStatus.SENT,
                    RecipientStatus.DELIVERED,
                    RecipientStatus.BOUNCED,
                ]),
            )
        )
        status.total_sent = (await db.execute(sent_stmt)).scalar() or 0

        bounced_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status == RecipientStatus.BOUNCED,
            )
        )
        status.total_bounced = (await db.execute(bounced_stmt)).scalar() or 0

        # Break down by bounce type from tracking events.
        bounce_events_stmt = (
            select(TrackingEvent.metadata_)
            .where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.metadata_["is_bounce"].as_boolean() == True,  # noqa: E712
            )
        )
        bounce_events = (await db.execute(bounce_events_stmt)).scalars().all()

        for meta in bounce_events:
            if not meta:
                continue
            bt = meta.get("bounce_type", "")
            if bt == "HARD":
                status.hard_bounces += 1
            elif bt == "SOFT":
                status.soft_bounces += 1
            elif bt == "COMPLAINT":
                status.complaints += 1

        if status.total_sent > 0:
            status.bounce_rate = round(
                (status.total_bounced / status.total_sent) * 100, 2,
            )

        return status

    async def _check_from_redis(
        self,
        campaign_id: int,
        redis,
    ) -> BounceRateStatus | None:
        """Attempt to build bounce status from Redis counters."""
        key = f"tidepool:campaign_counters:{campaign_id}"
        data = await redis.hgetall(key)
        if not data:
            return None

        def _int(k: str) -> int:
            val = data.get(k.encode() if isinstance(next(iter(data.keys()), b""), bytes) else k, 0)
            return int(val)

        total_sent = _int("sent")
        if total_sent == 0:
            return None

        bounce_key = f"tidepool:bounce_counters:{campaign_id}"
        bounce_data = await redis.hgetall(bounce_key)

        hard = int(bounce_data.get(b"hard", bounce_data.get("hard", 0)))
        soft = int(bounce_data.get(b"soft", bounce_data.get("soft", 0)))
        complaints = int(bounce_data.get(b"complaint", bounce_data.get("complaint", 0)))
        total_bounced = hard + soft + complaints

        return BounceRateStatus(
            campaign_id=campaign_id,
            total_sent=total_sent,
            total_bounced=total_bounced,
            bounce_rate=round((total_bounced / total_sent) * 100, 2) if total_sent else 0.0,
            hard_bounces=hard,
            soft_bounces=soft,
            complaints=complaints,
        )

    async def should_pause(
        self,
        campaign_id: int,
        db: AsyncSession,
        redis=None,
    ) -> bool:
        """Determine whether a campaign should be auto-paused.

        Returns True if the bounce rate exceeds the threshold AND at least
        ``MIN_SENT_FOR_MONITORING`` emails have been sent.
        """
        status = await self.check_bounce_rate(campaign_id, db, redis)

        if status.total_sent < MIN_SENT_FOR_MONITORING:
            return False

        return status.bounce_rate > BOUNCE_RATE_THRESHOLD

    async def auto_pause_if_needed(
        self,
        campaign_id: int,
        db: AsyncSession,
        redis=None,
    ) -> bool:
        """Check bounce rate and pause the campaign if the threshold is exceeded.

        Creates an audit log entry explaining the auto-pause.

        Returns
        -------
        bool
            True if the campaign was paused.
        """
        if not await self.should_pause(campaign_id, db, redis):
            return False

        # Load the campaign and verify it is still running.
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        result = await db.execute(stmt)
        campaign = result.scalar_one_or_none()

        if campaign is None:
            return False

        if campaign.status != CampaignStatus.RUNNING:
            return False

        # Pause the campaign.
        campaign.status = CampaignStatus.PAUSED
        await db.flush()

        # Get current bounce stats for the audit entry.
        status = await self.check_bounce_rate(campaign_id, db, redis)

        # Record audit log entry.
        audit_event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token="SYSTEM",
            event_type=EventType.DELIVERED,  # Closest type; metadata distinguishes.
            timestamp=datetime.now(timezone.utc),
            metadata_={
                "auto_pause": True,
                "reason": "bounce_rate_exceeded",
                "bounce_rate": status.bounce_rate,
                "total_sent": status.total_sent,
                "total_bounced": status.total_bounced,
                "hard_bounces": status.hard_bounces,
                "soft_bounces": status.soft_bounces,
                "complaints": status.complaints,
                "threshold": BOUNCE_RATE_THRESHOLD,
            },
        )
        db.add(audit_event)
        await db.flush()

        logger.warning(
            "AUTO-PAUSE: Campaign %d paused due to bounce rate %.1f%% "
            "(%d bounces / %d sent, threshold %.1f%%)",
            campaign_id,
            status.bounce_rate,
            status.total_bounced,
            status.total_sent,
            BOUNCE_RATE_THRESHOLD,
        )

        return True
