"""Tracking injection -- pixel insertion and link rewriting for email HTML."""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URL generators
# ---------------------------------------------------------------------------

def generate_pixel_url(base_url: str, campaign_id: int, recipient_token: str) -> str:
    """Build the full URL for the 1x1 tracking pixel.

    The resulting URL points to the open-tracking endpoint::

        {base_url}/api/v1/t/o/{recipient_token}

    The campaign_id is not strictly required in the URL because the token
    already maps to a unique (campaign, contact) pair, but we include it as
    a query parameter for fast server-side lookup without a DB round-trip.
    """
    base = base_url.rstrip("/")
    return f"{base}/api/v1/t/o/{recipient_token}?cid={campaign_id}"


def generate_click_url(
    base_url: str,
    recipient_token: str,
    original_url: str,
) -> str:
    """Build a click-tracking redirect URL.

    Returns::

        {base_url}/api/v1/t/c/{recipient_token}?url={percent_encoded_original}
    """
    base = base_url.rstrip("/")
    params = urlencode({"url": original_url})
    return f"{base}/api/v1/t/c/{recipient_token}?{params}"


# ---------------------------------------------------------------------------
# Tracking pixel injection
# ---------------------------------------------------------------------------

def inject_tracking_pixel(html: str, pixel_url: str) -> str:
    """Insert a 1x1 transparent tracking pixel image just before ``</body>``.

    If the HTML does not contain a ``</body>`` tag the pixel is appended to
    the end of the document.
    """
    pixel_tag = (
        f'<img src="{pixel_url}" width="1" height="1" '
        f'alt="" style="display:none;border:0;" />'
    )

    # Case-insensitive search for </body>.
    lower = html.lower()
    idx = lower.rfind("</body>")
    if idx != -1:
        return html[:idx] + pixel_tag + html[idx:]
    # No closing body tag -- append.
    return html + pixel_tag


# ---------------------------------------------------------------------------
# Link rewriting
# ---------------------------------------------------------------------------

class _LinkRewriter(HTMLParser):
    """HTML parser that rewrites ``<a href="...">`` attributes to pass
    through the click-tracking redirect endpoint.

    All other tags and content are emitted unchanged.
    """

    def __init__(self, redirect_base_url: str, recipient_token: str) -> None:
        super().__init__(convert_charrefs=False)
        self.redirect_base_url = redirect_base_url.rstrip("/")
        self.recipient_token = recipient_token
        self._parts: list[str] = []

    # -- HTMLParser callbacks ------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs = self._rewrite_href(attrs)
        self._parts.append(self._rebuild_tag(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs = self._rewrite_href(attrs)
        self._parts.append(self._rebuild_tag(tag, attrs, self_closing=True))

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._parts.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._parts.append(f"<![{data}]>")

    # -- Helpers -------------------------------------------------------------

    def _rewrite_href(
        self, attrs: list[tuple[str, str | None]],
    ) -> list[tuple[str, str | None]]:
        """Replace the ``href`` value with a click-tracking redirect URL."""
        new_attrs: list[tuple[str, str | None]] = []
        for name, value in attrs:
            if name == "href" and value and not self._is_special_href(value):
                tracked = (
                    f"{self.redirect_base_url}/{self.recipient_token}"
                    f"?url={quote(value, safe='')}"
                )
                new_attrs.append((name, tracked))
            else:
                new_attrs.append((name, value))
        return new_attrs

    @staticmethod
    def _is_special_href(href: str) -> bool:
        """Return True for mailto:, tel:, and anchor-only links."""
        lower = href.strip().lower()
        return lower.startswith(("mailto:", "tel:", "#", "javascript:"))

    @staticmethod
    def _rebuild_tag(
        tag: str,
        attrs: list[tuple[str, str | None]],
        self_closing: bool = False,
    ) -> str:
        parts = [tag]
        for name, value in attrs:
            if value is None:
                parts.append(name)
            else:
                parts.append(f'{name}="{value}"')
        close = " /" if self_closing else ""
        return "<" + " ".join(parts) + close + ">"

    def get_result(self) -> str:
        return "".join(self._parts)


def rewrite_links(
    html: str,
    redirect_base_url: str,
    recipient_token: str,
) -> str:
    """Rewrite all ``<a href="...">`` links in *html* to route through the
    click-tracking endpoint.

    Parameters
    ----------
    html:
        The HTML body of the email.
    redirect_base_url:
        Base URL for the click-tracking endpoint, e.g.
        ``https://phish.example.com/api/v1/t/c``.
    recipient_token:
        The unique token for this campaign recipient.

    Returns
    -------
    str
        The HTML with all non-special links rewritten.
    """
    try:
        rewriter = _LinkRewriter(redirect_base_url, recipient_token)
        rewriter.feed(html)
        rewriter.close()
        return rewriter.get_result()
    except Exception:
        logger.exception("Link rewriting failed; returning original HTML")
        return html
