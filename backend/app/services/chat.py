import json
import logging
from typing import List, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from app.repositories.chat import ChatRoomRepository, ChatMessageRepository
from app.repositories.workspace import WorkspaceMemberRepository
from app.models.chat import ChatRoom, ChatMessage
from app.core.exceptions import InsufficientPermissionsException
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

class ChatService:
    """
    Service layer coordinating ChatRoom scopes, persisted messages,
    Redis Pub/Sub publishers, and in-memory Redis presences.
    """
    def __init__(self, db: AsyncSession, cache: redis.Redis) -> None:
        self.db = db
        self.cache = cache
        self.room_repo = ChatRoomRepository(db)
        self.message_repo = ChatMessageRepository(db)
        self.member_repo = WorkspaceMemberRepository(db)

    async def _verify_workspace_membership(self, workspace_id: int, user_id: int) -> None:
        """
        Private helper confirming workspace membership permissions.
        """
        membership = await self.member_repo.get_by_workspace_and_user(workspace_id, user_id)
        if not membership:
            raise InsufficientPermissionsException("You must be a member of this workspace to perform chat operations.")

    async def create_room(self, workspace_id: int, name: str, current_user_id: int) -> ChatRoom:
        """
        Creates a Chat Room scoped to a workspace.
        Enforces membership permissions.
        """
        await self._verify_workspace_membership(workspace_id, current_user_id)
        
        room_in = {
            "name": name,
            "workspace_id": workspace_id,
        }
        room = await self.room_repo.create(obj_in=room_in)
        await self.db.commit()
        await self.db.refresh(room)
        
        logger.info(f"ChatRoom '{name}' (ID: {room.id}) created inside Workspace {workspace_id} by User {current_user_id}.")
        return room

    async def list_rooms(self, workspace_id: int, current_user_id: int) -> List[ChatRoom]:
        """
        Lists all chat rooms scoped to a workspace.
        """
        await self._verify_workspace_membership(workspace_id, current_user_id)
        return await self.room_repo.get_by_workspace(workspace_id)

    async def get_room_history(self, room_id: int, current_user_id: int, *, limit: int = 50) -> List[ChatMessage]:
        """
        Retrieves paginated catch-up history for a room, validating workspace membership.
        """
        room = await self.room_repo.get(room_id)
        if not room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found.")

        # Ensure user belongs to the room's workspace
        await self._verify_workspace_membership(room.workspace_id, current_user_id)
        return await self.message_repo.get_room_history(room_id, limit=limit)

    async def persist_message(self, room_id: int, user_id: int, content: str) -> ChatMessage:
        """
        Persists a chat message in PostgreSQL and eager-loads its author relationship.
        """
        message_in = {
            "room_id": room_id,
            "user_id": user_id,
            "content": content,
        }
        message = await self.message_repo.create(obj_in=message_in)
        await self.db.commit()
        
        # Query matching messages with joinedload user to load the related author profile safely
        query = select(ChatMessage).options(joinedload(ChatMessage.user)).filter(ChatMessage.id == message.id)
        result = await self.db.execute(query)
        message_loaded = result.scalars().first()
        return message_loaded

    async def publish_event(self, workspace_id: int, room_id: int, event: dict) -> None:
        """
        Publishes a JSON-serialized event to our global Redis Pub/Sub channel.
        """
        channel = f"workspace:{workspace_id}:room:{room_id}"
        payload_str = json.dumps(event)
        await self.cache.publish(channel, payload_str)

    # ---------------------------------------------------------
    # STATEFUL PRESENCE OPERATIONS
    # ---------------------------------------------------------
    async def track_user_connected(self, workspace_id: int, user_id: int) -> List[int]:
        """
        Adds a user ID to the workspace's online presence Redis set.
        Publishes a presence 'online' update globally.
        Returns the updated list of online user IDs.
        """
        redis_key = f"workspace:{workspace_id}:online_users"
        
        # Add user to set
        await self.cache.sadd(redis_key, user_id)
        
        # Publish global presence update
        event = {
            "type": "presence",
            "event": "online",
            "user_id": user_id,
        }
        await self.publish_event(workspace_id, room_id=0, event=event)  # room_id 0 serves as workspace-scoped system broadcasts
        
        # Retrieve all online users
        online_ids = await self.cache.smembers(redis_key)
        return [int(uid) for uid in online_ids]

    async def track_user_disconnected(self, workspace_id: int, user_id: int) -> None:
        """
        Removes a user ID from the workspace's online presence Redis set.
        Publishes a presence 'offline' update globally.
        """
        redis_key = f"workspace:{workspace_id}:online_users"
        
        # Remove user from set
        await self.cache.srem(redis_key, user_id)
        
        # Publish global presence update
        event = {
            "type": "presence",
            "event": "offline",
            "user_id": user_id,
        }
        await self.publish_event(workspace_id, room_id=0, event=event)
