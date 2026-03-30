"""Celery Beat tasks for campaign scheduling, progress monitoring, and cleanup."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, delete

from app.celery_app import celery
from app.database import async_session
from app.models.campaign import Campaign, CampaignStatus
from app.models.tracking import CampaignRecipient, RecipientStatus

logger = logging.getLogger(__name__)

# Redis key prefix for campaign counters (must match dispatcher.py).
_COUNTER_PREFIX = "tidepool:campaign_counters"


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery worker context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _get_redis():
    """Return a synchronous Redis client."""
    import redis as _redis
    from app.config import settings

    return _redis.from_url(settings.REDIS_URL)


# ---------------------------------------------------------------------------
# check_and_launch_scheduled
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.scheduler.check_and_launch_scheduled",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
)
def check_and_launch_scheduled(self) -> dict:
    """Query campaigns with status=SCHEDULED whose send window has arrived.

    For each matching campaign, dispatch the campaign task and transition
    the status to RUNNING.
    """
    try:
        return _run_async(_check_and_launch_async())
    except Exception as exc:
        logger.exception("check_and_launch_scheduled failed")
        raise self.retry(exc=exc)


async def _check_and_launch_async() -> dict:
    now = datetime.now(timezone.utc)
    launched: list[int] = []

    async with async_session() as session:
        stmt = (
            select(Campaign)
            .where(
                Campaign.status == CampaignStatus.SCHEDULED,
                Campaign.send_window_start <= now,
            )
        )
        result = await session.execute(stmt)
        campaigns = result.scalars().all()

        for campaign in campaigns:
            campaign.status = CampaignStatus.RUNNING
            launched.append(campaign.id)
            logger.info(
                "Launching scheduled campaign %d (%s)",
                campaign.id, campaign.name,
            )

        if launched:
            await session.commit()

    # Dispatch each campaign outside the DB session.
    from app.engine.dispatcher import dispatch_campaign
    for campaign_id in launched:
        dispatch_campaign.apply_async(args=[campaign_id])

    return {"launched": launched, "checked_at": now.isoformat()}


# ---------------------------------------------------------------------------
# check_all_campaign_progress
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.scheduler.check_all_campaign_progress",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def check_all_campaign_progress(self) -> dict:
    """Check progress of all RUNNING campaigns.

    - If all recipients processed -> mark COMPLETED.
    - If send_window_end has passed -> mark COMPLETED (with warning).
    - If running > 2x expected duration -> log alert.
    """
    try:
        return _run_async(_check_all_progress_async())
    except Exception as exc:
        logger.exception("check_all_campaign_progress failed")
        raise self.retry(exc=exc)


async def _check_all_progress_async() -> dict:
    now = datetime.now(timezone.utc)
    completed: list[int] = []
    still_running: list[int] = []
    alerts: list[int] = []

    async with async_session() as session:
        stmt = select(Campaign).where(Campaign.status == CampaignStatus.RUNNING)
        result = await session.execute(stmt)
        campaigns = result.scalars().all()

        for campaign in campaigns:
            # Count pending recipients.
            pending_stmt = (
                select(func.count())
                .select_from(CampaignRecipient)
                .where(
                    CampaignRecipient.campaign_id == campaign.id,
                    CampaignRecipient.status == RecipientStatus.PENDING,
                )
            )
            pending = (await session.execute(pending_stmt)).scalar() or 0

            if pending == 0:
                campaign.status = CampaignStatus.COMPLETED
                completed.append(campaign.id)
                logger.info("Campaign %d completed -- all recipients processed", campaign.id)
                continue

            # Check if send window has expired.
            if campaign.send_window_end and campaign.send_window_end <= now:
                campaign.status = CampaignStatus.COMPLETED
                completed.append(campaign.id)
                logger.warning(
                    "Campaign %d completed -- send window expired with %d recipients still pending",
                    campaign.id, pending,
                )
                continue

            # Check for stalled campaigns (running > 2x expected duration).
            _check_stalled(campaign, now, alerts)

            still_running.append(campaign.id)

        if completed:
            await session.commit()

    return {
        "completed": completed,
        "still_running": still_running,
        "alerts": alerts,
        "checked_at": now.isoformat(),
    }


def _check_stalled(campaign: Campaign, now: datetime, alerts: list[int]) -> None:
    """Log an alert if the campaign has been running far longer than expected."""
    try:
        r = _get_redis()
        key = f"{_COUNTER_PREFIX}:{campaign.id}"
        data = r.hgetall(key)
        if not data:
            return

        start_ts = float(data.get(b"start_ts", b"0"))
        total = int(data.get(b"total", b"0"))
        sent = int(data.get(b"sent", b"0"))

        if start_ts == 0 or total == 0:
            return

        elapsed = now.timestamp() - start_ts

        # Estimate expected duration from send window or a default of 4 hours.
        if campaign.send_window_start and campaign.send_window_end:
            expected = (campaign.send_window_end - campaign.send_window_start).total_seconds()
        else:
            expected = 4 * 3600.0

        if elapsed > expected * 2:
            alerts.append(campaign.id)
            logger.warning(
                "ALERT: Campaign %d has been running for %.0f seconds "
                "(2x expected %.0f seconds). Sent %d/%d.",
                campaign.id, elapsed, expected, sent, total,
            )
    except Exception:
        logger.debug("Could not check stall status for campaign %d", campaign.id)


# ---------------------------------------------------------------------------
# cleanup_expired_data
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.scheduler.cleanup_expired_data",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_expired_data(self) -> dict:
    """Daily cleanup of stale data.

    - Delete Redis campaign counter keys for campaigns completed > 30 days ago.
    - Remove orphaned upload files older than 7 days.
    - Delete expired API keys from the database.
    """
    try:
        return _run_async(_cleanup_async())
    except Exception as exc:
        logger.exception("cleanup_expired_data failed")
        raise self.retry(exc=exc)


async def _cleanup_async() -> dict:
    now = datetime.now(timezone.utc)
    cleaned_redis = 0
    cleaned_files = 0
    cleaned_keys = 0

    # -- 1. Redis campaign counters for old completed campaigns ---------------
    cutoff_30d = now - timedelta(days=30)

    async with async_session() as session:
        old_campaigns_stmt = (
            select(Campaign.id)
            .where(
                Campaign.status == CampaignStatus.COMPLETED,
                Campaign.updated_at <= cutoff_30d,
            )
        )
        result = await session.execute(old_campaigns_stmt)
        old_ids = [row[0] for row in result.all()]

    if old_ids:
        try:
            r = _get_redis()
            for cid in old_ids:
                key = f"{_COUNTER_PREFIX}:{cid}"
                if r.delete(key):
                    cleaned_redis += 1
        except Exception:
            logger.exception("Failed to clean Redis campaign counter keys")

    # -- 2. Orphaned upload files older than 7 days ---------------------------
    from app.config import settings

    upload_dir = getattr(settings, "UPLOAD_DIR", "/var/lib/tidepool/uploads")
    cutoff_7d = now - timedelta(days=7)

    if os.path.isdir(upload_dir):
        try:
            for entry in os.scandir(upload_dir):
                if entry.is_file():
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff_7d:
                        os.remove(entry.path)
                        cleaned_files += 1
                        logger.debug("Removed orphaned upload: %s", entry.path)
        except Exception:
            logger.exception("Failed to clean orphaned uploads in %s", upload_dir)

    # -- 3. Expired API keys --------------------------------------------------
    try:
        async with async_session() as session:
            # Only attempt if the api_keys table exists in the metadata.
            from app.database import Base
            if "api_keys" in Base.metadata.tables:
                from sqlalchemy import text
                result = await session.execute(
                    text(
                        "DELETE FROM api_keys WHERE expires_at IS NOT NULL "
                        "AND expires_at < :now"
                    ),
                    {"now": now},
                )
                cleaned_keys = result.rowcount or 0
                await session.commit()
    except Exception:
        logger.debug("Skipped API key cleanup (table may not exist)")

    logger.info(
        "Cleanup complete: %d Redis keys, %d upload files, %d API keys removed",
        cleaned_redis, cleaned_files, cleaned_keys,
    )

    return {
        "redis_keys_removed": cleaned_redis,
        "upload_files_removed": cleaned_files,
        "api_keys_removed": cleaned_keys,
        "cleaned_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# aggregate_daily_metrics (placeholder -- delegates to reports module)
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.scheduler.aggregate_daily_metrics",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def aggregate_daily_metrics(self) -> dict:
    """Trigger the daily metrics aggregation pipeline.

    Delegates to ``app.reports.tasks.aggregate_daily_metrics`` so that
    reporting logic stays in the reports module.
    """
    from app.reports.tasks import aggregate_daily_metrics as _agg
    return _agg()
