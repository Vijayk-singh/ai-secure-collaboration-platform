import logging
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.workspace import WorkspaceRepository, WorkspaceMemberRepository
from app.repositories.user import UserRepository
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole
from app.core.exceptions import InsufficientPermissionsException

logger = logging.getLogger(__name__)

class WorkspaceService:
    """
    Service layer coordinating Workspace instantiation, membership mapping,
    and contextual permission checks.
    """
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.workspace_repo = WorkspaceRepository(db)
        self.member_repo = WorkspaceMemberRepository(db)
        self.user_repo = UserRepository(db)

    async def create_workspace(self, name: str, description: Optional[str], owner_id: int) -> Workspace:
        """
        Creates a Workspace record and automatically enrolls the creator as WorkspaceRole.OWNER.
        """
        # Create workspace entity
        workspace_in = {
            "name": name,
            "description": description,
            "owner_id": owner_id,
        }
        workspace = await self.workspace_repo.create(obj_in=workspace_in)
        
        # Enroll owner as active member automatically
        member_in = {
            "workspace_id": workspace.id,
            "user_id": owner_id,
            "role": WorkspaceRole.OWNER,
        }
        await self.member_repo.create(obj_in=member_in)
        
        # Commit transaction safely
        await self.db.commit()
        await self.db.refresh(workspace)
        
        logger.info(f"Workspace '{name}' (ID: {workspace.id}) created by User {owner_id}.")
        return workspace

    async def list_user_workspaces(self, user_id: int) -> List[Workspace]:
        """
        Returns all workspaces that a specific user has joined.
        """
        return await self.workspace_repo.get_workspaces_for_user(user_id)

    async def add_workspace_member(
        self,
        workspace_id: int,
        invite_email: str,
        role: WorkspaceRole,
        current_user_id: int
    ) -> WorkspaceMember:
        """
        Adds a new user to a workspace.
        Ensures the inviting user holds OWNER or ADMIN privileges inside this workspace.
        """
        # 1. Verify current user's inviter credentials
        inviter_membership = await self.member_repo.get_by_workspace_and_user(workspace_id, current_user_id)
        if not inviter_membership or inviter_membership.role not in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]:
            logger.warning(f"Invite Denied: User {current_user_id} tried to add member to workspace {workspace_id} without permission.")
            raise InsufficientPermissionsException("Only owners or admins can add members to this workspace.")

        # 2. Resolve invited email
        invited_user = await self.user_repo.get_by_email(invite_email)
        if not invited_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{invite_email}' not found."
            )

        # 3. Check if membership link is already established
        existing_membership = await self.member_repo.get_by_workspace_and_user(workspace_id, invited_user.id)
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this workspace."
            )

        # 4. Create membership link
        member_in = {
            "workspace_id": workspace_id,
            "user_id": invited_user.id,
            "role": role,
        }
        membership = await self.member_repo.create(obj_in=member_in)
        await self.db.commit()
        membership.user = invited_user  # Set in-memory relation to prevent async lazy loading error

        # Enqueue workspace invite email task
        try:
            from app.services.notification import NotificationService
            workspace = await self.workspace_repo.get(workspace_id)
            inviter_user = await self.user_repo.get(current_user_id)
            if workspace and inviter_user:
                notification_service = NotificationService()
                await notification_service.queue_workspace_invite(
                    email=invited_user.email,
                    workspace_name=workspace.name,
                    inviter_name=inviter_user.full_name or inviter_user.email
                )
        except Exception as e:
            # Prevent failures in task queuing from rolling back workspace member additions
            logger.warning(f"Failed to queue workspace invite email for {invited_user.email}: {e}")
        
        logger.info(f"User {invited_user.id} added to Workspace {workspace_id} as '{role.value}' by User {current_user_id}.")
        return membership

    async def list_workspace_members(self, workspace_id: int, current_user_id: int) -> List[WorkspaceMember]:
        """
        Lists all members of a workspace.
        Enforces membership checks (current user must belong to this workspace).
        """
        # Enforce security lookup
        caller_membership = await self.member_repo.get_by_workspace_and_user(workspace_id, current_user_id)
        if not caller_membership:
            logger.warning(f"Roster Request Denied: Non-member {current_user_id} requested members of Workspace {workspace_id}.")
            raise InsufficientPermissionsException("You must be a member of this workspace to list its members.")

        return await self.member_repo.get_members_by_workspace(workspace_id)
