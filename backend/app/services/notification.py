import logging
from typing import Optional
import redis.asyncio as redis
from app.workers.task_queue import TaskQueue
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Service layer orchestrating event notifications, packing them into
    asynchronous jobs, and enqueuing them via TaskQueue.
    """
    def __init__(self, cache: Optional[redis.Redis] = None) -> None:
        # Fall back to active global Redis pool singleton
        self.queue = TaskQueue(cache or redis_service.client)

    async def queue_welcome_email(self, email: str, name: Optional[str] = None) -> str:
        """
        Enqueues an async welcome email task for new signups.
        """
        display_name = name or email
        subject = "Welcome to the AI-Powered Secure Collaboration Platform!"
        body = (
            f"Hello {display_name},\n\n"
            f"Thank you for registering! Your secure identity profile has been successfully "
            f"created under MEMBER access. You can now join collaborative workspaces, "
            f"create markdown notes with tags, and chat in realtime rooms.\n\n"
            f"Best regards,\n"
            f"Antigravity Platform Engineering Team"
        )
        
        # Enqueue immediately
        task_id = await self.queue.enqueue(
            name="send_email_notification",
            args=[email, subject, body],
            max_retries=3
        )
        logger.info(f"Notification: Welcoming email task (ID: {task_id}) enqueued for '{email}'.")
        return task_id

    async def queue_workspace_invite(
        self,
        email: str,
        workspace_name: str,
        inviter_name: str
    ) -> str:
        """
        Enqueues an async invite email task when a user joins a workspace.
        """
        subject = f"You've been added to the workspace '{workspace_name}'"
        body = (
            f"Hello,\n\n"
            f"User '{inviter_name}' has successfully added you to their collaborative workspace "
            f"'{workspace_name}'. Log in to your profile now to access shared markdown notes "
            f"and join active room channels!\n\n"
            f"Best regards,\n"
            f"Antigravity Platform Engineering Team"
        )
        
        # Enqueue immediately
        task_id = await self.queue.enqueue(
            name="send_email_notification",
            args=[email, subject, body],
            max_retries=3
        )
        logger.info(f"Notification: Workspace invite email task (ID: {task_id}) enqueued for '{email}'.")
        return task_id
