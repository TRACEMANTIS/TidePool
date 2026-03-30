"""Audit log router -- querying and exporting audit trails."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.audit.query import export_audit_log, get_audit_logs
from app.reports.export import export_csv, export_json
from app.schemas.reports import AuditLogFilter, AuditLogResponse

router = APIRouter(prefix="/audit")


# ---------------------------------------------------------------------------
# Paginated audit log listing
# ---------------------------------------------------------------------------

@router.get("/logs", response_model=AuditLogResponse)
async def list_audit_logs(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> AuditLogResponse:
    """Return paginated, filterable audit logs. Requires admin role."""
    filters = AuditLogFilter(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )
    return await get_audit_logs(db, filters)


# ---------------------------------------------------------------------------
# Audit log export
# ---------------------------------------------------------------------------

@router.get("/logs/export")
async def export_audit_logs(
    format: str = Query(default="json", regex="^(json|csv)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> StreamingResponse:
    """Export the full audit trail as JSON or CSV. Requires admin role."""
    result = await export_audit_log(db, date_from=date_from, date_to=date_to)

    if format == "csv":
        rows = result.get("entries", [])
        return await export_csv(rows, "audit_log_export.csv")
    else:
        return await export_json(result, "audit_log_export.json")


# ---------------------------------------------------------------------------
# Campaign-specific audit trail
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}")
async def campaign_audit_trail(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
) -> dict:
    """Return the full audit trail for a specific campaign with integrity hashes."""
    return await export_audit_log(db, campaign_id=campaign_id)
