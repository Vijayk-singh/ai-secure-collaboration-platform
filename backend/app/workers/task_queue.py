import json
import logging
import uuid
import time
from typing import Any, Dict, List, Optional
import redis.asyncio as redis
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

class TaskQueue:
    """
    Task Queue client facilitating pushing async jobs to Redis queues
    supporting immediate lists and sorted delayed sets.
    """
    def __init__(self, cache: redis.Redis) -> None:
        self.cache = cache

    async def enqueue(
        self,
        name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        delay: Optional[int] = None,  # Delay in seconds
        max_retries: int = 3,
    ) -> str:
        """
        Packs a task name and its arguments, enqueuing it for async execution.
        """
        task_id = str(uuid.uuid4())
        
        payload = {
            "task_id": task_id,
            "name": name,
            "args": args or [],
            "kwargs": kwargs or {},
            "retry_count": 0,
            "max_retries": max_retries,
        }
        
        payload_str = json.dumps(payload)

        # Handle delayed task (Sorted Set queue:delayed)
        if delay and delay > 0:
            target_time = time.time() + delay
            await self.cache.zadd("queue:delayed", {payload_str: target_time})
            logger.info(f"Task '{name}' (ID: {task_id}) enqueued in delayed queue. ETA delay: {delay}s.")
        # Handle immediate task (List queue:default)
        else:
            await self.cache.lpush("queue:default", payload_str)
            logger.info(f"Task '{name}' (ID: {task_id}) enqueued in default queue for immediate execution.")

        return task_id

    async def enqueue_raw(self, payload_str: str, delay: int = 0) -> None:
        """
        Direct enqueuer helper.
        Ideal for re-scheduling failed tasks with exponential backoffs.
        """
        if delay > 0:
            target_time = time.time() + delay
            await self.cache.zadd("queue:delayed", {payload_str: target_time})
        else:
            await self.cache.lpush("queue:default", payload_str)
