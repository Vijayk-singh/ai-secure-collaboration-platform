from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from typing import List
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.chat import ChatRoomCreate, ChatRoomResponse, ChatMessageResponse
from app.services.chat import ChatService
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/workspaces/{workspace_id}/rooms", response_model=ChatRoomResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_room(
    workspace_id: int,
    room_in: ChatRoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Creates a scoped Chat Room inside a workspace.
    Enforces workspace membership checks.
    """
    chat_service = ChatService(db, cache)
    return await chat_service.create_room(
        workspace_id=workspace_id,
        name=room_in.name,
        current_user_id=current_user.id
    )

@router.get("/workspaces/{workspace_id}/rooms", response_model=List[ChatRoomResponse])
async def list_chat_rooms(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Lists all chat rooms created inside a workspace.
    Enforces workspace membership checks.
    """
    chat_service = ChatService(db, cache)
    return await chat_service.list_rooms(workspace_id, current_user.id)

@router.get("/rooms/{room_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_history(
    room_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Retrieves the last N messages (catch-up history) inside a chat room.
    Eager-loads author profiles. Enforces membership verification.
    """
    chat_service = ChatService(db, cache)
    return await chat_service.get_room_history(
        room_id=room_id,
        current_user_id=current_user.id,
        limit=limit
    )
