"""SMTP profile management router."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/smtp-profiles")


# -- Local schemas (could be moved to schemas/ as the app grows) -----------


class SMTPProfileCreate(BaseModel):
    """Payload for creating an SMTP sending profile."""

    name: str = Field(..., min_length=1, max_length=128)
    host: str
    port: int = 587
    username: str
    password: str
    from_address: str
    use_tls: bool = True


class SMTPProfileUpdate(BaseModel):
    """Payload for updating an SMTP sending profile."""

    name: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    use_tls: bool | None = None


class SMTPProfileResponse(BaseModel):
    """SMTP profile returned by the API (password redacted)."""

    id: int
    name: str
    host: str
    port: int
    username: str
    from_address: str
    use_tls: bool


# -- Endpoints -------------------------------------------------------------


@router.get("/smtp-profiles", response_model=list[SMTPProfileResponse])
async def list_smtp_profiles(
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return all configured SMTP profiles."""
    return []


@router.post(
    "/smtp-profiles",
    response_model=SMTPProfileResponse,
    status_code=201,
)
async def create_smtp_profile(
    payload: SMTPProfileCreate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Create a new SMTP sending profile."""
    return {
        "id": 1,
        "name": payload.name,
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "from_address": payload.from_address,
        "use_tls": payload.use_tls,
    }


@router.get("/smtp-profiles/{profile_id}", response_model=SMTPProfileResponse)
async def get_smtp_profile(
    profile_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return a single SMTP profile by ID."""
    return {
        "id": profile_id,
        "name": "Placeholder",
        "host": "smtp.example.com",
        "port": 587,
        "username": "user@example.com",
        "from_address": "noreply@example.com",
        "use_tls": True,
    }


@router.put("/smtp-profiles/{profile_id}", response_model=SMTPProfileResponse)
async def update_smtp_profile(
    profile_id: int,
    payload: SMTPProfileUpdate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Update an existing SMTP profile."""
    return {
        "id": profile_id,
        "name": payload.name or "Updated",
        "host": payload.host or "smtp.example.com",
        "port": payload.port or 587,
        "username": payload.username or "user@example.com",
        "from_address": payload.from_address or "noreply@example.com",
        "use_tls": payload.use_tls if payload.use_tls is not None else True,
    }


@router.delete("/smtp-profiles/{profile_id}", response_model=SuccessResponse)
async def delete_smtp_profile(
    profile_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Delete an SMTP profile."""
    return {"message": f"SMTP profile {profile_id} deleted."}


@router.post("/smtp-profiles/{profile_id}/test", response_model=SuccessResponse)
async def test_smtp_profile(
    profile_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Send a test email using the specified SMTP profile."""
    return {"message": f"Test email sent via profile {profile_id}."}
