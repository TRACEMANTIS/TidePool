"""Health check endpoints for liveness and readiness probes."""

from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session

router = APIRouter()


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
        import redis.asyncio as aioredis

        from app.config import settings

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


@router.get("/health")
async def health_check() -> dict:
    """Return platform health status including database and Redis connectivity."""
    db_ok = await _check_db()
    redis_ok = await _check_redis()

    status = "healthy" if (db_ok and redis_ok) else "degraded"

    return {
        "status": status,
        "database": "connected" if db_ok else "unavailable",
        "redis": "connected" if redis_ok else "unavailable",
    }
