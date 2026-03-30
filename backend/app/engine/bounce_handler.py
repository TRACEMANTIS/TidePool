"""Bounce and complaint processing for campaign emails.

Includes provider-specific parsers for AWS SES (SNS), Mailgun, and SendGrid
webhook payloads, plus the core bounce processing logic that updates
recipient status and contact flags.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.celery_app import celery
from app.database import async_session
from app.models.contact import Contact
from app.models.tracking import CampaignRecipient, RecipientStatus, TrackingEvent, EventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BounceEvent dataclass
# ---------------------------------------------------------------------------

class BounceType(str, enum.Enum):
    HARD = "HARD"          # Permanent delivery failure (bad address, domain gone).
    SOFT = "SOFT"          # Temporary failure (mailbox full, greylisting).
    COMPLAINT = "COMPLAINT"  # Recipient marked the message as spam.


@dataclass
class BounceEvent:
    """Normalised bounce event produced by provider-specific parsers."""

    recipient_email: str
    bounce_type: BounceType
    message: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider-specific parsers
# ---------------------------------------------------------------------------

class SESBounceProcessor:
    """Parse AWS SES bounce/complaint notifications delivered via SNS."""

    def parse_sns_notification(self, payload: dict) -> BounceEvent | None:
        """Parse an SNS notification payload into a BounceEvent.

        Handles two SNS message types:
        - SubscriptionConfirmation: returns None (caller should confirm).
        - Notification: extracts bounce/complaint data.
        """
        msg_type = payload.get("Type", "")

        if msg_type == "SubscriptionConfirmation":
            # Caller is responsible for confirming the subscription.
            logger.info("SNS SubscriptionConfirmation received")
            return None

        if msg_type != "Notification":
            logger.warning("Unrecognised SNS message type: %s", msg_type)
            return None

        import json
        try:
            message = json.loads(payload.get("Message", "{}"))
        except (json.JSONDecodeError, TypeError):
            logger.error("Failed to parse SNS Message JSON")
            return None

        notification_type = message.get("notificationType", "")

        if notification_type == "Bounce":
            bounce = message.get("bounce", {})
            bounced_recipients = bounce.get("bouncedRecipients", [])
            if not bounced_recipients:
                return None

            recipient_email = bounced_recipients[0].get("emailAddress", "")
            bounce_sub_type = bounce.get("bounceType", "Permanent")

            if bounce_sub_type == "Permanent":
                b_type = BounceType.HARD
            else:
                b_type = BounceType.SOFT

            diagnostic = bounced_recipients[0].get("diagnosticCode", "")
            ts_str = bounce.get("timestamp", "")

            return BounceEvent(
                recipient_email=recipient_email,
                bounce_type=b_type,
                message=diagnostic,
                timestamp=_parse_timestamp(ts_str),
                raw_data=payload,
            )

        elif notification_type == "Complaint":
            complaint = message.get("complaint", {})
            complained_recipients = complaint.get("complainedRecipients", [])
            if not complained_recipients:
                return None

            recipient_email = complained_recipients[0].get("emailAddress", "")
            ts_str = complaint.get("timestamp", "")

            return BounceEvent(
                recipient_email=recipient_email,
                bounce_type=BounceType.COMPLAINT,
                message="Recipient filed a spam complaint",
                timestamp=_parse_timestamp(ts_str),
                raw_data=payload,
            )

        logger.debug("Ignoring SES notification type: %s", notification_type)
        return None


class MailgunBounceProcessor:
    """Parse Mailgun event webhook payloads."""

    def parse_webhook(self, payload: dict) -> BounceEvent | None:
        """Parse a Mailgun webhook payload into a BounceEvent."""
        event_data = payload.get("event-data", payload)
        event_type = event_data.get("event", "")

        type_map = {
            "bounced": BounceType.HARD,
            "dropped": BounceType.HARD,
            "complained": BounceType.COMPLAINT,
        }

        bounce_type = type_map.get(event_type)
        if bounce_type is None:
            logger.debug("Ignoring Mailgun event type: %s", event_type)
            return None

        # Mailgun 'dropped' with temporary reason is a soft bounce.
        if event_type == "dropped":
            severity = event_data.get("severity", "permanent")
            if severity == "temporary":
                bounce_type = BounceType.SOFT

        recipient = event_data.get("recipient", "")
        message = event_data.get("delivery-status", {}).get("message", "")
        if not message:
            message = event_data.get("reason", "")

        ts = event_data.get("timestamp")
        timestamp = datetime.fromtimestamp(float(ts), tz=timezone.utc) if ts else datetime.now(timezone.utc)

        return BounceEvent(
            recipient_email=recipient,
            bounce_type=bounce_type,
            message=message,
            timestamp=timestamp,
            raw_data=payload,
        )


class SendGridBounceProcessor:
    """Parse SendGrid Event Webhook payloads."""

    def parse_webhook(self, payload: list[dict]) -> list[BounceEvent]:
        """Parse a SendGrid webhook payload (array of events) into BounceEvents."""
        events: list[BounceEvent] = []

        type_map = {
            "bounce": BounceType.HARD,
            "dropped": BounceType.HARD,
            "spamreport": BounceType.COMPLAINT,
        }

        for item in payload:
            event_type = item.get("event", "")
            bounce_type = type_map.get(event_type)
            if bounce_type is None:
                continue

            # SendGrid bounce with type "blocked" is typically soft.
            if event_type == "bounce" and item.get("type") == "blocked":
                bounce_type = BounceType.SOFT

            recipient = item.get("email", "")
            message = item.get("reason", "")
            ts = item.get("timestamp")
            timestamp = (
                datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if ts else datetime.now(timezone.utc)
            )

            events.append(BounceEvent(
                recipient_email=recipient,
                bounce_type=bounce_type,
                message=message,
                timestamp=timestamp,
                raw_data=item,
            ))

        return events


# ---------------------------------------------------------------------------
# Core bounce handler
# ---------------------------------------------------------------------------

class BounceHandler:
    """Process bounce and complaint notifications for campaign recipients.

    Updates the ``CampaignRecipient`` status, records ``TrackingEvent``
    entries, and flags contacts on hard bounces or complaints.
    """

    async def process_bounce(
        self,
        bounce_event: BounceEvent,
        campaign_id: int | None = None,
    ) -> bool:
        """Handle a single bounce event.

        Parameters
        ----------
        bounce_event:
            Normalised bounce event from a provider parser.
        campaign_id:
            Optional campaign ID to scope the lookup.  If None, all
            matching recipients are updated.

        Returns
        -------
        bool
            True if the bounce was processed successfully.
        """
        async with async_session() as session:
            try:
                # Look up recipient(s) by email.
                stmt = (
                    select(CampaignRecipient)
                    .join(Contact, Contact.id == CampaignRecipient.contact_id)
                    .where(Contact.email == bounce_event.recipient_email)
                )
                if campaign_id is not None:
                    stmt = stmt.where(CampaignRecipient.campaign_id == campaign_id)

                result = await session.execute(stmt)
                recipients = result.scalars().all()

                if not recipients:
                    logger.warning(
                        "Bounce for unknown recipient email: %s",
                        bounce_event.recipient_email,
                    )
                    return False

                for recipient in recipients:
                    # Update recipient status to BOUNCED for hard bounces and complaints.
                    if bounce_event.bounce_type in (BounceType.HARD, BounceType.COMPLAINT):
                        recipient.status = RecipientStatus.BOUNCED

                    # Record tracking event.
                    event = TrackingEvent(
                        campaign_id=recipient.campaign_id,
                        recipient_token=str(recipient.token),
                        event_type=EventType.DELIVERED,
                        timestamp=bounce_event.timestamp,
                        metadata_={
                            "bounce_type": bounce_event.bounce_type.value,
                            "bounce_message": bounce_event.message,
                            "is_bounce": True,
                            "recipient_email": bounce_event.recipient_email,
                        },
                    )
                    session.add(event)

                # Flag contact across all address books on hard bounce.
                if bounce_event.bounce_type == BounceType.HARD:
                    await session.execute(
                        update(Contact)
                        .where(Contact.email == bounce_event.recipient_email)
                        .values(
                            is_valid_email=False,
                            bounce_count=Contact.bounce_count + 1,
                        )
                    )
                elif bounce_event.bounce_type == BounceType.COMPLAINT:
                    await session.execute(
                        update(Contact)
                        .where(Contact.email == bounce_event.recipient_email)
                        .values(do_not_email=True)
                    )
                elif bounce_event.bounce_type == BounceType.SOFT:
                    await session.execute(
                        update(Contact)
                        .where(Contact.email == bounce_event.recipient_email)
                        .values(bounce_count=Contact.bounce_count + 1)
                    )

                await session.commit()

                logger.info(
                    "Processed %s bounce for %s (%d recipient records updated)",
                    bounce_event.bounce_type.value,
                    bounce_event.recipient_email,
                    len(recipients),
                )
                return True

            except Exception:
                await session.rollback()
                logger.exception(
                    "Failed to process bounce for %s", bounce_event.recipient_email,
                )
                return False

    async def process_bounce_legacy(
        self,
        recipient_token: str,
        bounce_type: BounceType | str,
        bounce_message: str = "",
    ) -> bool:
        """Legacy interface: handle a bounce by recipient token.

        Preserved for backward compatibility with existing callers.
        """
        if isinstance(bounce_type, str):
            try:
                bounce_type = BounceType(bounce_type.upper())
            except ValueError:
                logger.error("Unknown bounce type: %s", bounce_type)
                return False

        async with async_session() as session:
            try:
                stmt = select(CampaignRecipient).where(
                    CampaignRecipient.token == recipient_token,
                )
                result = await session.execute(stmt)
                recipient = result.scalar_one_or_none()

                if recipient is None:
                    logger.warning(
                        "Bounce for unknown recipient token: %s", recipient_token,
                    )
                    return False

                # Load contact email for the BounceEvent.
                contact_stmt = select(Contact).where(Contact.id == recipient.contact_id)
                contact = (await session.execute(contact_stmt)).scalar_one_or_none()
                email = contact.email if contact else ""

                bounce_event = BounceEvent(
                    recipient_email=email,
                    bounce_type=bounce_type,
                    message=bounce_message,
                )

                return await self.process_bounce(bounce_event, campaign_id=recipient.campaign_id)

            except Exception:
                await session.rollback()
                logger.exception(
                    "Failed to process bounce for token %s", recipient_token,
                )
                return False


# ---------------------------------------------------------------------------
# Celery task -- webhook entry point
# ---------------------------------------------------------------------------

@celery.task(
    name="app.engine.bounce_handler.process_bounce_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_bounce_notification(self, data: dict) -> dict:
    """Celery task to process an incoming bounce webhook notification.

    Expected *data* keys (new format):
        - ``recipient_email`` (str): Recipient email address.
        - ``bounce_type`` (str): HARD / SOFT / COMPLAINT.
        - ``bounce_message`` (str, optional): Diagnostic text.
        - ``campaign_id`` (int, optional): Scope to a specific campaign.

    Legacy format (still supported):
        - ``recipient_token`` (str): Recipient UUID.
        - ``bounce_type`` (str): HARD / SOFT / COMPLAINT.
        - ``bounce_message`` (str, optional): Diagnostic text.
    """
    import asyncio

    handler = BounceHandler()

    # Determine which format we received.
    recipient_email = data.get("recipient_email", "")
    recipient_token = data.get("recipient_token", "")
    bounce_type_str = data.get("bounce_type", "HARD")
    bounce_message = data.get("bounce_message", "")
    campaign_id = data.get("campaign_id")

    if not recipient_email and not recipient_token:
        logger.error("Bounce notification missing recipient identifier: %s", data)
        return {"status": "error", "reason": "missing_recipient_identifier"}

    try:
        if recipient_email:
            try:
                bt = BounceType(bounce_type_str.upper())
            except ValueError:
                bt = BounceType.HARD

            event = BounceEvent(
                recipient_email=recipient_email,
                bounce_type=bt,
                message=bounce_message,
                raw_data=data,
            )
            result = asyncio.run(handler.process_bounce(event, campaign_id=campaign_id))
        else:
            result = asyncio.run(
                handler.process_bounce_legacy(recipient_token, bounce_type_str, bounce_message),
            )
    except Exception as exc:
        logger.exception("Bounce processing failed, retrying")
        raise self.retry(exc=exc)

    return {
        "status": "processed" if result else "failed",
        "recipient_email": recipient_email or recipient_token,
        "bounce_type": bounce_type_str,
    }


@celery.task(
    name="app.engine.bounce_handler.process_bounce_batch",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_bounce_batch(self, events_data: list[dict]) -> dict:
    """Process a batch of bounce events (used by SendGrid webhook)."""
    import asyncio

    handler = BounceHandler()
    processed = 0
    failed = 0

    for item in events_data:
        try:
            bt_str = item.get("bounce_type", "HARD")
            try:
                bt = BounceType(bt_str.upper())
            except ValueError:
                bt = BounceType.HARD

            event = BounceEvent(
                recipient_email=item.get("recipient_email", ""),
                bounce_type=bt,
                message=item.get("bounce_message", ""),
                raw_data=item,
            )
            result = asyncio.run(handler.process_bounce(event))
            if result:
                processed += 1
            else:
                failed += 1
        except Exception:
            logger.exception("Failed to process bounce event in batch")
            failed += 1

    return {"processed": processed, "failed": failed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO-8601 timestamp string, falling back to now on failure."""
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)
