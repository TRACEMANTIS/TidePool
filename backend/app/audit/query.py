"""Audit log querying and export utilities."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.schemas.reports import AuditLogEntry, AuditLogFilter, AuditLogResponse


async def get_audit_logs(
    db: AsyncSession,
    filters: AuditLogFilter,
) -> AuditLogResponse:
    """Query audit logs with filtering and pagination.

    Returns a paginated response sorted by timestamp descending.
    """
    conditions = []
    if filters.actor:
        conditions.append(AuditLog.actor == filters.actor)
    if filters.action:
        conditions.append(AuditLog.action == filters.action)
    if filters.resource_type:
        conditions.append(AuditLog.resource_type == filters.resource_type)
    if filters.resource_id:
        conditions.append(AuditLog.resource_id == filters.resource_id)
    if filters.date_from:
        conditions.append(AuditLog.timestamp >= filters.date_from)
    if filters.date_to:
        conditions.append(AuditLog.timestamp <= filters.date_to)

    where_clause = and_(*conditions) if conditions else True

    # Total count
    count_q = select(func.count(AuditLog.id)).where(where_clause)
    total = (await db.execute(count_q)).scalar() or 0

    # Paginated query
    offset = (filters.page - 1) * filters.per_page
    data_q = (
        select(AuditLog)
        .where(where_clause)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(filters.per_page)
    )
    rows = (await db.execute(data_q)).scalars().all()

    pages = (total + filters.per_page - 1) // filters.per_page if filters.per_page > 0 else 0

    items = [
        AuditLogEntry(
            id=row.id,
            actor=row.actor,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            before_state=row.before_state,
            after_state=row.after_state,
            ip_address=row.ip_address,
            timestamp=row.timestamp,
        )
        for row in rows
    ]

    return AuditLogResponse(
        items=items,
        total=total,
        page=filters.page,
        per_page=filters.per_page,
        pages=pages,
    )


async def export_audit_log(
    db: AsyncSession,
    campaign_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Export audit trail with chained integrity hashes.

    Each entry receives a SHA-256 hash that includes the previous entry's hash,
    creating a tamper-evident chain.
    """
    conditions = []
    if campaign_id is not None:
        # Filter to entries related to this campaign
        conditions.append(AuditLog.resource_type == "campaign")
        conditions.append(AuditLog.resource_id == str(campaign_id))
    if date_from:
        conditions.append(AuditLog.timestamp >= date_from)
    if date_to:
        conditions.append(AuditLog.timestamp <= date_to)

    where_clause = and_(*conditions) if conditions else True

    q = (
        select(AuditLog)
        .where(where_clause)
        .order_by(AuditLog.timestamp.asc())
    )
    rows = (await db.execute(q)).scalars().all()

    entries: list[dict[str, Any]] = []
    prev_hash = "0" * 64  # Genesis hash

    for row in rows:
        entry_data = {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "before_state": row.before_state,
            "after_state": row.after_state,
            "ip_address": row.ip_address,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }

        # Chain hash: hash of (previous_hash + current entry JSON)
        chain_input = prev_hash + json.dumps(entry_data, sort_keys=True, default=str)
        entry_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        entry_data["integrity_hash"] = entry_hash
        entry_data["previous_hash"] = prev_hash
        entries.append(entry_data)

        prev_hash = entry_hash

    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "total_entries": len(entries),
        "chain_genesis_hash": "0" * 64,
        "chain_final_hash": prev_hash,
        "entries": entries,
    }
