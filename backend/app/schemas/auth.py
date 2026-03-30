"""Authentication and user Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# -- User schemas --------------------------------------------------------------


class UserLogin(BaseModel):
    """Credentials submitted for authentication."""

    username: str
    password: str


class UserCreate(BaseModel):
    """Payload for creating a new user (admin only).

    Password must be at least 12 characters and include uppercase, lowercase,
    digit, and special character. Complexity is enforced at the endpoint level.
    """

    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str | None = None
    is_admin: bool = False


class UserResponse(BaseModel):
    """Public user representation returned by the API."""

    id: int
    username: str
    email: str
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class ChangePassword(BaseModel):
    """Payload for changing the current user's password."""

    current_password: str
    new_password: str = Field(..., min_length=12, max_length=128)


class PasswordValidationError(BaseModel):
    """Structured response for password complexity failures."""

    detail: str = "Password does not meet complexity requirements."
    errors: list[str]


# -- API key schemas -----------------------------------------------------------


class ApiKeyCreate(BaseModel):
    """Payload for creating a new API key."""

    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Number of days until the key expires. Null for no expiry.",
    )


class ApiKeyResponse(BaseModel):
    """API key metadata (never includes the raw key)."""

    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyResponse):
    """Returned only at creation time -- includes the raw key exactly once."""

    raw_key: str
