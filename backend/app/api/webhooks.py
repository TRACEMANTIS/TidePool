"""Webhook receiver router for bounce/complaint notifications from SMTP providers.

All webhook endpoints are unauthenticated -- they rely on provider-specific
signature verification instead.  Payloads are validated and then dispatched
to Celery tasks for async processing so that we return 200 quickly.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import settings
from app.engine.bounce_handler import (
    BounceType,
    MailgunBounceProcessor,
    SESBounceProcessor,
    SendGridBounceProcessor,
    process_bounce_notification,
    process_bounce_batch,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Rate limit: reuse the app-level limiter.  Webhook endpoints get a generous
# limit because providers may send bursts.
_WEBHOOK_RATE_LIMIT = "500/minute"


# ---------------------------------------------------------------------------
# AWS SES (via SNS)
# ---------------------------------------------------------------------------

@router.post("/ses", status_code=200)
async def ses_webhook(request: Request) -> dict:
    """Receive AWS SES bounce/complaint notifications via SNS.

    Handles:
    - SubscriptionConfirmation: auto-confirms by visiting the SubscribeURL.
    - Notification: parses the bounce/complaint and enqueues processing.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # -- Verify SNS signature -------------------------------------------------
    if not await _verify_sns_signature(payload):
        logger.warning("SNS signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid SNS signature.")

    msg_type = payload.get("Type", "")

    # -- SubscriptionConfirmation: auto-confirm -------------------------------
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = payload.get("SubscribeURL", "")
        if subscribe_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(subscribe_url)
                    logger.info(
                        "SNS subscription confirmed (status %d)", resp.status_code,
                    )
            except Exception:
                logger.exception("Failed to confirm SNS subscription")
        return {"status": "subscription_confirmed"}

    # -- Notification: parse and enqueue --------------------------------------
    if msg_type == "Notification":
        processor = SESBounceProcessor()
        event = processor.parse_sns_notification(payload)
        if event is not None:
            process_bounce_notification.delay({
                "recipient_email": event.recipient_email,
                "bounce_type": event.bounce_type.value,
                "bounce_message": event.message,
            })
        return {"status": "accepted"}

    return {"status": "ignored", "type": msg_type}


async def _verify_sns_signature(payload: dict) -> bool:
    """Verify the cryptographic signature of an SNS message.

    In production this should download the signing certificate from the
    SigningCertURL and verify against it.  For now we perform basic
    validation of required fields and trust payloads from known AWS
    endpoints.  A full implementation would use the ``M2Crypto`` or
    ``cryptography`` library.
    """
    signing_cert_url = payload.get("SigningCertURL", "")

    # Reject if the signing cert is not from amazonaws.com.
    if signing_cert_url and "amazonaws.com" not in signing_cert_url:
        return False

    # Basic structural check.
    required_fields = {"Type", "MessageId", "TopicArn"}
    if not required_fields.issubset(payload.keys()):
        return False

    return True


# ---------------------------------------------------------------------------
# Mailgun
# ---------------------------------------------------------------------------

@router.post("/mailgun", status_code=200)
async def mailgun_webhook(request: Request) -> dict:
    """Receive Mailgun event webhooks (bounced, dropped, complained)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # -- Verify Mailgun signature (HMAC-SHA256) --------------------------------
    if not _verify_mailgun_signature(payload):
        logger.warning("Mailgun signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid Mailgun signature.")

    processor = MailgunBounceProcessor()
    event = processor.parse_webhook(payload)

    if event is not None:
        process_bounce_notification.delay({
            "recipient_email": event.recipient_email,
            "bounce_type": event.bounce_type.value,
            "bounce_message": event.message,
        })
        return {"status": "accepted"}

    return {"status": "ignored"}


def _verify_mailgun_signature(payload: dict) -> bool:
    """Verify the Mailgun webhook signature using HMAC-SHA256.

    Mailgun sends ``signature`` object with ``timestamp``, ``token``,
    and ``signature`` fields.
    """
    sig_data = payload.get("signature", {})
    if not sig_data:
        # Legacy format: signature fields at top level.
        sig_data = payload

    timestamp = sig_data.get("timestamp", "")
    token = sig_data.get("token", "")
    signature = sig_data.get("signature", "")

    if not all([timestamp, token, signature]):
        return False

    # Use the app's secret key as the Mailgun API key for HMAC.
    # In production this should be the Mailgun API key stored in config.
    mailgun_key = getattr(settings, "MAILGUN_API_KEY", settings.SECRET_KEY)

    expected = hmac.new(
        mailgun_key.encode("utf-8"),
        f"{timestamp}{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# SendGrid
# ---------------------------------------------------------------------------

@router.post("/sendgrid", status_code=200)
async def sendgrid_webhook(request: Request) -> dict:
    """Receive SendGrid Event Webhook notifications."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # -- Verify SendGrid signature ---------------------------------------------
    body = await request.body()
    signature_header = request.headers.get("X-Twilio-Email-Event-Webhook-Signature", "")
    timestamp_header = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp", "")

    if not _verify_sendgrid_signature(body, signature_header, timestamp_header):
        logger.warning("SendGrid signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid SendGrid signature.")

    if not isinstance(payload, list):
        payload = [payload]

    processor = SendGridBounceProcessor()
    events = processor.parse_webhook(payload)

    if events:
        # Batch process for efficiency.
        batch_data = [
            {
                "recipient_email": e.recipient_email,
                "bounce_type": e.bounce_type.value,
                "bounce_message": e.message,
            }
            for e in events
        ]
        process_bounce_batch.delay(batch_data)
        return {"status": "accepted", "events_queued": len(events)}

    return {"status": "ignored"}


def _verify_sendgrid_signature(
    body: bytes,
    signature: str,
    timestamp: str,
) -> bool:
    """Verify the SendGrid Event Webhook signature.

    SendGrid uses an ECDSA signature with the public key provided in
    the webhook settings.  For a basic implementation we validate that
    the required headers are present.  A full implementation would use
    the ``starkbank-ecdsa`` or ``cryptography`` library to verify
    against the SendGrid verification key.
    """
    if not signature or not timestamp:
        # Allow unsigned payloads in development.
        sendgrid_key = getattr(settings, "SENDGRID_WEBHOOK_KEY", "")
        if not sendgrid_key:
            return True
        return False

    # Structural validation -- real verification requires ECDSA.
    # In production, implement full ECDSA verification here.
    return True
