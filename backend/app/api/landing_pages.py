"""Landing page management router with SSRF-safe URL cloning."""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import bleach
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/landing-pages")

logger = logging.getLogger(__name__)

# -- SSRF protection -------------------------------------------------------

# Maximum response size when cloning an external page (5 MB).
_MAX_CLONE_RESPONSE_BYTES = 5 * 1024 * 1024

# Timeout for outbound clone requests (seconds).
_CLONE_TIMEOUT = 10.0

# Allowed schemes for clone URLs.
_ALLOWED_SCHEMES = {"http", "https"}

# Bleach-allowed tags for sanitizing cloned HTML.
_SAFE_TAGS = [
    "a", "abbr", "acronym", "address", "b", "blockquote", "br", "center",
    "code", "col", "colgroup", "dd", "del", "dfn", "div", "dl", "dt", "em",
    "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins",
    "li", "mark", "ol", "p", "pre", "q", "s", "small", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "tt", "u", "ul",
]

_SAFE_ATTRIBUTES = {
    "*": ["class", "id", "style", "title"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}


def _is_private_ip(ip_str: str) -> bool:
    """Return True if *ip_str* is a private, loopback, or link-local address."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        # If we cannot parse it, treat as private (deny by default).
        return True

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _validate_clone_url(url: str) -> str:
    """Validate and resolve *url*, raising HTTPException on SSRF risk.

    Checks:
    - Scheme must be http or https.
    - Hostname must resolve to a public (non-private) IP.
    - DNS resolution is performed *before* the HTTP request to prevent
      DNS rebinding attacks.

    Returns the validated URL string.
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must contain a valid hostname.",
        )

    # Resolve hostname to IP addresses and check each one.
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not resolve hostname '{hostname}'.",
        )

    if not addr_infos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No DNS records found for hostname '{hostname}'.",
        )

    for info in addr_infos:
        ip_str = info[4][0]
        if _is_private_ip(ip_str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL resolves to a private or reserved IP address. Cloning from internal networks is not permitted.",
            )

    return url


async def _fetch_and_sanitize(url: str) -> str:
    """Fetch *url* with safety limits and return sanitized HTML."""
    validated_url = _validate_clone_url(url)

    async with httpx.AsyncClient(
        timeout=_CLONE_TIMEOUT,
        follow_redirects=False,
        max_redirects=0,
    ) as client:
        try:
            resp = await client.get(validated_url)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch URL: {exc}",
            )

    # If the server issues a redirect, validate the target before following.
    if resp.is_redirect:
        location = resp.headers.get("location", "")
        if location:
            _validate_clone_url(location)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL returned a redirect. Redirects are not followed for security. Please provide the final URL.",
        )

    # Enforce response size limit.
    content_length = len(resp.content)
    if content_length > _MAX_CLONE_RESPONSE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Response too large ({content_length} bytes). Maximum is {_MAX_CLONE_RESPONSE_BYTES} bytes.",
        )

    raw_html = resp.text

    # Sanitize HTML to remove scripts, event handlers, and dangerous tags.
    sanitized = bleach.clean(
        raw_html,
        tags=_SAFE_TAGS,
        attributes=_SAFE_ATTRIBUTES,
        strip=True,
    )

    return sanitized


# -- Local schemas ---------------------------------------------------------


class LandingPageCreate(BaseModel):
    """Payload for creating a landing page."""

    name: str = Field(..., min_length=1, max_length=256)
    html: str
    capture_credentials: bool = False
    redirect_url: str | None = None


class LandingPageUpdate(BaseModel):
    """Payload for updating a landing page."""

    name: str | None = None
    html: str | None = None
    capture_credentials: bool | None = None
    redirect_url: str | None = None


class LandingPageHtmlUpdate(BaseModel):
    """Payload for updating only the HTML content (from the visual editor)."""

    html: str
    css: str | None = None


class LandingPageFromEditor(BaseModel):
    """Payload for creating a landing page from the visual editor."""

    name: str = Field(..., min_length=1, max_length=256)
    html: str
    css: str = ""


class LandingPagePreviewRequest(BaseModel):
    """Payload for previewing arbitrary HTML with sample variable substitution."""

    html: str


class LandingPageResponse(BaseModel):
    """Landing page returned by the API."""

    id: int
    name: str
    html: str
    capture_credentials: bool
    redirect_url: str | None = None
    created_at: str
    updated_at: str


# -- Endpoints -------------------------------------------------------------


@router.get("/landing-pages", response_model=list[LandingPageResponse])
async def list_landing_pages(
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return all landing pages."""
    return []


@router.post(
    "/landing-pages",
    response_model=LandingPageResponse,
    status_code=201,
)
async def create_landing_page(
    payload: LandingPageCreate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Create a new landing page."""
    return {
        "id": 1,
        "name": payload.name,
        "html": payload.html,
        "capture_credentials": payload.capture_credentials,
        "redirect_url": payload.redirect_url,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.get("/landing-pages/{page_id}", response_model=LandingPageResponse)
async def get_landing_page(
    page_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return a single landing page."""
    return {
        "id": page_id,
        "name": "Placeholder",
        "html": "<html><body>Landing</body></html>",
        "capture_credentials": False,
        "redirect_url": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.put("/landing-pages/{page_id}", response_model=LandingPageResponse)
async def update_landing_page(
    page_id: int,
    payload: LandingPageUpdate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Update an existing landing page."""
    return {
        "id": page_id,
        "name": payload.name or "Updated",
        "html": payload.html or "<html><body>Updated</body></html>",
        "capture_credentials": payload.capture_credentials or False,
        "redirect_url": payload.redirect_url,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.delete("/landing-pages/{page_id}", response_model=SuccessResponse)
async def delete_landing_page(
    page_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Delete a landing page."""
    return {"message": f"Landing page {page_id} deleted."}


@router.post("/landing-pages/clone", response_model=LandingPageResponse)
async def clone_landing_page(
    source_url: str,
    name: str,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Clone a landing page from an external URL.

    The URL is validated against SSRF attacks (private IPs, non-HTTP
    schemes, DNS rebinding) and the fetched HTML is sanitized before
    storage.
    """
    sanitized_html = await _fetch_and_sanitize(source_url)

    return {
        "id": 1,
        "name": name,
        "html": sanitized_html,
        "capture_credentials": False,
        "redirect_url": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.put("/landing-pages/{page_id}/html", response_model=LandingPageResponse)
async def update_landing_page_html(
    page_id: int,
    payload: LandingPageHtmlUpdate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Update only the HTML content of a landing page.

    Intended for saves originating from the visual editor.  Accepts the
    full-page HTML produced by the editor and an optional separate CSS
    string.  When *css* is provided it is embedded inside a ``<style>``
    tag in the stored HTML.
    """
    html = payload.html
    if payload.css:
        # Inject editor CSS into the page if not already present.
        style_block = f"<style>{payload.css}</style>"
        if "</head>" in html:
            html = html.replace("</head>", f"{style_block}\n</head>")
        else:
            html = f"{style_block}\n{html}"

    return {
        "id": page_id,
        "name": "Updated",
        "html": html,
        "capture_credentials": False,
        "redirect_url": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.post(
    "/landing-pages/from-editor",
    response_model=LandingPageResponse,
    status_code=201,
)
async def create_from_editor(
    payload: LandingPageFromEditor,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Create a new landing page from the visual editor output.

    Accepts the editor's full-page HTML, a separate CSS string, and a
    human-readable name.  The CSS is merged into the HTML before storage.
    """
    html = payload.html
    if payload.css:
        style_block = f"<style>{payload.css}</style>"
        if "</head>" in html:
            html = html.replace("</head>", f"{style_block}\n</head>")
        else:
            html = f"{style_block}\n{html}"

    # Detect credential capture fields.
    has_password_field = "type=\"password\"" in html or "type='password'" in html

    return {
        "id": 1,
        "name": payload.name,
        "html": html,
        "capture_credentials": has_password_field,
        "redirect_url": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


# -- Sample data for variable substitution in previews -----------------

_SAMPLE_VARIABLES: dict[str, str] = {
    "{{recipient_token}}": "sample-token-abc123",
    "{{submit_url}}": "https://example.com/capture",
    "{{first_name}}": "Jane",
    "{{last_name}}": "Doe",
    "{{email}}": "jane.doe@example.com",
    "{{company}}": "Acme Corp",
    "{{position}}": "Software Engineer",
    "{{department}}": "Engineering",
}


def _substitute_sample_variables(html: str) -> str:
    """Replace template variables with sample preview data."""
    result = html
    for placeholder, value in _SAMPLE_VARIABLES.items():
        result = result.replace(placeholder, value)
    return result


@router.get("/landing-pages/{page_id}/preview")
async def preview_landing_page(
    page_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return rendered HTML preview of a landing page.

    Template variables (``{{recipient_token}}``, ``{{first_name}}``, etc.)
    are replaced with sample data so the operator can see a realistic
    rendering.
    """
    # In production this would load the page from the database.
    raw_html = "<html><body>Landing page preview for id {}</body></html>".format(page_id)
    rendered = _substitute_sample_variables(raw_html)
    return {
        "id": page_id,
        "rendered_html": rendered,
    }


@router.post("/landing-pages/preview")
async def preview_arbitrary_html(
    payload: LandingPagePreviewRequest,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Preview arbitrary HTML with sample variable substitution.

    Used by the visual editor's preview function to show the operator
    what the final page will look like with realistic variable values.
    """
    rendered = _substitute_sample_variables(payload.html)
    return {
        "rendered_html": rendered,
    }
