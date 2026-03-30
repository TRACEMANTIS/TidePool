"""FastAPI dependencies for authentication and authorization.

Supports two authentication methods:
  1. JWT Bearer token (Authorization: Bearer <jwt>)  -- for web dashboard
  2. API key header  (X-API-Key: <key>)               -- for programmatic access
"""

from __future__ import annotations

import fnmatch
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.utils.security import decode_access_token, verify_api_key

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,  # We handle missing tokens ourselves to support API keys.
)


async def _resolve_jwt_user(
    token: str,
    db: AsyncSession,
) -> User | None:
    """Decode a JWT and load the corresponding User from the database."""
    payload = decode_access_token(token)
    if payload is None:
        return None

    username: str | None = payload.get("sub")
    if username is None:
        return None

    result = await db.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def _resolve_api_key_user(
    raw_key: str,
    db: AsyncSession,
) -> tuple[User | None, ApiKey | None]:
    """Look up an API key, verify it, and return the owning user + key record.

    This iterates over active keys whose prefix matches the supplied key.
    Bcrypt verification ensures constant-time comparison per candidate.
    """
    if not raw_key:
        return None, None

    prefix = raw_key[:11]
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.is_active.is_(True),
        )
    )
    candidates = result.scalars().all()

    now = datetime.now(timezone.utc)
    for candidate in candidates:
        if candidate.expires_at is not None and candidate.expires_at < now:
            continue
        if verify_api_key(raw_key, candidate.key_hash):
            # Update last_used_at timestamp.
            await db.execute(
                update(ApiKey)
                .where(ApiKey.id == candidate.id)
                .values(last_used_at=now)
            )
            # Load the owning user.
            user_result = await db.execute(
                select(User).where(
                    User.id == candidate.user_id,
                    User.is_active.is_(True),
                )
            )
            user = user_result.scalar_one_or_none()
            return user, candidate

    return None, None


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current user from either a JWT or an API key header.

    Checks X-API-Key first, then falls back to the Bearer token.

    Raises:
        HTTPException 401 if no valid credential is provided.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # --- Try API key header first ---
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        user, api_key_record = await _resolve_api_key_user(api_key_header, db)
        if user is None:
            raise credentials_exception
        # Stash the ApiKey record on the request state so scope checks can use it.
        request.state.api_key = api_key_record
        return user

    # --- Fall back to JWT ---
    if token:
        user = await _resolve_jwt_user(token, db)
        if user is not None:
            request.state.api_key = None
            return user

    raise credentials_exception


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user has admin privileges.

    Raises:
        HTTPException 403 if the user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return current_user


def require_scope(scope: str) -> Callable:
    """Return a dependency that verifies the API key has the required scope.

    For JWT-authenticated requests (no API key), all scopes are implicitly
    granted -- scope restrictions only apply to API keys.

    Scope matching supports wildcard patterns, e.g. ``automation:*`` matches
    ``automation:read`` and ``automation:write``.
    """

    async def _check_scope(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        api_key: ApiKey | None = getattr(request.state, "api_key", None)
        if api_key is None:
            # JWT auth -- all scopes granted.
            return current_user

        granted_scopes: list[str] = api_key.scopes or []
        for granted in granted_scopes:
            if fnmatch.fnmatch(scope, granted):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key missing required scope: {scope}",
        )

    return _check_scope
