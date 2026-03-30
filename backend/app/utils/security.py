"""Password hashing, JWT token utilities, and API key management."""

import re
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


# -- Password utilities -------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def validate_password_complexity(password: str) -> list[str]:
    """Check that a password meets complexity requirements.

    Requirements:
        - Minimum 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character

    Returns:
        A list of failure reasons (empty list means the password is valid).
    """
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Password must be at least 12 characters long.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("Password must contain at least one special character.")
    return errors


# -- JWT utilities -------------------------------------------------------------


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token (short-lived, default 15 min)."""
    to_encode = data.copy()
    to_encode["type"] = "access"
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT refresh token (long-lived, default 7 days)."""
    to_encode = data.copy()
    to_encode["type"] = "refresh"
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token.

    Returns the payload dict or None on any failure (expired, invalid,
    malformed, wrong token type).
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        if payload.get("sub") is None:
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    """Decode and validate a JWT refresh token.

    Returns the payload dict or None on any failure.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        if payload.get("sub") is None:
            return None
        return payload
    except JWTError:
        return None


# -- API key utilities ---------------------------------------------------------


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        A tuple of (raw_key, key_hash, key_prefix).
        - raw_key: the full plaintext key (shown once to the user)
        - key_hash: bcrypt hash for storage
        - key_prefix: first 8 characters for identification
    """
    raw_key = "tp_" + secrets.token_urlsafe(48)
    key_hash = pwd_context.hash(raw_key)
    key_prefix = raw_key[:11]  # "tp_" + first 8 chars of the token portion
    return raw_key, key_hash, key_prefix


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify a raw API key against its stored bcrypt hash.

    Uses bcrypt's built-in constant-time comparison.
    """
    try:
        return pwd_context.verify(raw_key, key_hash)
    except Exception:
        return False
