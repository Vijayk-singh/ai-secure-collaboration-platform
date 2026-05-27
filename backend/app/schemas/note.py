from typing import List, Optional
import datetime
from pydantic import BaseModel, Field

class TagResponse(BaseModel):
    """
    Response schema returning tag info.
    """
    id: int
    name: str

    model_config = {
        "from_attributes": True
    }

class NoteBase(BaseModel):
    """
    Shared Note properties validated across requests/responses.
    """
    title: str = Field(..., min_length=1, max_length=255, description="Note title")
    content: Optional[str] = Field(None, description="Markdown formatting content")

class NoteCreate(NoteBase):
    """
    Validation schema for creating a note with tags.
    """
    tags: List[str] = Field(default_factory=list, description="Array of tag labels")

class NoteUpdate(BaseModel):
    """
    Validation schema for modifying note content, title, or tags.
    """
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = None
    tags: Optional[List[str]] = None

class NoteResponse(NoteBase):
    """
    Full response payload returning complete note context.
    """
    id: int
    workspace_id: int
    owner_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    tags: List[TagResponse]  # Pre-loads tag relationships safely

    model_config = {
        "from_attributes": True
    }
