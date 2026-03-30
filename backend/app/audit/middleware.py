"""Audit logging middleware for TidePool.

Intercepts state-changing requests (POST, PUT, DELETE) and records them
to the audit_logs table.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.audit import AuditLog
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)

# Paths to skip (high-volume tracking endpoints, health checks)
_SKIP_PREFIXES = (
    "/api/v1/tracking/",
    "/health",
    "/",
)

# Only audit state-changing methods
_AUDITED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Log state-changing API requests to the audit_logs table."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-auditable methods
        if request.method not in _AUDITED_METHODS:
            return await call_next(request)

        # Skip tracking and health endpoints
        path = request.url.path
        if path.startswith("/api/v1/tracking/") or path in ("/health", "/"):
            return await call_next(request)

        response: Response = await call_next(request)

        # Extract audit details after the response is produced
        try:
            actor = self._extract_actor(request)
            action = f"{request.method} {path}"
            resource_type, resource_id = self._parse_resource(path)
            ip_address = self._get_client_ip(request)

            async with async_session() as session:
                stmt = insert(AuditLog).values(
                    actor=actor,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip_address,
                )
                await session.execute(stmt)
                await session.commit()
        except Exception:
            # Audit logging must not break the request cycle.
            logger.exception("Failed to write audit log entry")

        return response

    @staticmethod
    def _extract_actor(request: Request) -> str:
        """Best-effort extraction of the acting user from the request."""
        # Try JWT from Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                return payload["sub"]

        # Try API key header (log the prefix only)
        api_key = request.headers.get("x-api-key", "")
        if api_key:
            return f"apikey:{api_key[:11]}"

        return "anonymous"

    @staticmethod
    def _parse_resource(path: str) -> tuple[str, str]:
        """Extract resource type and ID from the URL path.

        Example: /api/v1/campaigns/42 -> ("campaign", "42")
        """
        parts = [p for p in path.strip("/").split("/") if p]
        # Skip the api/v1 prefix
        resource_parts = parts[2:] if len(parts) > 2 else parts

        resource_type = resource_parts[0] if resource_parts else "unknown"
        # Singularise: strip trailing 's'
        if resource_type.endswith("s") and len(resource_type) > 1:
            resource_type = resource_type[:-1]

        resource_id = resource_parts[1] if len(resource_parts) > 1 else "N/A"

        return resource_type, str(resource_id)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Get client IP, respecting X-Forwarded-For if present."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"


# ---------------------------------------------------------------------------
# Standalone audit logging function (for use within endpoints)
# ---------------------------------------------------------------------------

async def log_audit_event(
    db: AsyncSession,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Explicitly log an audit event from within an endpoint.

    Use this for fine-grained audit entries that capture before/after state.
    """
    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        before_state=before_state,
        after_state=after_state,
        ip_address=ip,
    )
    db.add(entry)
    await db.flush()
