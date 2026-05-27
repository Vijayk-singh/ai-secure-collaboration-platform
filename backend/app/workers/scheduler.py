import asyncio
import time
import logging
from typing import Optional
import redis.asyncio as redis
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    Background delayed task scheduler.
    Periodically polls 'queue:delayed' Sorted Set, promoting ready tasks
    to 'queue:default' atomically using Redis Transactions.
    """
    def __init__(self, cache: redis.Redis) -> None:
        self.cache = cache
        self.running = False
        self.task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """
        Spawns the background asyncio scheduler loop.
        """
        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info("Task Scheduler daemon started.")

    async def stop(self) -> None:
        """
        Terminates the background scheduler loop.
        """
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            logger.info("Task Scheduler daemon stopped.")

    async def _scheduler_loop(self) -> None:
        """
        Main polling loop checking delayed tasks ready for execution.
        """
        while self.running:
            try:
                now = time.time()
                # Fetch all tasks whose ETA timestamp is less than or equal to now
                tasks = await self.cache.zrangebyscore("queue:delayed", 0, now)
                
                for task_str in tasks:
                    # Run a transaction pipe to claim task and prevent multi-node double scheduling
                    async with self.cache.pipeline(transaction=True) as pipe:
                        pipe.zrem("queue:delayed", task_str)
                        pipe.lpush("queue:default", task_str)
                        
                        results = await pipe.execute()
                        # results[0] is the result of zrem. If it returned 1, this worker successfully removed it
                        if results[0] == 1:
                            logger.info("Scheduler promoted delayed task to active queue successfully.")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Task Scheduler encountered an error in polling loop: {e}")

            # Sleep 1 second before checking again
            await asyncio.sleep(1.0)
