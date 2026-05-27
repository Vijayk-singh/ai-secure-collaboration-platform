from typing import Optional
import datetime
from pydantic import BaseModel, Field, EmailStr
from app.models.workspace import WorkspaceRole
from app.schemas.user import UserResponse

class WorkspaceBase(BaseModel):
    """
    Shared Workspace properties validated across requests/responses.
    """
    name: str = Field(..., min_length=1, max_length=255, description="Name of the workspace")
    description: Optional[str] = Field(None, max_length=1000, description="Optional workspace summary")

class WorkspaceCreate(WorkspaceBase):
    """
    Validation schema for creating workspaces.
    """
    pass

class WorkspaceResponse(WorkspaceBase):
    """
    Response schema returning workspace info.
    """
    id: int
    owner_id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {
        "from_attributes": True
    }

class WorkspaceMemberAdd(BaseModel):
    """
    Validation schema to add a user to a workspace.
    """
    email: EmailStr = Field(..., description="Email of the user to invite")
    role: WorkspaceRole = Field(WorkspaceRole.MEMBER, description="Assigned workspace role")

class WorkspaceMemberResponse(BaseModel):
    """
    Response schema representing workspace membership links.
    """
    id: int
    workspace_id: int
    user_id: int
    role: WorkspaceRole
    created_at: datetime.datetime
    user: UserResponse  # Serializes details of the member user profile

    model_config = {
        "from_attributes": True
    }
