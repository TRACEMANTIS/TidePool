"""Authentication router -- login, registration, API keys, and user management.

Implements:
  - JWT login / refresh for the web dashboard
  - API key CRUD for programmatic access
  - Admin-only user registration
  - Password change with complexity validation
  - Account lockout after 5 failed login attempts (15-minute window)

No default admin account is created automatically.

CLI bootstrap for the first admin user:
    python -m app.cli create-admin --username admin --email admin@example.com
    (or use a one-off script against the database directly)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    ChangePassword,
    PasswordValidationError,
    RefreshRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    generate_api_key,
    hash_password,
    validate_password_complexity,
    verify_password,
)

router = APIRouter(prefix="/auth")

# ---------------------------------------------------------------------------
# Account lockout settings
# ---------------------------------------------------------------------------
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


# ---------------------------------------------------------------------------
# Helper: check / update lockout state
# ---------------------------------------------------------------------------

def _is_locked(user: User) -> bool:
    """Return True if the user account is currently locked out."""
    if user.locked_until is None:
        return False
    now = datetime.now(timezone.utc)
    if user.locked_until > now:
        return True
    # Lock window has expired -- will be reset on next successful login.
    return False


# ---------------------------------------------------------------------------
# JWT endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate a user and return JWT access + refresh tokens."""
    result = await db.execute(
        select(User).where(User.username == credentials.username)
    )
    user = result.scalar_one_or_none()

    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        raise generic_error

    # Check lockout.
    if _is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Account is temporarily locked due to too many failed login "
                "attempts. Try again later."
            ),
        )

    if not user.is_active:
        raise generic_error

    if not verify_password(credentials.password, user.hashed_password):
        # Increment failed attempts and possibly lock.
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=LOCKOUT_DURATION_MINUTES
            )
        await db.flush()
        raise generic_error

    # Successful login -- reset lockout counters.
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.flush()

    token_data = {"sub": user.username, "user_id": user.id, "is_admin": user.is_admin}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data={"sub": user.username, "user_id": user.id})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload.",
        )

    result = await db.execute(
        select(User).where(User.username == username, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    token_data = {"sub": user.username, "user_id": user.id, "is_admin": user.is_admin}
    new_access = create_access_token(data=token_data)
    new_refresh = create_refresh_token(data={"sub": user.username, "user_id": user.id})

    return Token(access_token=new_access, refresh_token=new_refresh)


# ---------------------------------------------------------------------------
# User management endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user account. Requires admin privileges."""
    # Validate password complexity at the endpoint level.
    complexity_errors = validate_password_complexity(payload.password)
    if complexity_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=PasswordValidationError(errors=complexity_errors).model_dump(),
        )

    # Check for duplicate username.
    existing = await db.execute(
        select(User).where(User.username == payload.username)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        )

    # Check for duplicate email.
    existing_email = await db.execute(
        select(User).where(User.email == payload.email)
    )
    if existing_email.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=payload.is_admin,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
async def current_user(
    user: User = Depends(get_current_user),
) -> User:
    """Return the profile of the currently authenticated user."""
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePassword,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change the current user's password. Requires the current password."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    complexity_errors = validate_password_complexity(payload.new_password)
    if complexity_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=PasswordValidationError(errors=complexity_errors).model_dump(),
        )

    user.hashed_password = hash_password(payload.new_password)
    await db.flush()


# ---------------------------------------------------------------------------
# API key endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new API key. The raw key is returned exactly once."""
    raw_key, key_hash, key_prefix = generate_api_key()

    expires_at = None
    if payload.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    api_key = ApiKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=payload.name,
        user_id=user.id,
        scopes=payload.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "is_active": api_key.is_active,
        "created_at": api_key.created_at,
        "expires_at": api_key.expires_at,
        "last_used_at": api_key.last_used_at,
        "raw_key": raw_key,
    }


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKey]:
    """List all API keys belonging to the current user (metadata only)."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke (deactivate) an API key. Only the key owner or an admin can do this."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found.",
        )

    if api_key.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only revoke your own API keys.",
        )

    api_key.is_active = False
    await db.flush()
