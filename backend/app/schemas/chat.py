import datetime
from pydantic import BaseModel, Field
from app.schemas.user import UserResponse

class ChatRoomBase(BaseModel):
    """
    Shared ChatRoom properties validated across requests/responses.
    """
    name: str = Field(..., min_length=1, max_length=255, description="Name of the chat room")

class ChatRoomCreate(ChatRoomBase):
    """
    Validation schema for creating chat rooms.
    """
    pass

class ChatRoomResponse(ChatRoomBase):
    """
    Response schema returning chat room context.
    """
    id: int
    workspace_id: int
    created_at: datetime.datetime

    model_config = {
        "from_attributes": True
    }

class ChatMessageResponse(BaseModel):
    """
    Response schema returning full message details including author profile.
    """
    id: int
    room_id: int
    user_id: int
    content: str
    created_at: datetime.datetime
    user: UserResponse  # Pre-loads and serializes message author details

    model_config = {
        "from_attributes": True
    }
