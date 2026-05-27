import json
from fastapi import APIRouter, Depends, status
import redis.asyncio as redis
from typing import List
from app.core.redis import get_redis
from app.schemas.worker import QueueStatsResponse, DLQTaskPayload
from app.workers.task_queue import TaskQueue
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    current_user: User = Depends(get_current_user),  # Protected session route
    cache: redis.Redis = Depends(get_redis),
):
    """
    Returns active queue size diagnostics.
    """
    default_size = await cache.llen("queue:default")
    delayed_size = await cache.zcard("queue:delayed")
    dlq_size = await cache.llen("queue:dlq")

    return {
        "default_queue_size": default_size,
        "delayed_queue_size": delayed_size,
        "dlq_size": dlq_size,
    }

@router.get("/dlq", response_model=List[DLQTaskPayload])
async def get_dlq_tasks(
    current_user: User = Depends(get_current_user),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Retrieves all dead-lettered task payloads for monitoring and debugging.
    """
    # Fetch all tasks in the list
    raw_payloads = await cache.lrange("queue:dlq", 0, -1)
    
    tasks = []
    for item in raw_payloads:
        try:
            tasks.append(json.loads(item))
        except (TypeError, json.JSONDecodeError):
            continue
            
    return tasks

@router.post("/test-fail", status_code=status.HTTP_202_ACCEPTED)
async def trigger_simulated_failure(
    current_user: User = Depends(get_current_user),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Test Route: Enqueues an intentionally failing task 'mock_failed_task'.
    Used to demonstrate the 3-attempt backoff retry cycle and eventual DLQ promotion.
    """
    queue = TaskQueue(cache)
    # Configure with max_retries=2 (total 3 attempts) for quick test cycles
    task_id = await queue.enqueue(name="mock_failed_task", max_retries=2)

    return {
        "task_id": task_id,
        "status": "enqueued",
        "message": "Intentionally failing task enqueued. Watch the logs to audit exponential retries and DLQ promotion!"
    }
