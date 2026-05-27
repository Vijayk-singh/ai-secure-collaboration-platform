from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.workspace import Workspace, WorkspaceMember

class WorkspaceRepository(BaseRepository[Workspace]):
    """
    Repository handling database actions for Workspace entities.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Workspace, db)

    async def get_workspaces_for_user(self, user_id: int) -> List[Workspace]:
        """
        Retrieves all workspaces that a specific user is currently subscribed to.
        Filters via WorkspaceMember association table.
        """
        query = (
            select(self.model)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == self.model.id)
            .filter(WorkspaceMember.user_id == user_id)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

class WorkspaceMemberRepository(BaseRepository[WorkspaceMember]):
    """
    Repository handling membership associations inside Workspaces.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(WorkspaceMember, db)

    async def get_by_workspace_and_user(self, workspace_id: int, user_id: int) -> Optional[WorkspaceMember]:
        """
        Retrieves a single membership association record.
        Crucial for fast RBAC permission gate checks.
        """
        query = select(self.model).filter(
            self.model.workspace_id == workspace_id,
            self.model.user_id == user_id
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_members_by_workspace(self, workspace_id: int) -> List[WorkspaceMember]:
        """
        Lists all user profiles currently active inside a target workspace.
        Uses joinedload('user') to load the related User records, preventing N+1 queries.
        """
        query = (
            select(self.model)
            .options(joinedload(self.model.user))
            .filter(self.model.workspace_id == workspace_id)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
