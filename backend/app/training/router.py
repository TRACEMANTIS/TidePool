"""Training redirect router -- thin redirect layer for post-phish training.

TidePool does not host training content. Instead, administrators configure
an external training URL on each campaign (KnowBe4, internal LMS,
SharePoint page, etc.). This router:

1. Redirects phished recipients to that external URL.
2. Logs that the redirect occurred (for compliance reporting).
3. Optionally shows a brief interstitial before redirecting if
   ``training_redirect_delay_seconds`` is set on the campaign.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.campaign import Campaign
from app.training.models import TrainingRedirect
from app.training.schemas import TrainingRedirectListResponse, TrainingRedirectResponse

router = APIRouter(prefix="/training")


def _interstitial_html(redirect_url: str, delay_seconds: int) -> str:
    """Build a minimal interstitial page that redirects after a delay."""
    # HTML-escape the URL for safe embedding in the page.
    safe_url = (
        redirect_url
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Security Awareness</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#f0f4f8;color:#1a2a3a;margin:0;padding:0;display:flex;
align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);
padding:2.5rem;max-width:520px;text-align:center}}
h1{{font-size:1.5rem;margin-bottom:1rem;color:#1a5276}}
p{{color:#4a6a8a;line-height:1.6}}
.countdown{{font-size:2rem;font-weight:700;color:#2e86c1;margin:1.5rem 0}}
a{{color:#2e86c1}}
</style>
</head>
<body>
<div class="card">
<h1>This was a simulated phishing test</h1>
<p>You will be redirected to your organization's security training in:</p>
<div class="countdown" id="timer">{delay_seconds}</div>
<p><a href="{safe_url}" id="link">Click here if you are not redirected automatically</a></p>
</div>
<script>
(function(){{
var s={delay_seconds},el=document.getElementById("timer");
var iv=setInterval(function(){{
s--;el.textContent=s;
if(s<=0){{clearInterval(iv);window.location.href="{safe_url}";}}
}},1000);
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public endpoint -- redirect phished recipients to training
# ---------------------------------------------------------------------------


@router.get("/redirect/{campaign_id}/{recipient_token}")
async def training_redirect(
    campaign_id: int,
    recipient_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Redirect a phished recipient to the campaign's external training URL.

    This is a public endpoint -- no authentication required.  The
    campaign_id and recipient_token pair identifies the recipient.

    If the campaign has a ``training_redirect_delay_seconds`` value
    greater than zero, an interstitial page is shown first with a
    countdown timer before the redirect occurs.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or not campaign.training_redirect_url:
        return HTMLResponse(
            content=(
                "<!DOCTYPE html><html><head><title>Training</title></head>"
                "<body><p>No training redirect is configured for this campaign.</p>"
                "</body></html>"
            ),
            status_code=200,
        )

    # Record the redirect for compliance reporting.
    redirect_record = TrainingRedirect(
        campaign_id=campaign_id,
        recipient_token=recipient_token,
        redirected_at=datetime.now(timezone.utc),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(redirect_record)
    await db.flush()
    await db.commit()

    # If a delay is configured, show an interstitial page.
    delay = campaign.training_redirect_delay_seconds
    if delay and delay > 0:
        html = _interstitial_html(campaign.training_redirect_url, delay)
        return HTMLResponse(content=html, status_code=200)

    # Immediate redirect.
    return RedirectResponse(
        url=campaign.training_redirect_url,
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Admin endpoint -- compliance reporting
# ---------------------------------------------------------------------------


@router.get(
    "/completions/{campaign_id}",
    response_model=TrainingRedirectListResponse,
)
async def list_completions(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_admin),
) -> TrainingRedirectListResponse:
    """Return all recipients who were redirected to training for a campaign.

    Admin-only endpoint for compliance reporting.
    """
    result = await db.execute(
        select(TrainingRedirect)
        .where(TrainingRedirect.campaign_id == campaign_id)
        .order_by(TrainingRedirect.redirected_at)
    )
    redirects = list(result.scalars().all())

    count_result = await db.execute(
        select(func.count())
        .select_from(TrainingRedirect)
        .where(TrainingRedirect.campaign_id == campaign_id)
    )
    total = count_result.scalar_one()

    items = [
        TrainingRedirectResponse(
            id=r.id,
            campaign_id=r.campaign_id,
            recipient_token=r.recipient_token,
            redirected_at=r.redirected_at,
        )
        for r in redirects
    ]

    return TrainingRedirectListResponse(items=items, total=total)
