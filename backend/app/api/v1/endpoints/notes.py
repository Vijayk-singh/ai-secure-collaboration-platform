from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse
from app.schemas.pagination import PageParams, Page
from app.services.note import NoteService
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/workspaces/{workspace_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    workspace_id: int,
    note_in: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a markdown Note inside a workspace, parsing tags (e.g. ["#security", "#collab"]).
    Enforces workspace membership boundaries.
    """
    note_service = NoteService(db)
    return await note_service.create_note(
        workspace_id=workspace_id,
        title=note_in.title,
        content=note_in.content,
        owner_id=current_user.id,
        tag_names=note_in.tags
    )

@router.get("/workspaces/{workspace_id}/notes", response_model=Page[NoteResponse])
async def list_notes(
    workspace_id: int,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    page_params: PageParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists paginated notes inside a workspace.
    Supports tag filtering (e.g. tag=security) and full-text search strings (search=fastapi).
    Returns an envelope including total count and paginated items list.
    """
    note_service = NoteService(db)
    items, total = await note_service.list_notes_in_workspace(
        workspace_id=workspace_id,
        current_user_id=current_user.id,
        skip=page_params.offset,
        limit=page_params.limit,
        tag=tag,
        search=search
    )
    return {
        "items": items,
        "total": total,
        "limit": page_params.limit,
        "offset": page_params.offset
    }

@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves details of a single Note, including its active Tag lists.
    Validates workspace membership.
    """
    note_service = NoteService(db)
    return await note_service.get_note(note_id, current_user.id)

@router.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: int,
    note_in: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Edits note fields (collaborative editing context).
    Allow modifying tags or body content independently.
    """
    note_service = NoteService(db)
    return await note_service.update_note(
        note_id=note_id,
        title=note_in.title,
        content=note_in.content,
        tag_names=note_in.tags,
        current_user_id=current_user.id
    )

@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes a note.
    Restricted to Note Creator or Workspace OWNERS / ADMINS.
    """
    note_service = NoteService(db)
    await note_service.delete_note(note_id, current_user.id)
