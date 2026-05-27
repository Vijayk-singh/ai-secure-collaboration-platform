from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.core.database import get_db
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
)
from app.services.workspace import WorkspaceService
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    workspace_in: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new Workspace.
    Enrolls the creator instantly as the OWNER.
    """
    workspace_service = WorkspaceService(db)
    return await workspace_service.create_workspace(
        name=workspace_in.name,
        description=workspace_in.description,
        owner_id=current_user.id
    )

@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all Workspaces the authenticated user has joined.
    """
    workspace_service = WorkspaceService(db)
    return await workspace_service.list_user_workspaces(current_user.id)

@router.post("/{workspace_id}/members", response_model=WorkspaceMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    workspace_id: int,
    member_in: WorkspaceMemberAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Invites and registers a new member inside a workspace.
    Restricted to inviting user holding OWNER or ADMIN role inside this workspace.
    """
    workspace_service = WorkspaceService(db)
    return await workspace_service.add_workspace_member(
        workspace_id=workspace_id,
        invite_email=member_in.email,
        role=member_in.role,
        current_user_id=current_user.id
    )

@router.get("/{workspace_id}/members", response_model=List[WorkspaceMemberResponse])
async def list_members(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists all active members in a workspace.
    Enforces membership validation checks (must belong to this workspace).
    """
    workspace_service = WorkspaceService(db)
    return await workspace_service.list_workspace_members(workspace_id, current_user.id)
