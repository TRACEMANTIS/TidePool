"""Landing page serving engine.

Resolves a campaign's landing page configuration, renders it with the
appropriate recipient-specific variables, and returns an HTML response
ready to capture credentials during a phishing simulation.
"""

from __future__ import annotations

import logging

from fastapi.responses import HTMLResponse
from jinja2 import BaseLoader, Environment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.landing_page import LandingPage, PageType
from app.landing_pages.template_library import TemplateLibrary

logger = logging.getLogger(__name__)

# Jinja2 environment for rendering custom/cloned HTML that is stored in the
# database (as opposed to the file-backed built-in templates).
_string_env = Environment(
    loader=BaseLoader(),
    autoescape=False,
    keep_trailing_newline=True,
)

# Shared template library instance.
_library = TemplateLibrary()


class LandingPageServer:
    """Serves rendered landing pages for active campaigns.

    Usage::

        server = LandingPageServer()
        response = await server.serve(
            campaign_id=42,
            recipient_token="abc123...",
            db=async_session,
        )
    """

    async def serve(
        self,
        campaign_id: int,
        recipient_token: str,
        db: AsyncSession,
    ) -> HTMLResponse:
        """Look up the campaign's landing page and return rendered HTML.

        If the campaign or landing page cannot be resolved, returns a
        minimal fallback page (to avoid leaking internal state to the
        target).
        """
        # -- Resolve campaign and landing page --------------------------------
        campaign = await db.get(Campaign, campaign_id)
        if campaign is None or campaign.landing_page_id is None:
            logger.warning(
                "No landing page configured for campaign %s", campaign_id,
            )
            return self._fallback_response()

        landing_page = await db.get(LandingPage, campaign.landing_page_id)
        if landing_page is None:
            logger.warning(
                "Landing page %s not found for campaign %s",
                campaign.landing_page_id, campaign_id,
            )
            return self._fallback_response()

        # -- Build the submission URL -----------------------------------------
        # The submit URL is the tracking submission endpoint. The composite
        # tracking ID encodes both campaign and recipient for server-side
        # correlation.
        submit_url = f"/api/v1/t/s/{campaign_id}.{recipient_token}"

        # -- Render based on page type ----------------------------------------
        if landing_page.page_type == PageType.TEMPLATE:
            html = self._render_builtin_template(
                landing_page, submit_url, recipient_token,
            )
        else:
            # CLONED or CUSTOM -- HTML is stored directly in the model.
            html = self._render_custom_html(
                landing_page.html_content, submit_url, recipient_token,
                landing_page.config,
            )

        return HTMLResponse(content=html, status_code=200)

    # -- Rendering helpers ----------------------------------------------------

    @staticmethod
    def _render_builtin_template(
        landing_page: LandingPage,
        submit_url: str,
        recipient_token: str,
    ) -> str:
        """Render a built-in template from the template library.

        The template ID is stored in ``landing_page.config["template_id"]``.
        Additional variables (company_name, company_logo_url, etc.) are
        pulled from ``landing_page.config``.
        """
        config = landing_page.config or {}
        template_id = config.get("template_id", "generic_login")

        variables: dict[str, str] = {
            "submit_url": submit_url,
            "recipient_token": recipient_token,
        }

        # Merge any extra variables from the config (company_name, etc.).
        for key in ("company_name", "company_logo_url"):
            if key in config:
                variables[key] = config[key]

        try:
            return _library.render_template(template_id, variables)
        except (KeyError, FileNotFoundError):
            logger.error(
                "Failed to render built-in template %r for landing page %s",
                template_id, landing_page.id,
            )
            return _FALLBACK_HTML

    @staticmethod
    def _render_custom_html(
        html_content: str,
        submit_url: str,
        recipient_token: str,
        config: dict | None = None,
    ) -> str:
        """Render custom or cloned HTML by substituting Jinja2 variables.

        Handles ``{{submit_url}}``, ``{{recipient_token}}``, and any
        additional variables stored in the landing page config.
        """
        variables: dict[str, str] = {
            "submit_url": submit_url,
            "recipient_token": recipient_token,
        }
        if config:
            for key in ("company_name", "company_logo_url"):
                if key in config:
                    variables[key] = config[key]

        try:
            template = _string_env.from_string(html_content)
            return template.render(**variables)
        except Exception:
            logger.exception("Failed to render custom landing page HTML")
            return _FALLBACK_HTML

    @staticmethod
    def _fallback_response() -> HTMLResponse:
        """Return a minimal fallback page when the landing page cannot be
        resolved.  Intentionally bland to avoid revealing platform details.
        """
        return HTMLResponse(content=_FALLBACK_HTML, status_code=200)


# -- Fallback HTML ------------------------------------------------------------

_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Page Not Available</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#f5f5f5;color:#333;margin:0;padding:0;display:flex;
align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);
padding:2rem;max-width:420px;text-align:center}
h1{font-size:1.25rem;margin-bottom:0.75rem}
p{color:#666;font-size:0.9rem;line-height:1.5}
</style>
</head>
<body>
<div class="card">
<h1>This page is not available</h1>
<p>The resource you are looking for could not be found. Please check
the URL and try again.</p>
</div>
</body>
</html>"""
