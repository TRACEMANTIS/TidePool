"""Celery application configuration for async task processing."""

from celery import Celery
from celery.schedules import crontab  # noqa: F401 -- available for beat schedule

from app.config import settings

celery = Celery(
    "tidepool",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Autodiscover tasks in these modules.
celery.autodiscover_tasks(
    [
        "app.engine",
        "app.addressbook",
        "app.automation",
        "app.reports",
    ]
)

# Beat schedule -- periodic tasks.
celery.conf.beat_schedule = {
    "check-scheduled-campaigns": {
        "task": "app.engine.scheduler.check_and_launch_scheduled",
        "schedule": 60.0,  # Every 60 seconds.
    },
    "check-campaign-progress": {
        "task": "app.engine.scheduler.check_all_campaign_progress",
        "schedule": 120.0,  # Every 120 seconds.
    },
    "cleanup-expired-tokens": {
        "task": "app.engine.scheduler.cleanup_expired_data",
        "schedule": crontab(minute=0, hour=2),  # Daily at 02:00 UTC.
    },
    "aggregate-daily-metrics": {
        "task": "app.reports.tasks.aggregate_daily_metrics",
        "schedule": crontab(minute=0, hour=3),  # Daily at 03:00 UTC.
    },
}
