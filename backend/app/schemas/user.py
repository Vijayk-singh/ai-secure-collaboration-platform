from typing import Optional
import datetime
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole

class UserBase(BaseModel):
    """
    Shared attributes validated across requests and responses.
    """
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=255, description="User's full name")

class UserCreate(UserBase):
    """
    Strict schema validation rules for user registration.
    """
    password: str = Field(..., min_length=8, max_length=100, description="Plaintext password")

class UserUpdate(BaseModel):
    """
    Validation schema for partial profile modifications.
    """
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=100)

class UserResponse(UserBase):
    """
    Safe output schema ensuring password hashes are never exposed.
    """
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    # Tell Pydantic v2 to read properties from SQLAlchemy models automatically
    model_config = {
        "from_attributes": True
    }
