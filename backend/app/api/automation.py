"""FastAPI router for campaign automation -- quick-launch workflow.

This module exposes endpoints that allow launching a complete phishing
campaign from a single API call (file upload + lure parameters), removing
the need for multiple manual UI steps.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.automation.file_parser import ColumnMapping, detect_columns
from app.automation.orchestrator import CampaignOrchestrator, OrchestratorError
from app.schemas.automation import (
    CampaignStatusResponse,
    ColumnDetectionResponse,
    ColumnSuggestion,
    EmailPreview,
    LureCategory,
    PreviewResponse,
    QuickLaunchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation")

UPLOAD_DIR = settings.UPLOAD_DIR
ALLOWED_EXTENSIONS = set(settings.ALLOWED_UPLOAD_EXTENSIONS)
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Magic byte signatures for file type validation.
_ZIP_MAGIC = b"PK"  # xlsx/xls (Office Open XML) are ZIP archives.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(filename: str) -> str:
    """Strip path traversal characters and normalize the filename."""
    # Take only the basename to prevent directory traversal.
    name = os.path.basename(filename)
    # Remove any remaining suspicious characters.
    name = re.sub(r"[^\w.\-]", "_", name)
    return name


def _validate_magic_bytes(header: bytes, extension: str) -> bool:
    """Validate that the file header matches expected magic bytes.

    Returns True if the file appears to be the correct type.
    """
    if extension in (".xlsx", ".xls"):
        # Office Open XML (.xlsx) and compound binary (.xls) both start
        # with the ZIP signature or the OLE2 signature respectively.
        return header[:2] == _ZIP_MAGIC or header[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    if extension == ".csv":
        # CSV files should be decodable as text.
        try:
            header.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


async def _save_upload(file: UploadFile) -> str:
    """Save an uploaded file to the upload directory and return its path.

    Raises HTTPException on invalid extension, bad magic bytes, or
    oversized file.
    """
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    sanitized = _sanitize_filename(file.filename)
    ext = os.path.splitext(sanitized)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    # Ensure the upload directory exists.
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(UPLOAD_DIR, unique_name)

    # Read first chunk to validate magic bytes.
    first_chunk = await file.read(1024 * 256)
    if not first_chunk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if not _validate_magic_bytes(first_chunk[:16], ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content does not match expected format for '{ext}'.",
        )

    total_bytes = len(first_chunk)
    with open(dest, "wb") as fh:
        fh.write(first_chunk)
        while True:
            chunk = await file.read(1024 * 256)  # 256 KB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                fh.close()
                os.unlink(dest)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
                )
            fh.write(chunk)

    return dest


def _build_column_mapping(
    email_column: str,
    first_name_column: str | None,
    last_name_column: str | None,
    department_column: str | None,
) -> ColumnMapping:
    """Build a column mapping dict from the form parameters."""
    return {
        "email": email_column,
        "first_name": first_name_column,
        "last_name": last_name_column,
        "department": department_column,
    }


def _get_user_id(user: dict) -> int:
    """Extract the authenticated user's ID."""
    return user.get("id") or user.get("user_id") or user.get("sub", 0)


# ---------------------------------------------------------------------------
# POST /automation/quick-launch
# ---------------------------------------------------------------------------

@router.post(
    "/quick-launch",
    response_model=QuickLaunchResponse,
    status_code=201,
    summary="Launch a campaign from a contact file and lure parameters",
)
async def quick_launch(
    request: Request,
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file containing contacts"),
    email_column: str = Form(..., max_length=256, description="Column name containing email addresses"),
    first_name_column: str | None = Form(None, max_length=256, description="Column name for first names"),
    last_name_column: str | None = Form(None, max_length=256, description="Column name for last names"),
    department_column: str | None = Form(None, max_length=256, description="Column name for departments"),
    lure_category: LureCategory = Form(..., description="Lure template category"),
    lure_subject: str = Form(..., max_length=500, description="Email subject line"),
    lure_body: str = Form(..., max_length=100000, description="Email body (supports {{first_name}}, {{last_name}}, {{department}}, {{company}} variables)"),
    from_name: str = Form(..., max_length=256, description="Sender display name"),
    from_address: str = Form(..., max_length=320, description="Sender email address"),
    smtp_profile_id: int = Form(..., description="ID of the SMTP profile to use"),
    landing_page_id: int | None = Form(None, description="Landing page ID (uses default if omitted)"),
    training_module_id: int | None = Form(None, description="Training module ID (uses default if omitted)"),
    training_redirect_url: str | None = Form(None, description="External URL to redirect users to after falling for the phish (http/https)"),
    training_redirect_delay_seconds: int = Form(0, ge=0, description="Seconds to show interstitial before redirecting to training URL"),
    send_window_hours: int = Form(24, ge=1, le=720, description="Spread sends over this many hours"),
    campaign_name: str | None = Form(None, max_length=256, description="Campaign name (auto-generated if omitted)"),
    start_immediately: bool = Form(False, description="Dispatch to send queue immediately"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> QuickLaunchResponse:
    """Create and optionally launch a complete phishing campaign.

    Rate limited to 5 requests per minute per client.

    Processing flow:
    1. Validate the SMTP profile exists.
    2. Save uploaded file and create an AddressBook record.
    3. Parse contacts from the file (streamed for large files).
    4. Create an EmailTemplate from the lure parameters.
    5. Create a Campaign linking all components.
    6. If ``start_immediately``, dispatch to the Celery send queue.
    7. Return the campaign ID and summary statistics.
    """
    # Validate training redirect URL scheme if provided.
    if training_redirect_url and not training_redirect_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="training_redirect_url must start with http:// or https://",
        )
    # Manual rate limit check for quick-launch (5/minute).
    limiter = request.app.state.limiter
    await limiter.check("5/minute", request)

    # Save the uploaded file.
    file_path = await _save_upload(file)

    try:
        user_id = _get_user_id(user)
        orchestrator = CampaignOrchestrator(db, user_id=user_id)

        column_mapping = _build_column_mapping(
            email_column, first_name_column, last_name_column, department_column,
        )

        # 1-2. Ingest contacts.
        address_book, valid_count, invalid_count = await orchestrator.ingest_file(
            file_path, column_mapping,
            book_name=campaign_name or file.filename,
        )

        if valid_count == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No valid email addresses found. {invalid_count} rows had invalid or missing emails.",
            )

        # 3. Create template.
        template = await orchestrator.create_template(
            subject=lure_subject,
            body=lure_body,
            category=lure_category.value,
            from_name=from_name,
        )

        # 4. Build campaign name.
        name = campaign_name or f"{lure_category.value} Campaign - {datetime.now(timezone.utc):%Y-%m-%d %H:%M}"

        # 5. Create campaign.
        campaign = await orchestrator.create_campaign(
            name=name,
            address_book=address_book,
            template=template,
            smtp_profile_id=smtp_profile_id,
            landing_page_id=landing_page_id,
            send_window_hours=send_window_hours,
            training_redirect_url=training_redirect_url,
            training_redirect_delay_seconds=training_redirect_delay_seconds,
        )

        # 6. Optionally launch.
        if start_immediately:
            await orchestrator.launch(campaign.id)

        await db.commit()

        estimated_completion = datetime.now(timezone.utc) + timedelta(hours=send_window_hours)

        return QuickLaunchResponse(
            campaign_id=campaign.id,
            name=name,
            total_recipients=valid_count,
            status="SCHEDULED" if start_immediately else "DRAFT",
            estimated_completion=estimated_completion if start_immediately else None,
        )

    except OrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    finally:
        # Clean up the temporary upload.
        if os.path.exists(file_path):
            os.unlink(file_path)


# ---------------------------------------------------------------------------
# POST /automation/preview
# ---------------------------------------------------------------------------

@router.post(
    "/preview",
    response_model=PreviewResponse,
    summary="Preview rendered emails without creating any records",
)
async def preview(
    file: UploadFile = File(..., description="Excel (.xlsx) or CSV file containing contacts"),
    email_column: str = Form(..., max_length=256, description="Column name containing email addresses"),
    first_name_column: str | None = Form(None, max_length=256),
    last_name_column: str | None = Form(None, max_length=256),
    department_column: str | None = Form(None, max_length=256),
    lure_category: LureCategory = Form(...),
    lure_subject: str = Form(..., max_length=500, description="Email subject line"),
    lure_body: str = Form(..., max_length=100000, description="Email body with {{variable}} placeholders"),
    from_name: str = Form(..., max_length=256),
    from_address: str = Form(..., max_length=320),
    smtp_profile_id: int = Form(...),
    landing_page_id: int | None = Form(None),
    training_module_id: int | None = Form(None),
    send_window_hours: int = Form(24, ge=1, le=720),
    campaign_name: str | None = Form(None, max_length=256),
    start_immediately: bool = Form(False),
    _user: dict = Depends(get_current_user),
) -> PreviewResponse:
    """Render a preview of the first 5 emails and return recipient stats.

    No database records are created.
    """
    file_path = await _save_upload(file)

    try:
        column_mapping = _build_column_mapping(
            email_column, first_name_column, last_name_column, department_column,
        )

        orchestrator = CampaignOrchestrator.__new__(CampaignOrchestrator)
        previews, total = orchestrator.preview(
            file_path, column_mapping, lure_subject, lure_body, count=5,
        )

        emails = [
            EmailPreview(
                to=p["to"],
                subject=p["subject"],
                body_preview=p["body_preview"],
            )
            for p in previews
        ]

        return PreviewResponse(
            emails=emails,
            total_recipients=total,
            estimated_duration_hours=float(send_window_hours),
        )
    except OrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


# ---------------------------------------------------------------------------
# GET /automation/campaigns/{id}/status
# ---------------------------------------------------------------------------

@router.get(
    "/campaigns/{campaign_id}/status",
    response_model=CampaignStatusResponse,
    summary="Detailed campaign send status",
)
async def campaign_status(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> CampaignStatusResponse:
    """Return sent/pending/failed counts, current send rate, and ETA.

    Only the campaign owner may view status.
    """
    user_id = _get_user_id(user)
    orchestrator = CampaignOrchestrator(db, user_id=user_id)

    try:
        data = await orchestrator.get_status(campaign_id)
    except OrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    # Ownership check: the orchestrator should enforce this, but we add a
    # belt-and-suspenders check here.
    if data.get("created_by") and data["created_by"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this campaign.",
        )

    return CampaignStatusResponse(**data)


# ---------------------------------------------------------------------------
# POST /automation/campaigns/{id}/abort
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/abort",
    response_model=CampaignStatusResponse,
    summary="Abort a running or scheduled campaign",
)
async def abort_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> CampaignStatusResponse:
    """Stop a campaign immediately and return its final status.

    Only the campaign owner may abort a campaign.
    """
    user_id = _get_user_id(user)
    orchestrator = CampaignOrchestrator(db, user_id=user_id)

    try:
        # Verify ownership before aborting.
        pre_status = await orchestrator.get_status(campaign_id)
        if pre_status.get("created_by") and pre_status["created_by"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to abort this campaign.",
            )

        await orchestrator.abort(campaign_id)
        await db.commit()
        data = await orchestrator.get_status(campaign_id)
    except OrchestratorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return CampaignStatusResponse(**data)


# ---------------------------------------------------------------------------
# POST /automation/detect-columns
# ---------------------------------------------------------------------------

@router.post(
    "/detect-columns",
    response_model=ColumnDetectionResponse,
    summary="Auto-detect column names and suggest mappings",
)
async def detect_columns_endpoint(
    file: UploadFile = File(...),
    _user: dict = Depends(get_current_user),
) -> ColumnDetectionResponse:
    """Upload a file and get back detected columns with sample values."""
    file_path = await _save_upload(file)

    try:
        raw = detect_columns(file_path)
        columns = [
            ColumnSuggestion(
                name=col["name"],
                sample_values=col["sample_values"],
                suggested_mapping=col["suggested_mapping"],
            )
            for col in raw
        ]
        return ColumnDetectionResponse(columns=columns)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)
