"""Address book and contact management router."""

from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.schemas.common import PaginatedResponse, SuccessResponse

router = APIRouter(prefix="/addressbooks")


# -- Local schemas ---------------------------------------------------------


class AddressBookResponse(BaseModel):
    """Address book summary returned by the API."""

    id: int
    name: str
    contact_count: int
    created_at: str


class ContactResponse(BaseModel):
    """Single contact record."""

    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None


class ColumnMapping(BaseModel):
    """Column mapping payload for CSV/XLSX imports."""

    email: str
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None


# -- Endpoints -------------------------------------------------------------


@router.post(
    "/addressbooks/upload",
    response_model=SuccessResponse,
    status_code=201,
)
async def upload_addressbook(
    file: UploadFile = File(...),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Upload a CSV or XLSX file to create a new address book."""
    return {
        "message": f"File '{file.filename}' uploaded. Map columns to continue.",
        "data": {"addressbook_id": 1, "detected_columns": []},
    }


@router.get("/addressbooks", response_model=list[AddressBookResponse])
async def list_addressbooks(
    _user: dict = Depends(get_current_user),
) -> list[dict]:
    """Return all address books for the current user."""
    return []


@router.get("/addressbooks/{book_id}", response_model=AddressBookResponse)
async def get_addressbook(
    book_id: int,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return address book details including import statistics."""
    return {
        "id": book_id,
        "name": "Placeholder",
        "contact_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
    }


@router.get(
    "/addressbooks/{book_id}/contacts",
    response_model=PaginatedResponse[ContactResponse],
)
async def list_contacts(
    book_id: int,
    page: int = 1,
    per_page: int = 50,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return paginated contacts for an address book."""
    return {
        "items": [],
        "total": 0,
        "page": page,
        "per_page": per_page,
        "pages": 0,
    }


@router.post(
    "/addressbooks/{book_id}/map-columns",
    response_model=SuccessResponse,
)
async def map_columns(
    book_id: int,
    mapping: ColumnMapping,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Apply column mapping to a previously uploaded file and import contacts."""
    return {"message": f"Column mapping applied to address book {book_id}."}
