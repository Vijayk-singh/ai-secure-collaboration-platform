from typing import List
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.chat import ChatRoom, ChatMessage

class ChatRoomRepository(BaseRepository[ChatRoom]):
    """
    Repository handling database actions for ChatRoom entities.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(ChatRoom, db)

    async def get_by_workspace(self, workspace_id: int) -> List[ChatRoom]:
        """
        Retrieves all active chat rooms scoped to a workspace.
        """
        query = select(self.model).filter(self.model.workspace_id == workspace_id).order_by(self.model.created_at.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

class ChatMessageRepository(BaseRepository[ChatMessage]):
    """
    Repository handling database actions for ChatMessage entities.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(ChatMessage, db)

    async def get_room_history(self, room_id: int, *, limit: int = 50) -> List[ChatMessage]:
        """
        Retrieves the last N messages inside a room, eager-loading related user profiles.
        Returns them in ascending (chronological) order.
        """
        # Fetch last limit messages ordered descending (latest first) to slice it correctly
        query = (
            select(self.model)
            .options(joinedload(self.model.user))
            .filter(self.model.room_id == room_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        
        # Reverse list in-memory to deliver them chronologically (oldest to newest)
        messages.reverse()
        return messages
