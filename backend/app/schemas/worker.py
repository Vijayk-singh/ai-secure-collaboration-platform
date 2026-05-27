from typing import Any, Dict, List
from pydantic import BaseModel, Field

class QueueStatsResponse(BaseModel):
    """
    Diagnostic metrics returning the active sizes of each queue array.
    """
    default_queue_size: int = Field(..., description="Size of queue:default list")
    delayed_queue_size: int = Field(..., description="Size of queue:delayed sorted set")
    dlq_size: int = Field(..., description="Size of queue:dlq list")

class DLQTaskPayload(BaseModel):
    """
    Response schema returning dead-lettered task details for auditing.
    """
    task_id: str
    name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    retry_count: int
    max_retries: int
    dlq_timestamp: float = Field(..., description="Timestamp when task was shunted to DLQ")
    dlq_reason: str = Field(..., description="Traceback error message that caused the failure")
