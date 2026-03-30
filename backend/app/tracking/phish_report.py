"""Phish report button integration.

Provides endpoints for recipients who correctly identify a simulated phishing
email and click the "Report Phish" button.  This tracks the *positive*
behaviour of users who report suspicious messages.
"""

from __future__ import annotations

import logging
import re

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.tracking.realtime import RealtimeTracker
from app.tracking.recorder import EventRecorder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/t")

# Reuse the same token-validation pattern from the main tracking module.
_COMPOSITE_PATTERN = re.compile(r"^(\d+)\.([A-Za-z0-9_-]{32,64})$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")

_REPORT_THANK_YOU_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Report Received</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#f0f4f8;color:#1a2a3a;margin:0;padding:0;display:flex;
align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);
padding:2.5rem;max-width:480px;text-align:center}
h1{font-size:1.5rem;margin-bottom:1rem;color:#1a5276}
p{color:#4a6a8a;line-height:1.6}
</style>
</head>
<body>
<div class="card">
<h1>Thank You</h1>
<p>Thank you for reporting this suspicious email. Your vigilance helps keep the organisation secure.</p>
</div>
</body>
</html>"""


def _validate_tracking_id(tracking_id: str) -> bool:
    """Return True if *tracking_id* matches an accepted token format."""
    return bool(_TOKEN_PATTERN.match(tracking_id)) or bool(
        _COMPOSITE_PATTERN.match(tracking_id)
    )


def _parse_tracking_id(tracking_id: str) -> tuple[int | None, str]:
    """Extract campaign_id and recipient token from a tracking_id."""
    m = _COMPOSITE_PATTERN.match(tracking_id)
    if m:
        return int(m.group(1)), m.group(2)
    return None, tracking_id


def _get_redis() -> aioredis.Redis:
    """Create an async Redis client from application settings."""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@router.post("/report/{tracking_id}")
async def report_phish(
    tracking_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Record that a user reported the simulated phishing email.

    Returns a consistent response regardless of token validity to prevent
    enumeration.
    """
    if not _validate_tracking_id(tracking_id):
        return HTMLResponse(content=_REPORT_THANK_YOU_HTML, status_code=200)

    campaign_id, token = _parse_tracking_id(tracking_id)
    if campaign_id is None:
        return HTMLResponse(content=_REPORT_THANK_YOU_HTML, status_code=200)

    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    metadata = {"user_agent": ua, "ip_address": ip}

    try:
        redis_client = _get_redis()
        rt = RealtimeTracker(redis_client)
        recorder = EventRecorder(rt)
        await recorder.record_report(campaign_id, token, metadata, db)
    except Exception:
        logger.exception("Failed to record phish report for %s (non-fatal)", tracking_id)
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass

    return HTMLResponse(content=_REPORT_THANK_YOU_HTML, status_code=200)


@router.get("/report-button/{tracking_id}")
async def report_button_page(tracking_id: str) -> HTMLResponse:
    """Return a small HTML page confirming that the report was received.

    This endpoint is intended for email clients that open links in a
    preview pane. It shows a simple confirmation message without
    recording a new event (the POST endpoint handles recording).
    """
    return HTMLResponse(content=_REPORT_THANK_YOU_HTML, status_code=200)
