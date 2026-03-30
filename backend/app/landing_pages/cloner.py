"""URL cloner -- fetches an external page and produces a self-contained
landing page template suitable for credential capture simulations.

The cloner:
- Strips all ``<script>`` tags and inline event handlers.
- Rewrites relative URLs to absolute.
- Base64-encodes small images (< 500 KB) as data URIs.
- Rewrites every ``<form>`` action to the ``{{submit_url}}`` placeholder.
- Injects a hidden ``recipient_token`` field into every form.

SSRF protections are enforced by the calling layer (the landing_pages
API router validates and resolves URLs before they reach this module).
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger(__name__)

# -- Constants ----------------------------------------------------------------

# Maximum page size to download (5 MB).
MAX_PAGE_SIZE: int = 5 * 1024 * 1024

# Maximum individual asset size to inline (500 KB).
MAX_ASSET_SIZE: int = 500 * 1024

# HTTP timeout for all outbound requests (seconds).
REQUEST_TIMEOUT: float = 10.0

# Inline event-handler attributes to strip.
_EVENT_ATTRS: set[str] = {
    "onabort", "onblur", "onchange", "onclick", "ondblclick",
    "onerror", "onfocus", "onhashchange", "oninput", "onkeydown",
    "onkeypress", "onkeyup", "onload", "onmousedown", "onmousemove",
    "onmouseout", "onmouseover", "onmouseup", "onpageshow",
    "onpagehide", "onpopstate", "onresize", "onscroll", "onselect",
    "onsubmit", "onunload", "onbeforeunload", "oncontextmenu",
    "ondrag", "ondragend", "ondragenter", "ondragleave", "ondragover",
    "ondragstart", "ondrop", "ontouchstart", "ontouchmove",
    "ontouchend", "ontouchcancel", "onanimationstart", "onanimationend",
    "onanimationiteration", "ontransitionend",
}

# Image MIME types we are willing to inline.
_INLINEABLE_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
}


# -- PageCloner ---------------------------------------------------------------

class PageCloner:
    """Fetches an external URL and produces sanitized, self-contained HTML
    ready for use as a phishing simulation landing page.

    Usage::

        cloner = PageCloner()
        result = await cloner.clone("https://example.com/login")
        # result == {"html": "...", "title": "...", "assets": [...]}
    """

    def __init__(
        self,
        timeout: float = REQUEST_TIMEOUT,
        max_page_size: int = MAX_PAGE_SIZE,
        max_asset_size: int = MAX_ASSET_SIZE,
    ) -> None:
        self._timeout = timeout
        self._max_page_size = max_page_size
        self._max_asset_size = max_asset_size

    async def clone(self, url: str) -> dict[str, Any]:
        """Clone the page at *url* and return a result dict.

        Returns::

            {
                "html": "<rendered self-contained HTML>",
                "title": "Page Title",
                "assets": ["https://example.com/logo.png", ...]
            }

        Raises ``httpx.HTTPError`` on network failure and ``ValueError``
        if the response exceeds *max_page_size*.
        """
        html, base_url = await self._fetch_page(url)
        soup = BeautifulSoup(html, "lxml")

        title = self._extract_title(soup)
        self._strip_scripts(soup)
        self._strip_event_handlers(soup)
        self._strip_comments(soup)
        self._absolutize_urls(soup, base_url)
        assets = await self._inline_images(soup)
        self._rewrite_forms(soup)

        rendered = str(soup)
        return {
            "html": rendered,
            "title": title,
            "assets": assets,
        }

    # -- Internal helpers -----------------------------------------------------

    async def _fetch_page(self, url: str) -> tuple[str, str]:
        """Fetch *url* and return (html_text, effective_base_url)."""
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=3,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        if len(resp.content) > self._max_page_size:
            raise ValueError(
                f"Page size ({len(resp.content)} bytes) exceeds "
                f"maximum ({self._max_page_size} bytes)."
            )

        return resp.text, str(resp.url)

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        """Extract the ``<title>`` text, or return an empty string."""
        tag = soup.find("title")
        if tag and tag.string:
            return tag.string.strip()
        return ""

    @staticmethod
    def _strip_scripts(soup: BeautifulSoup) -> None:
        """Remove all ``<script>`` and ``<noscript>`` elements."""
        for tag in soup.find_all(["script", "noscript"]):
            tag.decompose()

    @staticmethod
    def _strip_event_handlers(soup: BeautifulSoup) -> None:
        """Remove all inline event-handler attributes from every element."""
        for tag in soup.find_all(True):
            if not isinstance(tag, Tag):
                continue
            attrs_to_remove = [
                attr for attr in tag.attrs
                if attr.lower() in _EVENT_ATTRS
                or attr.lower().startswith("on")
            ]
            for attr in attrs_to_remove:
                del tag[attr]

    @staticmethod
    def _strip_comments(soup: BeautifulSoup) -> None:
        """Remove HTML comments (may contain sensitive info)."""
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    @staticmethod
    def _absolutize_urls(soup: BeautifulSoup, base_url: str) -> None:
        """Rewrite relative href/src/action attributes to absolute URLs."""
        for attr in ("href", "src", "action"):
            for tag in soup.find_all(True, attrs={attr: True}):
                value = tag[attr]
                if not value or value.startswith(("data:", "mailto:", "#", "javascript:")):
                    continue
                if not urlparse(value).scheme:
                    tag[attr] = urljoin(base_url, value)

    async def _inline_images(self, soup: BeautifulSoup) -> list[str]:
        """Download images and inline them as base64 data URIs.

        Returns a list of original image URLs that were processed.
        """
        inlined: list[str] = []
        img_tags = soup.find_all("img", src=True)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=3,
        ) as client:
            for img in img_tags:
                src = img["src"]
                if src.startswith("data:"):
                    continue

                ext = self._get_extension(src)
                mime = _INLINEABLE_TYPES.get(ext)
                if not mime:
                    continue

                try:
                    resp = await client.get(src)
                    resp.raise_for_status()
                except (httpx.HTTPError, httpx.InvalidURL):
                    logger.debug("Failed to fetch image: %s", src)
                    continue

                if len(resp.content) > self._max_asset_size:
                    logger.debug(
                        "Image too large to inline (%d bytes): %s",
                        len(resp.content), src,
                    )
                    continue

                # Use content-type from response if available.
                ct = resp.headers.get("content-type", "").split(";")[0].strip()
                if ct in _INLINEABLE_TYPES.values():
                    mime = ct

                b64 = base64.b64encode(resp.content).decode("ascii")
                img["src"] = f"data:{mime};base64,{b64}"
                inlined.append(src)

        return inlined

    @staticmethod
    def _get_extension(url: str) -> str:
        """Extract the lowercase file extension from a URL path."""
        path = urlparse(url).path
        dot_idx = path.rfind(".")
        if dot_idx == -1:
            return ""
        ext = path[dot_idx:].lower()
        # Strip query fragments that might be appended.
        for ch in ("?", "#", "&"):
            idx = ext.find(ch)
            if idx != -1:
                ext = ext[:idx]
        return ext

    @staticmethod
    def _rewrite_forms(soup: BeautifulSoup) -> None:
        """Rewrite all ``<form>`` actions to ``{{submit_url}}`` and inject
        a hidden ``recipient_token`` field.
        """
        for form in soup.find_all("form"):
            form["action"] = "{{ submit_url }}"
            form["method"] = "POST"

            # Check whether a recipient_token field already exists.
            existing = form.find(
                "input", attrs={"name": "recipient_token"}
            )
            if not existing:
                hidden = soup.new_tag(
                    "input",
                    type="hidden",
                    attrs={"name": "recipient_token", "value": "{{ recipient_token }}"},
                )
                form.insert(0, hidden)
