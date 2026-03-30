"""Lightweight tracking-only FastAPI entrypoint.

This module creates a minimal FastAPI application that serves ONLY the
tracking endpoints (/t/o/, /t/c/, /t/s/) and the landing page server
(/lp/).  It is designed to run as a separate service so that burst
traffic from campaign recipients does not impact the admin dashboard.

What is included:
- Tracking router (email opens, link clicks, form submissions)
- Landing page server router (serves pages that clicked links lead to)
- SecurityHeadersMiddleware (basic security headers)
- Inline 100KB request size limit (tracking payloads are tiny)
- /health endpoint with Redis and DB connectivity checks

What is intentionally excluded:
- Authentication middleware (tracking endpoints are token-based, no sessions)
- AuditMiddleware (tracking events are recorded by the EventRecorder, not audit)
- CORSMiddleware (tracking endpoints are not called by browser JS from other origins)
- RequestSizeLimitMiddleware (replaced by a tighter inline check)
- Rate limiting (tracking tier handles volume via horizontal scaling)
- All admin/dashboard routers
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db, close_db, async_session
from app.api.tracking import router as tracking_router
from app.landing_pages.server import router as landing_page_router


# -- Security headers middleware ----------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers into every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response


# -- Inline request size limit ------------------------------------------------
# Tracking submissions are small (form field names only).  100KB is generous.

_MAX_TRACKING_BODY_BYTES = 100 * 1024  # 100 KB


class TrackingSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds 100KB."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            if int(content_length) > _MAX_TRACKING_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large. "
                            f"Maximum allowed: {_MAX_TRACKING_BODY_BYTES} bytes."
                        )
                    },
                )
        return await call_next(request)


# -- Lifespan -----------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle events."""
    await init_db()
    yield
    await close_db()


# -- Health check helpers -----------------------------------------------------

async def _check_db() -> bool:
    """Return True if the database is reachable."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    """Return True if Redis is reachable."""
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


# -- Application factory ------------------------------------------------------

def create_tracking_app() -> FastAPI:
    """Build the minimal tracking-only FastAPI application."""
    app = FastAPI(
        title="TidePool Tracking Service",
        description=(
            "Lightweight tracking service for email opens, link clicks, "
            "and credential submissions. Runs independently from the "
            "admin API to isolate burst campaign traffic."
        ),
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
        # Disable interactive docs in production tracking service.
        # Uncomment for debugging: docs_url="/docs", redoc_url="/redoc"
        docs_url=None,
        redoc_url=None,
    )

    # -- Middleware (last added = first executed) ------------------------------
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TrackingSizeLimitMiddleware)

    # -- Routers --------------------------------------------------------------
    # Tracking endpoints: /api/v1/t/o/{id}, /api/v1/t/c/{id}, /api/v1/t/s/{id}
    app.include_router(tracking_router, prefix="/api/v1", tags=["tracking"])

    # Landing page server: /lp/{campaign_id}/{recipient_token}
    app.include_router(landing_page_router, tags=["landing-pages"])

    # -- Health endpoint ------------------------------------------------------
    @app.get("/health")
    async def health_check() -> dict:
        """Return tracking service health status."""
        db_ok = await _check_db()
        redis_ok = await _check_redis()

        status = "healthy" if (db_ok and redis_ok) else "degraded"

        return {
            "service": "tracking",
            "status": status,
            "database": "connected" if db_ok else "unavailable",
            "redis": "connected" if redis_ok else "unavailable",
        }

    return app


app = create_tracking_app()
