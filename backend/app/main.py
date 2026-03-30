"""TidePool FastAPI application factory and entrypoint."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.api import (
    health,
    auth,
    automation,
    campaigns,
    smtp_profiles,
    addressbooks,
    templates,
    landing_pages,
    tracking,
    reports,
    monitor,
    webhooks,
)
from app.api import agents as agents_api
from app.api import audit as audit_api
from app.audit.middleware import AuditMiddleware
from app.tracking.phish_report import router as phish_report_router
from app.training import router as training


# -- Rate limiter (attached to app.state for use in routers) ----------------

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
)


# -- Security headers middleware --------------------------------------------

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


# -- Request size limit middleware ------------------------------------------

# 50 MB for multipart (file uploads), 1 MB for everything else.
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_MAX_BODY_BYTES = 1 * 1024 * 1024


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the allowed maximum."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            length = int(content_length)
            content_type = request.headers.get("content-type", "")
            if "multipart/form-data" in content_type:
                limit = _MAX_UPLOAD_BYTES
            else:
                limit = _MAX_BODY_BYTES

            if length > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Maximum allowed: {limit} bytes."
                    },
                )

        return await call_next(request)


# -- Lifespan ---------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage startup and shutdown lifecycle events."""
    await init_db()
    yield
    await close_db()


# -- Application factory ----------------------------------------------------

def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="Phishing simulation and security awareness platform.",
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # -- Rate limiter -------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -- Middleware (order matters: last added = first executed) -------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(AuditMiddleware)

    # -- Routers ------------------------------------------------------------
    app.include_router(health.router, tags=["health"])
    app.include_router(automation.router, prefix="/api/v1", tags=["automation"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(campaigns.router, prefix="/api/v1", tags=["campaigns"])
    app.include_router(smtp_profiles.router, prefix="/api/v1", tags=["smtp-profiles"])
    app.include_router(addressbooks.router, prefix="/api/v1", tags=["addressbooks"])
    app.include_router(templates.router, prefix="/api/v1", tags=["templates"])
    app.include_router(landing_pages.router, prefix="/api/v1", tags=["landing-pages"])
    app.include_router(tracking.router, prefix="/api/v1", tags=["tracking"])
    app.include_router(reports.router, prefix="/api/v1", tags=["reports"])
    app.include_router(monitor.router, prefix="/api/v1", tags=["monitor"])
    app.include_router(audit_api.router, prefix="/api/v1", tags=["audit"])
    app.include_router(phish_report_router, prefix="/api/v1", tags=["tracking"])
    app.include_router(training.router, prefix="/api/v1", tags=["training"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
    app.include_router(agents_api.router, prefix="/api/v1", tags=["agents"])

    # -- Root endpoint ------------------------------------------------------
    @app.get("/")
    async def root() -> dict:
        """Return basic application information."""
        return {
            "app": settings.APP_NAME,
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


app = create_app()
