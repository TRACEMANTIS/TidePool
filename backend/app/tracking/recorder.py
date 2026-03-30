"""Event recording service -- persists tracking events to the database and
updates Redis real-time counters.

All public methods follow the same pattern:
1. Create/update a ``TrackingEvent`` row in PostgreSQL.
2. Increment the Redis counter via ``RealtimeTracker``.
3. Return the persisted event.

If the Redis update fails the database write still succeeds (graceful degradation).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracking import EventType, TrackingEvent
from app.tracking.realtime import RealtimeTracker

logger = logging.getLogger(__name__)


class EventRecorder:
    """High-level service that writes tracking events to the DB and Redis."""

    def __init__(self, realtime: RealtimeTracker) -> None:
        self._rt = realtime

    # -- Internal helpers ---------------------------------------------------

    async def _push_redis(
        self, campaign_id: int, event_type: str, recipient_token: str,
        metadata: dict | None = None,
    ) -> None:
        """Best-effort update of Redis counters and event feed."""
        try:
            await self._rt.increment(campaign_id, event_type)
            event_data = {
                "event_type": event_type,
                "recipient_token": recipient_token,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if metadata:
                event_data["metadata"] = metadata
            await self._rt.push_event(campaign_id, event_data)
        except Exception:
            logger.warning(
                "Redis update failed for campaign %s event %s (non-fatal)",
                campaign_id, event_type, exc_info=True,
            )

    # -- Public recording methods -------------------------------------------

    async def record_sent(
        self,
        campaign_id: int,
        recipient_token: str,
        db: AsyncSession,
    ) -> TrackingEvent:
        """Record that an email was sent to a recipient."""
        now = datetime.now(timezone.utc)
        event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token=recipient_token,
            event_type=EventType.SENT,
            timestamp=now,
            metadata_={"recorded_at": now.isoformat()},
        )
        db.add(event)
        await db.flush()

        await self._push_redis(campaign_id, EventType.SENT.value, recipient_token)
        # Also record the send timestamp for rate calculation.
        try:
            await self._rt.record_send_time(campaign_id)
        except Exception:
            logger.warning("Failed to record send time in Redis (non-fatal)", exc_info=True)

        return event

    async def record_open(
        self,
        campaign_id: int,
        recipient_token: str,
        metadata: dict,
        db: AsyncSession,
    ) -> TrackingEvent:
        """Record an email-open event.

        Deduplication: only the first open per recipient creates a new event
        row. Subsequent opens increment an ``open_count`` field in the
        existing event's metadata.
        """
        now = datetime.now(timezone.utc)
        metadata = dict(metadata)
        metadata["timestamp"] = now.isoformat()

        # Check for existing open event for this recipient in this campaign.
        result = await db.execute(
            select(TrackingEvent).where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.recipient_token == recipient_token,
                TrackingEvent.event_type == EventType.OPENED,
            ).limit(1)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            # Subsequent open -- increment counter, do not create new row.
            existing_meta = dict(existing.metadata_ or {})
            existing_meta["open_count"] = existing_meta.get("open_count", 1) + 1
            existing_meta["last_opened_at"] = now.isoformat()
            existing.metadata_ = existing_meta
            await db.flush()
            return existing

        # First open -- create new event row.
        metadata["open_count"] = 1
        event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token=recipient_token,
            event_type=EventType.OPENED,
            timestamp=now,
            metadata_=metadata,
        )
        db.add(event)
        await db.flush()

        await self._push_redis(
            campaign_id, EventType.OPENED.value, recipient_token, metadata,
        )
        return event

    async def record_click(
        self,
        campaign_id: int,
        recipient_token: str,
        url: str,
        metadata: dict,
        db: AsyncSession,
    ) -> TrackingEvent:
        """Record a link-click event."""
        now = datetime.now(timezone.utc)
        metadata = dict(metadata)
        metadata["url_clicked"] = url
        metadata["timestamp"] = now.isoformat()

        event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token=recipient_token,
            event_type=EventType.CLICKED,
            timestamp=now,
            metadata_=metadata,
        )
        db.add(event)
        await db.flush()

        await self._push_redis(
            campaign_id, EventType.CLICKED.value, recipient_token, metadata,
        )
        return event

    async def record_submission(
        self,
        campaign_id: int,
        recipient_token: str,
        field_names: list[str],
        metadata: dict,
        db: AsyncSession,
    ) -> TrackingEvent:
        """Record a credential/form submission.

        Only field *names* are stored -- never field values.
        """
        now = datetime.now(timezone.utc)
        metadata = dict(metadata)
        metadata["field_names_submitted"] = field_names
        metadata["timestamp"] = now.isoformat()

        event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token=recipient_token,
            event_type=EventType.SUBMITTED,
            timestamp=now,
            metadata_=metadata,
        )
        db.add(event)
        await db.flush()

        # Strip field names from the Redis payload (minimal data in feed).
        redis_meta = {
            "timestamp": metadata["timestamp"],
            "field_count": len(field_names),
        }
        await self._push_redis(
            campaign_id, EventType.SUBMITTED.value, recipient_token, redis_meta,
        )
        return event

    async def record_report(
        self,
        campaign_id: int,
        recipient_token: str,
        metadata: dict,
        db: AsyncSession,
    ) -> TrackingEvent:
        """Record that a user reported the phishing email."""
        now = datetime.now(timezone.utc)
        metadata = dict(metadata)
        metadata["timestamp"] = now.isoformat()

        event = TrackingEvent(
            campaign_id=campaign_id,
            recipient_token=recipient_token,
            event_type=EventType.REPORTED,
            timestamp=now,
            metadata_=metadata,
        )
        db.add(event)
        await db.flush()

        await self._push_redis(
            campaign_id, EventType.REPORTED.value, recipient_token, metadata,
        )
        return event
