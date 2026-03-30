"""Email template management router."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/templates")


# -- Local schemas ---------------------------------------------------------


class TemplateCreate(BaseModel):
    """Payload for creating an email template."""

    name: str = Field(..., min_length=1, max_length=256)
    subject: str
    html_body: str
    text_body: str | None = None
    envelope_sender_name: str | None = None


class TemplateUpdate(BaseModel):
    """Payload for updating an email template."""

    name: str | None = None
    subject: str | None = None
    html_body: str | None = None
    text_body: str | None = None
    envelope_sender_name: str | None = None


class TemplateResponse(BaseModel):
    """Email template returned by the API."""

    id: int
    name: str
    subject: str
    html_body: str
    text_body: str | None = None
    envelope_sender_name: str | None = None
    created_at: str
    updated_at: str


# -- Endpoints -------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return all email templates."""
    return []


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: TemplateCreate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Create a new email template."""
    return {
        "id": 1,
        "name": payload.name,
        "subject": payload.subject,
        "html_body": payload.html_body,
        "text_body": payload.text_body,
        "envelope_sender_name": payload.envelope_sender_name,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return a single email template."""
    return {
        "id": template_id,
        "name": "Placeholder",
        "subject": "Subject",
        "html_body": "<p>Body</p>",
        "text_body": None,
        "envelope_sender_name": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Update an existing email template."""
    return {
        "id": template_id,
        "name": payload.name or "Updated",
        "subject": payload.subject or "Subject",
        "html_body": payload.html_body or "<p>Body</p>",
        "text_body": payload.text_body,
        "envelope_sender_name": payload.envelope_sender_name,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@router.delete("/templates/{template_id}", response_model=SuccessResponse)
async def delete_template(
    template_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Delete an email template."""
    return {"message": f"Template {template_id} deleted."}


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Render a preview of the template with sample variable substitution."""
    return {
        "id": template_id,
        "rendered_subject": "Preview Subject",
        "rendered_html": "<p>Preview body with {{FirstName}} replaced.</p>",
    }
