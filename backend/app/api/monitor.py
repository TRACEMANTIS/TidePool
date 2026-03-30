"""Real-time campaign monitoring API.

All endpoints read from Redis for speed. Database queries are avoided
on the hot path to keep latency minimal during active campaigns.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.schemas.tracking import (
    ActiveCampaignSummary,
    EventFeedItem,
    EventFeedResponse,
    LiveCampaignStats,
    SendRatePoint,
)
from app.tracking.realtime import RealtimeTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor")


# -- Redis dependency -------------------------------------------------------

async def _get_redis() -> aioredis.Redis:
    """Yield an async Redis client."""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _get_tracker() -> RealtimeTracker:
    """Build a RealtimeTracker backed by a fresh Redis connection."""
    client = await _get_redis()
    return RealtimeTracker(client)


# -- Endpoints --------------------------------------------------------------


@router.get("/campaigns/{campaign_id}/live", response_model=LiveCampaignStats)
async def live_campaign_stats(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> LiveCampaignStats:
    """Return real-time stats for a single campaign.

    Reads counters from Redis. Falls back to zeroed stats if Redis is
    unavailable.
    """
    # Verify campaign exists.
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    try:
        redis_client = await _get_redis()
        tracker = RealtimeTracker(redis_client)
        counts = await tracker.get_live_counts(campaign_id)
        send_rate = await tracker.get_send_rate(campaign_id)
        await redis_client.aclose()
    except Exception:
        logger.warning("Redis unavailable for live stats (campaign %s)", campaign_id)
        counts = {}
        send_rate = 0.0

    # Compute elapsed time and ETA.
    elapsed = 0.0
    eta = None
    if campaign.send_window_start is not None:
        start = campaign.send_window_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    total_recipients = len(campaign.recipients) if campaign.recipients else 0
    sent_count = counts.get("SENT", 0)
    if send_rate > 0 and total_recipients > sent_count:
        remaining = total_recipients - sent_count
        eta = (remaining / send_rate) * 60.0  # send_rate is per minute

    return LiveCampaignStats(
        sent=counts.get("SENT", 0),
        delivered=counts.get("DELIVERED", 0),
        opened=counts.get("OPENED", 0),
        clicked=counts.get("CLICKED", 0),
        submitted=counts.get("SUBMITTED", 0),
        reported=counts.get("REPORTED", 0),
        send_rate_per_minute=send_rate,
        elapsed_seconds=max(0.0, elapsed),
        eta_seconds=eta,
        status=campaign.status.value,
    )


@router.get("/campaigns/{campaign_id}/feed", response_model=EventFeedResponse)
async def event_feed(
    campaign_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> EventFeedResponse:
    """Return recent tracking events for a campaign.

    Cursor-based pagination: the ``cursor`` is a timestamp string. Events
    older than the cursor are returned.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    try:
        redis_client = await _get_redis()
        tracker = RealtimeTracker(redis_client)

        if cursor is not None:
            # Cursor is a timestamp -- fetch events scored below it.
            try:
                max_score = float(cursor)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor.")
            raw = await redis_client.zrevrangebyscore(
                tracker._events_key(campaign_id),
                max=max_score,
                min="-inf",
                start=0,
                num=limit + 1,
            )
        else:
            raw = await redis_client.zrevrange(
                tracker._events_key(campaign_id),
                0,
                limit,  # fetch one extra to detect has_more
            )

        await redis_client.aclose()
    except HTTPException:
        raise
    except Exception:
        logger.warning("Redis unavailable for event feed (campaign %s)", campaign_id)
        return EventFeedResponse(events=[], next_cursor=None, has_more=False)

    events: list[EventFeedItem] = []
    for entry in raw[: limit]:
        try:
            data = entry if isinstance(entry, str) else entry.decode("utf-8")
            parsed = json.loads(data)
            events.append(EventFeedItem(
                event_type=parsed.get("event_type", "UNKNOWN"),
                recipient_token=parsed.get("recipient_token", ""),
                timestamp=parsed.get("timestamp", ""),
                metadata=parsed.get("metadata"),
            ))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

    has_more = len(raw) > limit
    next_cursor = None
    if has_more and events:
        # Use the timestamp of the last returned event as the next cursor.
        last_ts = events[-1].timestamp
        try:
            from datetime import datetime as _dt
            parsed_ts = _dt.fromisoformat(last_ts)
            next_cursor = str(parsed_ts.timestamp())
        except (ValueError, TypeError):
            next_cursor = str(time.time())

    return EventFeedResponse(
        events=events,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/campaigns/{campaign_id}/send-rate", response_model=list[SendRatePoint])
async def send_rate_timeseries(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[SendRatePoint]:
    """Return send-rate data bucketed by minute for the last 5 minutes."""
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    try:
        redis_client = await _get_redis()
        now = time.time()
        key = RealtimeTracker._send_times_key(campaign_id)

        # Retrieve all send timestamps in the last 5 minutes.
        raw_timestamps = await redis_client.zrangebyscore(
            key, now - 300, now,
        )
        await redis_client.aclose()
    except Exception:
        logger.warning("Redis unavailable for send-rate (campaign %s)", campaign_id)
        return []

    # Bucket by minute.
    buckets: dict[int, int] = {}
    for ts_str in raw_timestamps:
        try:
            ts = float(ts_str)
        except (ValueError, TypeError):
            continue
        bucket = int(ts // 60) * 60
        buckets[bucket] = buckets.get(bucket, 0) + 1

    # Build sorted time series.
    points: list[SendRatePoint] = []
    for bucket_ts in sorted(buckets):
        dt = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
        points.append(SendRatePoint(
            timestamp=dt.isoformat(),
            rate=float(buckets[bucket_ts]),
        ))

    return points


@router.get("/active", response_model=list[ActiveCampaignSummary])
async def active_campaigns(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ActiveCampaignSummary]:
    """List all currently running campaigns with summary stats from Redis."""
    result = await db.execute(
        select(Campaign).where(Campaign.status == CampaignStatus.RUNNING)
    )
    campaigns = result.scalars().all()

    if not campaigns:
        return []

    summaries: list[ActiveCampaignSummary] = []
    try:
        redis_client = await _get_redis()
        tracker = RealtimeTracker(redis_client)

        for c in campaigns:
            counts = await tracker.get_live_counts(c.id)
            send_rate = await tracker.get_send_rate(c.id)

            total = len(c.recipients) if c.recipients else 0
            sent = counts.get("SENT", 0)
            progress = (sent / total * 100.0) if total > 0 else 0.0

            started = None
            if c.send_window_start is not None:
                started = c.send_window_start.isoformat()

            summaries.append(ActiveCampaignSummary(
                campaign_id=c.id,
                name=c.name,
                status=c.status.value,
                progress_percent=round(progress, 1),
                send_rate=send_rate,
                started_at=started,
            ))

        await redis_client.aclose()
    except Exception:
        logger.warning("Redis unavailable for active campaign listing")
        # Return DB-only data without Redis stats.
        for c in campaigns:
            started = None
            if c.send_window_start is not None:
                started = c.send_window_start.isoformat()
            summaries.append(ActiveCampaignSummary(
                campaign_id=c.id,
                name=c.name,
                status=c.status.value,
                progress_percent=0.0,
                send_rate=0.0,
                started_at=started,
            ))

    return summaries
