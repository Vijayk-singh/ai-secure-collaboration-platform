import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis
from app.core.database import get_db
from app.core.redis import get_redis

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def check_health(
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Checks the connectivity status of PostgreSQL and Redis.
    Returns 200 with diagnostics.
    """
    database_status = "disconnected"
    redis_status = "disconnected"
    overall_status = "healthy"

    # Verify PostgreSQL connectivity
    try:
        await db.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        overall_status = "unhealthy"

    # Verify Redis connectivity
    try:
        if await cache.ping():
            redis_status = "connected"
        else:
            overall_status = "unhealthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        overall_status = "unhealthy"

    return {
        "status": overall_status,
        "services": {
            "database": database_status,
            "redis": redis_status,
        }
    }
