"""Celery tasks for campaign email dispatch.

Entry point: ``dispatch_campaign(campaign_id)`` loads the campaign
configuration, creates recipient records, calculates throttle parameters,
and fans out ``send_batch`` tasks to deliver emails through the configured
SMTP backend.
"""

from __future__ import annotations

import asyncio
import logging
import math
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.celery_app import celery
from app.database import async_session
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.tracking import (
    CampaignRecipient,
    EventType,
    RecipientStatus,
    TrackingEvent,
)
from app.engine.renderer import EmailRenderer
from app.engine.smtp_backends import get_backend
from app.engine.throttle import SendThrottle, calculate_throttle

logger = logging.getLogger(__name__)

# Default batch size when the campaign does not specify one.
_DEFAULT_BATCH_SIZE = 50

# Maximum emails in a single batch task to bound memory and task duration.
_MAX_BATCH_SIZE = 200

# Default send window in hours if the campaign has no window configured.
_DEFAULT_WINDOW_HOURS = 4.0

# Redis key prefix for campaign counters.
_COUNTER_PREFIX = "tidepool:campaign_counters"


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery worker context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (unlikely in Celery worker, but
            # handle gracefully by creating a new loop in a thread).
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# dispatch_campaign
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.dispatcher.dispatch_campaign",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def dispatch_campaign(self, campaign_id: int) -> dict:
    """Main entry point -- prepare and launch a campaign.

    1. Load campaign configuration from the database.
    2. Create ``CampaignRecipient`` records for every contact in the
       campaign's address book (skipping duplicates).
    3. Calculate batch sizes and throttle rate from the campaign's
       ``throttle_rate`` and send window.
    4. Fan out ``send_batch`` sub-tasks.
    5. Update campaign status to ``RUNNING``.
    """
    try:
        result = _run_async(_dispatch_campaign_async(campaign_id))
        return result
    except Exception as exc:
        logger.exception("dispatch_campaign failed for campaign %d", campaign_id)
        raise self.retry(exc=exc)


async def _dispatch_campaign_async(campaign_id: int) -> dict:
    """Async implementation of campaign dispatch."""
    async with async_session() as session:
        # -- Load campaign ---------------------------------------------------
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()

        if campaign is None:
            logger.error("Campaign %d not found", campaign_id)
            return {"status": "error", "reason": "campaign_not_found"}

        if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.SCHEDULED):
            logger.warning(
                "Campaign %d is in state %s, cannot dispatch",
                campaign_id, campaign.status.value,
            )
            return {"status": "error", "reason": f"invalid_status:{campaign.status.value}"}

        # -- Resolve contacts via recipients relationship --------------------
        # The campaign->recipients relationship holds CampaignRecipient rows.
        # If none exist yet we need to look up contacts.  The campaign model
        # does not carry an address_book_id column directly, so we load all
        # contacts linked through the recipients relationship.  If no
        # recipients have been created yet, we look for contacts in the
        # address book referenced by the API schema (stored externally by the
        # campaign-creation endpoint).  For now, we check whether recipients
        # already exist; if not, we create them from the contacts table where
        # contacts already reference this campaign via CampaignRecipient or,
        # failing that, from *all* contacts (the API layer is expected to
        # pre-populate recipients at campaign creation time).

        existing_count_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(CampaignRecipient.campaign_id == campaign_id)
        )
        existing_count = (await session.execute(existing_count_stmt)).scalar() or 0

        if existing_count == 0:
            # Attempt to create recipients from contacts.  In a full
            # implementation the campaign would carry an address_book_id or
            # the API layer would have pre-populated recipients.  We create
            # records for all contacts that don't already have a recipient
            # entry for this campaign.
            contact_stmt = select(Contact)
            contact_result = await session.execute(contact_stmt)
            contacts = contact_result.scalars().all()

            if not contacts:
                logger.error("No contacts available for campaign %d", campaign_id)
                return {"status": "error", "reason": "no_contacts"}

            for contact in contacts:
                recipient = CampaignRecipient(
                    campaign_id=campaign_id,
                    contact_id=contact.id,
                    token=secrets.token_urlsafe(32),
                    status=RecipientStatus.PENDING,
                )
                session.add(recipient)

            await session.flush()
            existing_count = len(contacts)
            logger.info(
                "Created %d recipient records for campaign %d",
                existing_count, campaign_id,
            )

        # -- Calculate throttle and batch parameters -------------------------
        window_hours = _DEFAULT_WINDOW_HOURS
        if campaign.send_window_start and campaign.send_window_end:
            delta = campaign.send_window_end - campaign.send_window_start
            window_hours = max(0.1, delta.total_seconds() / 3600.0)

        rate_per_minute = campaign.throttle_rate or calculate_throttle(
            existing_count, window_hours,
        )
        batch_size = min(_MAX_BATCH_SIZE, max(1, rate_per_minute))

        # -- Load all pending recipient IDs ----------------------------------
        pending_stmt = (
            select(CampaignRecipient.contact_id)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status == RecipientStatus.PENDING,
            )
        )
        pending_result = await session.execute(pending_stmt)
        pending_ids = [row[0] for row in pending_result.all()]

        if not pending_ids:
            logger.warning("No pending recipients for campaign %d", campaign_id)
            return {"status": "error", "reason": "no_pending_recipients"}

        # -- Update campaign status to RUNNING --------------------------------
        campaign.status = CampaignStatus.RUNNING
        await session.commit()

    # -- Initialise Redis counters -------------------------------------------
    _init_redis_counters(campaign_id, len(pending_ids))

    # -- Fan out batch tasks -------------------------------------------------
    num_batches = math.ceil(len(pending_ids) / batch_size)
    for i in range(num_batches):
        batch_ids = pending_ids[i * batch_size : (i + 1) * batch_size]
        send_batch.apply_async(
            args=[campaign_id, batch_ids],
            countdown=i * 2,  # Stagger batches slightly.
        )

    # Schedule a progress check after a reasonable delay.
    estimated_minutes = len(pending_ids) / max(1, rate_per_minute)
    check_delay = max(60, int(estimated_minutes * 60 * 0.5))
    check_campaign_progress.apply_async(
        args=[campaign_id],
        countdown=check_delay,
    )

    logger.info(
        "Campaign %d dispatched: %d recipients in %d batches at %d/min",
        campaign_id, len(pending_ids), num_batches, rate_per_minute,
    )

    return {
        "status": "dispatched",
        "campaign_id": campaign_id,
        "total_recipients": len(pending_ids),
        "num_batches": num_batches,
        "rate_per_minute": rate_per_minute,
    }


def _init_redis_counters(campaign_id: int, total: int) -> None:
    """Initialise Redis counters for tracking campaign progress."""
    try:
        import redis as _redis
        from app.config import settings

        r = _redis.from_url(settings.REDIS_URL)
        key = f"{_COUNTER_PREFIX}:{campaign_id}"
        r.hset(key, mapping={
            "sent": 0,
            "failed": 0,
            "pending": total,
            "total": total,
            "start_ts": datetime.now(timezone.utc).timestamp(),
        })
        r.expire(key, 86400 * 7)  # Keep counters for 7 days.
    except Exception:
        logger.exception("Failed to initialise Redis counters for campaign %d", campaign_id)


def _update_redis_counters(campaign_id: int, sent: int, failed: int) -> None:
    """Atomically increment sent/failed and decrement pending counters."""
    try:
        import redis as _redis
        from app.config import settings

        r = _redis.from_url(settings.REDIS_URL)
        key = f"{_COUNTER_PREFIX}:{campaign_id}"
        pipe = r.pipeline()
        pipe.hincrby(key, "sent", sent)
        pipe.hincrby(key, "failed", failed)
        pipe.hincrby(key, "pending", -(sent + failed))
        pipe.execute()
    except Exception:
        logger.exception("Failed to update Redis counters for campaign %d", campaign_id)


# ---------------------------------------------------------------------------
# send_batch
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.dispatcher.send_batch",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_batch(self, campaign_id: int, recipient_ids: list[int]) -> dict:
    """Send emails for a batch of recipients.

    Loads the SMTP profile, email template, and campaign config, then for
    each recipient: renders the template with tracking injected, sends via
    the configured SMTP backend, and updates the recipient status.
    """
    try:
        result = _run_async(_send_batch_async(campaign_id, recipient_ids))
        return result
    except Exception as exc:
        logger.exception(
            "send_batch failed for campaign %d (batch of %d)",
            campaign_id, len(recipient_ids),
        )
        raise self.retry(exc=exc)


async def _send_batch_async(campaign_id: int, recipient_contact_ids: list[int]) -> dict:
    """Async implementation of batch sending."""
    sent_count = 0
    failed_count = 0
    renderer = EmailRenderer()

    async with async_session() as session:
        # -- Load campaign and related objects --------------------------------
        stmt = select(Campaign).where(Campaign.id == campaign_id)
        result = await session.execute(stmt)
        campaign = result.scalar_one_or_none()

        if campaign is None:
            logger.error("Campaign %d not found in send_batch", campaign_id)
            return {"status": "error", "reason": "campaign_not_found"}

        if campaign.status == CampaignStatus.PAUSED:
            logger.info("Campaign %d is paused, skipping batch", campaign_id)
            return {"status": "paused", "campaign_id": campaign_id}

        if campaign.status == CampaignStatus.CANCELLED:
            logger.info("Campaign %d is cancelled, skipping batch", campaign_id)
            return {"status": "cancelled", "campaign_id": campaign_id}

        smtp_profile = campaign.smtp_profile
        template = campaign.email_template

        if smtp_profile is None:
            logger.error(
                "Campaign %d has no SMTP profile configured", campaign_id,
            )
            return {"status": "error", "reason": "missing_smtp_profile"}

        if template is None:
            logger.error(
                "Campaign %d has no email template configured", campaign_id,
            )
            return {"status": "error", "reason": "missing_email_template"}

        backend = get_backend(smtp_profile)

        # Determine the base URL for tracking.  In production this would come
        # from application config; fall back to a sensible default.
        from app.config import settings
        base_url = getattr(settings, "BASE_URL", "http://localhost:8000")

        # -- Set up throttle --------------------------------------------------
        rate = campaign.throttle_rate or 60
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(settings.REDIS_URL)
            throttle = SendThrottle(rate, redis_client, campaign_id)
        except Exception:
            logger.warning("Redis unavailable for throttling; proceeding without")
            throttle = None
            redis_client = None

        # -- Load recipients for this batch -----------------------------------
        recipient_stmt = (
            select(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.contact_id.in_(recipient_contact_ids),
            )
        )
        recipient_result = await session.execute(recipient_stmt)
        recipients = recipient_result.scalars().all()

        for recipient in recipients:
            if recipient.status != RecipientStatus.PENDING:
                continue

            # Load the contact for template rendering.
            contact_stmt = select(Contact).where(Contact.id == recipient.contact_id)
            contact_result = await session.execute(contact_stmt)
            contact = contact_result.scalar_one_or_none()

            if contact is None:
                logger.warning(
                    "Contact %d not found for campaign %d",
                    recipient.contact_id, campaign_id,
                )
                recipient.status = RecipientStatus.FAILED
                failed_count += 1
                continue

            # -- Throttle ------------------------------------------------
            if throttle is not None:
                try:
                    await throttle.acquire()
                except Exception:
                    logger.warning("Throttle acquire failed; sending without delay")

            # -- Render with tracking ------------------------------------
            token_str = str(recipient.token)
            try:
                rendered = renderer.render_with_tracking(
                    template=template,
                    contact=contact,
                    campaign_id=campaign_id,
                    recipient_token=token_str,
                    base_url=base_url,
                )
            except Exception:
                logger.exception(
                    "Template rendering failed for contact %d in campaign %d",
                    contact.id, campaign_id,
                )
                recipient.status = RecipientStatus.FAILED
                failed_count += 1
                continue

            # -- Build headers -------------------------------------------
            send_headers: dict[str, str] = {"X-TidePool-Token": token_str}
            if settings.TIDEPOOL_HEADER_ENABLED:
                from app.utils.header_signing import sign_campaign_id
                send_headers["X-TidePool-Campaign-ID"] = sign_campaign_id(
                    campaign_id,
                )

            # -- Send via SMTP backend -----------------------------------
            try:
                success = await backend.send(
                    from_addr=smtp_profile.from_address,
                    from_name=smtp_profile.from_name,
                    to_addr=contact.email,
                    subject=rendered.subject,
                    body_html=rendered.body_html,
                    body_text=rendered.body_text,
                    headers=send_headers,
                )
            except Exception:
                logger.exception(
                    "SMTP send raised exception for contact %d in campaign %d",
                    contact.id, campaign_id,
                )
                success = False

            now = datetime.now(timezone.utc)

            if success:
                recipient.status = RecipientStatus.SENT
                recipient.sent_at = now
                sent_count += 1

                # Record SENT tracking event.
                event = TrackingEvent(
                    campaign_id=campaign_id,
                    recipient_token=token_str,
                    event_type=EventType.SENT,
                    timestamp=now,
                    metadata_={"backend": smtp_profile.backend_type.value},
                )
                session.add(event)
            else:
                recipient.status = RecipientStatus.FAILED
                failed_count += 1

        await session.commit()

        # Cleanup throttle Redis client.
        if redis_client is not None:
            await redis_client.close()

    # -- Update Redis counters -----------------------------------------------
    _update_redis_counters(campaign_id, sent_count, failed_count)

    logger.info(
        "Batch complete for campaign %d: %d sent, %d failed",
        campaign_id, sent_count, failed_count,
    )

    return {
        "status": "complete",
        "campaign_id": campaign_id,
        "sent": sent_count,
        "failed": failed_count,
    }


# ---------------------------------------------------------------------------
# check_campaign_progress
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.dispatcher.check_campaign_progress",
    bind=True,
    max_retries=10,
    default_retry_delay=60,
)
def check_campaign_progress(self, campaign_id: int) -> dict:
    """Periodic task to check if all batches for a campaign have completed.

    Updates the campaign status to ``COMPLETED`` when no pending recipients
    remain.  Re-enqueues itself if work is still in progress.
    """
    try:
        result = _run_async(_check_progress_async(campaign_id))
    except Exception as exc:
        logger.exception("check_campaign_progress failed for campaign %d", campaign_id)
        raise self.retry(exc=exc)

    if result.get("status") == "in_progress":
        # Re-check in 60 seconds.
        check_campaign_progress.apply_async(
            args=[campaign_id],
            countdown=60,
        )

    return result


async def _check_progress_async(campaign_id: int) -> dict:
    """Async implementation of progress checking."""
    async with async_session() as session:
        # Count pending recipients.
        pending_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status == RecipientStatus.PENDING,
            )
        )
        pending = (await session.execute(pending_stmt)).scalar() or 0

        # Load campaign to check/update status.
        campaign_stmt = select(Campaign).where(Campaign.id == campaign_id)
        campaign = (await session.execute(campaign_stmt)).scalar_one_or_none()

        if campaign is None:
            return {"status": "error", "reason": "campaign_not_found"}

        if campaign.status in (CampaignStatus.CANCELLED, CampaignStatus.COMPLETED):
            return {"status": campaign.status.value.lower(), "campaign_id": campaign_id}

        if pending > 0:
            logger.info(
                "Campaign %d still has %d pending recipients", campaign_id, pending,
            )
            return {
                "status": "in_progress",
                "campaign_id": campaign_id,
                "pending": pending,
            }

        # All recipients processed -- mark campaign complete.
        campaign.status = CampaignStatus.COMPLETED
        await session.commit()

        # Gather final counts for the return value.
        sent_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status == RecipientStatus.SENT,
            )
        )
        sent = (await session.execute(sent_stmt)).scalar() or 0

        failed_stmt = (
            select(func.count())
            .select_from(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign_id,
                CampaignRecipient.status == RecipientStatus.FAILED,
            )
        )
        failed = (await session.execute(failed_stmt)).scalar() or 0

        logger.info(
            "Campaign %d completed: %d sent, %d failed", campaign_id, sent, failed,
        )

        return {
            "status": "completed",
            "campaign_id": campaign_id,
            "sent": sent,
            "failed": failed,
        }
