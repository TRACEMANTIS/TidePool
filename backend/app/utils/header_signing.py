"""HMAC signing for X-TidePool-Campaign-ID headers.

Signs campaign IDs with HMAC-SHA256 so that downstream mail security gateways
(Mimecast, Defender, etc.) can verify that the header was injected
by TidePool rather than forged.
"""

from __future__ import annotations

import hashlib
import hmac


def _get_secret() -> str:
    """Retrieve the header signing secret from application settings."""
    from app.config import settings
    return settings.TIDEPOOL_HEADER_SECRET


def sign_campaign_id(campaign_id: int | str) -> str:
    """Sign a campaign ID with HMAC-SHA256.

    Returns ``'{campaign_id}:{hmac_hex}'`` if a secret is configured,
    or just ``'{campaign_id}'`` if the secret is empty.
    """
    secret = _get_secret()
    cid = str(campaign_id)

    if not secret:
        return cid

    signature = hmac.new(
        secret.encode(),
        cid.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{cid}:{signature}"


def verify_campaign_header(header_value: str) -> tuple[str, bool]:
    """Parse and verify a signed header value.

    Returns ``(campaign_id, is_valid)``.  If the secret is not
    configured, all values are treated as valid (signature check
    is skipped).
    """
    secret = _get_secret()

    if ":" not in header_value:
        # Unsigned value -- valid only when no secret is configured.
        return header_value, not bool(secret)

    cid, provided_sig = header_value.rsplit(":", 1)

    if not secret:
        # No secret configured; cannot verify, but the ID is parseable.
        return cid, True

    expected_sig = hmac.new(
        secret.encode(),
        cid.encode(),
        hashlib.sha256,
    ).hexdigest()

    return cid, hmac.compare_digest(provided_sig, expected_sig)
