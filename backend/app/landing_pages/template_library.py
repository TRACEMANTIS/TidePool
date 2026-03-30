"""Built-in landing page template library for phishing simulations.

Provides a registry of pre-built credential capture templates and a
Jinja2-based rendering engine that substitutes campaign-specific
variables (submit URL, recipient token, company name, etc.) at serve
time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateNotFound

logger = logging.getLogger(__name__)

# Templates live at the project root, outside the backend package.
# Resolve relative to this file:  backend/app/landing_pages/ -> project root
TEMPLATE_DIR: Path = Path(__file__).resolve().parents[3] / "landing_page_templates"


# ---------------------------------------------------------------------------
# Template metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class TemplateMeta:
    """Metadata for a single built-in landing page template."""

    id: str
    name: str
    description: str
    category: str
    variables: list[str] = field(default_factory=list)
    filename: str = ""  # relative to TEMPLATE_DIR


# Built-in template registry.
_REGISTRY: dict[str, TemplateMeta] = {
    "o365_login": TemplateMeta(
        id="o365_login",
        name="Microsoft 365 Login",
        description="Realistic Microsoft 365 sign-in page with two-step email/password flow.",
        category="cloud",
        variables=["submit_url", "recipient_token"],
        filename="o365_login.html",
    ),
    "google_login": TemplateMeta(
        id="google_login",
        name="Google Sign-In",
        description="Google account sign-in page with email and password steps.",
        category="cloud",
        variables=["submit_url", "recipient_token"],
        filename="google_login.html",
    ),
    "okta_login": TemplateMeta(
        id="okta_login",
        name="Okta SSO Portal",
        description="Generic Okta-style SSO login portal with company branding.",
        category="sso",
        variables=["submit_url", "recipient_token", "company_name"],
        filename="okta_login.html",
    ),
    "vpn_login": TemplateMeta(
        id="vpn_login",
        name="VPN Portal",
        description="Corporate VPN login page with realm selector.",
        category="network",
        variables=["submit_url", "recipient_token", "company_name"],
        filename="vpn_login.html",
    ),
    "generic_login": TemplateMeta(
        id="generic_login",
        name="Generic Corporate Login",
        description="Clean, minimal corporate login page with customizable branding.",
        category="general",
        variables=["submit_url", "recipient_token", "company_name", "company_logo_url"],
        filename="generic_login.html",
    ),
}


# ---------------------------------------------------------------------------
# Jinja2 loader that reads from TEMPLATE_DIR
# ---------------------------------------------------------------------------

class _TemplateFileLoader(BaseLoader):
    """Jinja2 loader that reads HTML files from *TEMPLATE_DIR*."""

    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str, callable]:
        path = TEMPLATE_DIR / template
        if not path.is_file():
            raise TemplateNotFound(template)
        source = path.read_text(encoding="utf-8")
        mtime = path.stat().st_mtime
        return source, str(path), lambda: path.stat().st_mtime == mtime


# Shared Jinja2 environment -- undefined variables render as empty strings
# to avoid blowing up if optional variables are omitted.
_jinja_env = Environment(
    loader=_TemplateFileLoader(),
    autoescape=False,  # HTML templates are pre-authored; no auto-escaping.
    keep_trailing_newline=True,
    undefined=__import__("jinja2").Undefined,
)


# ---------------------------------------------------------------------------
# TemplateLibrary
# ---------------------------------------------------------------------------

class TemplateLibrary:
    """Manages built-in landing page templates.

    Usage::

        lib = TemplateLibrary()
        templates = lib.list_templates()
        html = lib.render_template("o365_login", {
            "submit_url": "https://phish.example.com/api/v1/t/s/42.abc",
            "recipient_token": "abc123...",
        })
    """

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or TEMPLATE_DIR

    # -- Public API --------------------------------------------------------

    def list_templates(self) -> list[dict[str, Any]]:
        """Return metadata for all registered templates.

        Each item contains: id, name, description, category, variables,
        and preview_thumbnail_exists (True if a .png thumbnail is on disk).
        """
        result: list[dict[str, Any]] = []
        for meta in _REGISTRY.values():
            thumb_path = self._template_dir / f"{meta.id}_thumb.png"
            result.append({
                "id": meta.id,
                "name": meta.name,
                "description": meta.description,
                "category": meta.category,
                "variables": list(meta.variables),
                "preview_thumbnail_exists": thumb_path.is_file(),
            })
        return result

    def get_template(self, template_id: str) -> str:
        """Return the raw (un-rendered) HTML for *template_id*.

        Raises ``KeyError`` if the template ID is not registered.
        Raises ``FileNotFoundError`` if the HTML file is missing from disk.
        """
        meta = self._get_meta(template_id)
        path = self._template_dir / meta.filename
        if not path.is_file():
            raise FileNotFoundError(
                f"Template file not found: {path}"
            )
        return path.read_text(encoding="utf-8")

    def render_template(
        self, template_id: str, variables: dict[str, str]
    ) -> str:
        """Render *template_id* with the given *variables* via Jinja2.

        Raises ``KeyError`` if the template ID is not registered.
        """
        meta = self._get_meta(template_id)
        template = _jinja_env.get_template(meta.filename)
        return template.render(**variables)

    def get_metadata(self, template_id: str) -> TemplateMeta:
        """Return the ``TemplateMeta`` for *template_id*."""
        return self._get_meta(template_id)

    # -- Internal ----------------------------------------------------------

    @staticmethod
    def _get_meta(template_id: str) -> TemplateMeta:
        """Look up template metadata, raising ``KeyError`` on miss."""
        try:
            return _REGISTRY[template_id]
        except KeyError:
            raise KeyError(
                f"Unknown template ID: {template_id!r}. "
                f"Available: {', '.join(sorted(_REGISTRY))}"
            ) from None
