"""Email template rendering with Jinja2 variable substitution."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from jinja2 import BaseLoader, Environment, Undefined

from app.engine.tracker import inject_tracking_pixel, rewrite_links, generate_pixel_url

logger = logging.getLogger(__name__)


class _SilentUndefined(Undefined):
    """Return empty string for missing template variables instead of raising."""

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False


_jinja_env = Environment(
    loader=BaseLoader(),
    undefined=_SilentUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


@dataclass(frozen=True)
class RenderedEmail:
    """Container for a fully rendered email."""

    subject: str
    body_html: str
    body_text: str


class EmailRenderer:
    """Render email templates by substituting contact variables via Jinja2.

    Supported built-in variables:
        {{first_name}}, {{last_name}}, {{email}},
        {{department}}, {{title}}, {{company}}

    Any keys present in a contact's ``custom_fields`` JSON column are also
    available as top-level template variables.
    """

    def _build_context(self, contact) -> dict[str, str]:
        """Build the Jinja2 context dict from a Contact ORM object."""
        ctx: dict[str, str] = {
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "email": contact.email or "",
            "department": contact.department or "",
            "title": contact.title or "",
            "company": "",
        }
        # Merge custom_fields so they are accessible as top-level vars.
        if contact.custom_fields and isinstance(contact.custom_fields, dict):
            for key, value in contact.custom_fields.items():
                ctx.setdefault(key, str(value) if value is not None else "")
        return ctx

    def _render_string(self, template_str: str, context: dict[str, str]) -> str:
        """Render a single template string against the given context."""
        try:
            tmpl = _jinja_env.from_string(template_str)
            return tmpl.render(context)
        except Exception:
            logger.exception("Failed to render template string")
            return template_str

    def render(self, template, contact) -> RenderedEmail:
        """Render an EmailTemplate for a specific Contact.

        Parameters
        ----------
        template:
            An ``EmailTemplate`` ORM object with ``subject``, ``body_html``,
            and optionally ``body_text`` attributes.
        contact:
            A ``Contact`` ORM object.

        Returns
        -------
        RenderedEmail
            The rendered subject, HTML body, and plain-text body.
        """
        ctx = self._build_context(contact)

        subject = self._render_string(template.subject, ctx)
        body_html = self._render_string(template.body_html, ctx)
        body_text = self._render_string(template.body_text or "", ctx)

        return RenderedEmail(subject=subject, body_html=body_html, body_text=body_text)

    def render_with_tracking(
        self,
        template,
        contact,
        campaign_id: int,
        recipient_token: str,
        base_url: str,
    ) -> RenderedEmail:
        """Render a template and inject tracking pixel + click-tracked links.

        Parameters
        ----------
        template:
            An ``EmailTemplate`` ORM object.
        contact:
            A ``Contact`` ORM object.
        campaign_id:
            The campaign this email belongs to.
        recipient_token:
            Unique token identifying this recipient (UUID string).
        base_url:
            The public-facing base URL of the TidePool instance
            (e.g. ``https://phish.example.com``).

        Returns
        -------
        RenderedEmail
            Rendered email with tracking pixel appended and all links
            rewritten to pass through the click tracker.
        """
        rendered = self.render(template, contact)

        pixel_url = generate_pixel_url(base_url, campaign_id, recipient_token)
        redirect_base = f"{base_url.rstrip('/')}/api/v1/t/c"

        tracked_html = inject_tracking_pixel(rendered.body_html, pixel_url)
        tracked_html = rewrite_links(tracked_html, redirect_base, recipient_token)

        return RenderedEmail(
            subject=rendered.subject,
            body_html=tracked_html,
            body_text=rendered.body_text,
        )
