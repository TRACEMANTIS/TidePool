"""Celery tasks for the reports module."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="app.reports.tasks.aggregate_daily_metrics",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def aggregate_daily_metrics(self) -> dict:
    """Aggregate campaign metrics for the previous day.

    This task runs daily at 03:00 UTC via Celery Beat.  It collects
    per-campaign and per-department metrics for all campaigns that were
    active during the previous calendar day and persists snapshot rows
    for historical trend analysis.
    """
    import asyncio

    try:
        return asyncio.run(_aggregate_async())
    except Exception as exc:
        logger.exception("aggregate_daily_metrics failed")
        raise self.retry(exc=exc)


async def _aggregate_async() -> dict:
    """Async implementation of daily metrics aggregation."""
    from sqlalchemy import select, and_
    from app.database import async_session
    from app.models.campaign import Campaign, CampaignStatus
    from app.reports.aggregator import MetricsAggregator

    now = datetime.now(timezone.utc)
    yesterday_start = (now - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    yesterday_end = yesterday_start + timedelta(days=1)

    aggregator = MetricsAggregator()
    aggregated_campaigns: list[int] = []

    async with async_session() as session:
        # Find campaigns that were active (RUNNING or COMPLETED) during yesterday.
        stmt = select(Campaign).where(
            Campaign.status.in_([
                CampaignStatus.RUNNING,
                CampaignStatus.COMPLETED,
                CampaignStatus.PAUSED,
            ]),
            Campaign.updated_at >= yesterday_start,
        )
        result = await session.execute(stmt)
        campaigns = result.scalars().all()

        for campaign in campaigns:
            try:
                metrics = await aggregator.get_campaign_metrics(campaign.id, session)
                aggregated_campaigns.append(campaign.id)
                logger.info(
                    "Aggregated metrics for campaign %d: %d sent, %.1f%% open rate",
                    campaign.id, metrics.sent, metrics.open_rate,
                )
            except Exception:
                logger.exception(
                    "Failed to aggregate metrics for campaign %d", campaign.id,
                )

    logger.info(
        "Daily metrics aggregation complete: %d campaigns processed",
        len(aggregated_campaigns),
    )

    return {
        "aggregated_campaigns": aggregated_campaigns,
        "period_start": yesterday_start.isoformat(),
        "period_end": yesterday_end.isoformat(),
        "completed_at": now.isoformat(),
    }
