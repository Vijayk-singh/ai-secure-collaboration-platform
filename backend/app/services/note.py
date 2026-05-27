import logging
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.note import NoteRepository, TagRepository
from app.repositories.workspace import WorkspaceMemberRepository
from app.models.note import Note
from app.models.workspace import WorkspaceRole
from app.core.exceptions import InsufficientPermissionsException

logger = logging.getLogger(__name__)

class NoteService:
    """
    Service layer coordinating Note operations, tag resolution,
    collaborative edits, and deletion authorization.
    """
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.note_repo = NoteRepository(db)
        self.tag_repo = TagRepository(db)
        self.member_repo = WorkspaceMemberRepository(db)

    async def _verify_workspace_membership(self, workspace_id: int, user_id: int) -> None:
        """
        Private helper confirming if a user belongs to a target workspace.
        """
        membership = await self.member_repo.get_by_workspace_and_user(workspace_id, user_id)
        if not membership:
            logger.warning(f"Workspace Boundary Violated: User {user_id} tried to query Workspace {workspace_id} notes.")
            raise InsufficientPermissionsException("You must belong to this workspace to perform note operations.")

    async def create_note(
        self,
        workspace_id: int,
        title: str,
        content: Optional[str],
        owner_id: int,
        tag_names: List[str]
    ) -> Note:
        """
        Creates a markdown Note inside a workspace, dynamically parsing and linking Tags.
        """
        # 1. Confirm membership
        await self._verify_workspace_membership(workspace_id, owner_id)

        # 2. Resolve tags (idempotently fetch or create Tag instances)
        tags_instances = []
        for name in tag_names:
            if name.strip():
                tag = await self.tag_repo.get_or_create_by_name(name)
                tags_instances.append(tag)

        # 3. Create Note record with in-memory tags mapped directly in constructor
        note_in = {
            "title": title,
            "content": content,
            "workspace_id": workspace_id,
            "owner_id": owner_id,
            "tags": tags_instances,
        }
        note = await self.note_repo.create(obj_in=note_in)
        
        await self.db.commit()
        # Do not call db.refresh(note) to preserve the in-memory populated tags relationship,
        # avoiding async lazy-loading greenlet errors during Pydantic serialization.
        
        # Enqueue background semantic chunking and embedding generation
        try:
            from app.workers.task_queue import TaskQueue
            from app.core.redis import redis_service
            if redis_service.client:
                queue = TaskQueue(redis_service.client)
                await queue.enqueue(name="generate_note_embeddings", args=[note.id])
        except Exception as e:
            logger.warning(f"Failed to enqueue note embedding task for note {note.id}: {e}")

        logger.info(f"Note '{title}' (ID: {note.id}) created inside Workspace {workspace_id} by User {owner_id}.")
        return note

    async def get_note(self, note_id: int, current_user_id: int) -> Note:
        """
        Retrieves a note eager-loading its tags, validating workspace membership.
        """
        note = await self.note_repo.get_note_with_tags(note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found."
            )

        # Enforce workspace security lookup
        await self._verify_workspace_membership(note.workspace_id, current_user_id)
        return note

    async def list_notes_in_workspace(
        self,
        workspace_id: int,
        current_user_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Note], int]:
        """
        Lists paginated, filtered, and searched notes scoped inside a workspace.
        Enforces membership checks.
        """
        await self._verify_workspace_membership(workspace_id, current_user_id)
        return await self.note_repo.get_paginated_notes(
            workspace_id,
            skip=skip,
            limit=limit,
            tag=tag,
            search=search
        )

    async def update_note(
        self,
        note_id: int,
        title: Optional[str],
        content: Optional[str],
        tag_names: Optional[List[str]],
        current_user_id: int
    ) -> Note:
        """
        Edits note title or markdown content (collaborative wiki editing).
        """
        note = await self.note_repo.get_note_with_tags(note_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")

        # Verify editing permission (must be member of this workspace)
        await self._verify_workspace_membership(note.workspace_id, current_user_id)

        # Apply basic updates
        updates = {}
        if title is not None:
            updates["title"] = title
        if content is not None:
            updates["content"] = content

        note = await self.note_repo.update(note, obj_in=updates)

        # Apply tag updates (re-mapping tag relations entirely if provided)
        if tag_names is not None:
            tags_instances = []
            for name in tag_names:
                if name.strip():
                    tag = await self.tag_repo.get_or_create_by_name(name)
                    tags_instances.append(tag)
            note.tags = tags_instances

        await self.db.commit()
        await self.db.refresh(note)
        
        # Enqueue background semantic chunking and embedding generation
        try:
            from app.workers.task_queue import TaskQueue
            from app.core.redis import redis_service
            if redis_service.client:
                queue = TaskQueue(redis_service.client)
                await queue.enqueue(name="generate_note_embeddings", args=[note.id])
        except Exception as e:
            logger.warning(f"Failed to enqueue note embedding task for note {note.id}: {e}")

        logger.info(f"Note {note_id} updated by User {current_user_id}.")
        return note

    async def delete_note(self, note_id: int, current_user_id: int) -> None:
        """
        Deletes a note.
        Enforces a robust permission check: Deletion is restricted to the note owner
        or a user with OWNER or ADMIN privileges inside the workspace.
        """
        note = await self.note_repo.get(note_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")

        # Check inviter membership role
        membership = await self.member_repo.get_by_workspace_and_user(note.workspace_id, current_user_id)
        if not membership:
            raise InsufficientPermissionsException("You do not belong to this workspace.")

        # Auth Deletion check: owner OR workspace admin/owner role
        if note.owner_id != current_user_id and membership.role not in [WorkspaceRole.OWNER, WorkspaceRole.ADMIN]:
            logger.warning(f"Delete Blocked: Member {current_user_id} tried to delete Note {note_id} owned by {note.owner_id}.")
            raise InsufficientPermissionsException("Only the note owner or workspace admins can delete this note.")

        await self.note_repo.delete(note.id)
        await self.db.commit()
        logger.info(f"Note {note_id} deleted by User {current_user_id}.")
