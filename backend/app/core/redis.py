from typing import AsyncGenerator
import redis.asyncio as redis
from app.core.config import settings

class RedisService:
    """
    Manages the lifecycle of the asynchronous Redis client pool.
    """
    def __init__(self) -> None:
        self.client: redis.Redis | None = None

    def init_redis(self) -> None:
        """
        Initializes the async Redis client using configuration settings.
        """
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,  # Automatically decodes Redis bytes response to python strings
        )

    async def ping(self) -> bool:
        """
        Runs a ping query on the Redis server to check connectivity.
        """
        if self.client is None:
            self.init_redis()
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def close(self) -> None:
        """
        Closes the Redis client connection pool safely.
        """
        if self.client:
            await self.client.aclose()  # Use aclose() for redis-py 5.x+
            self.client = None

# Single global instance to manage connection state
redis_service = RedisService()

async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """
    FastAPI dependency yielding the current active Redis client.
    """
    if redis_service.client is None:
        redis_service.init_redis()
    yield redis_service.client
