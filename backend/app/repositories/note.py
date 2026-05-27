from typing import List, Optional, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.note import Note, Tag

class NoteRepository(BaseRepository[Note]):
    """
    Repository handling database actions for Note entities.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Note, db)

    async def get_note_with_tags(self, note_id: int) -> Optional[Note]:
        """
        Fetches a single Note instance, eager-loading related Tags.
        """
        query = (
            select(self.model)
            .options(selectinload(self.model.tags))
            .filter(self.model.id == note_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_paginated_notes(
        self,
        workspace_id: int,
        *,
        skip: int = 0,
        limit: int = 20,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Note], int]:
        """
        Returns a paginated list of notes scoped to a workspace, along with the total count.
        Supports case-insensitive full-text filter on title/content and tag matching.
        """
        # Base filter scoped strictly inside this workspace
        base_filter = [self.model.workspace_id == workspace_id]
        
        # Apply search string matching across title OR content body
        if search:
            pattern = f"%{search}%"
            base_filter.append(
                or_(
                    self.model.title.ilike(pattern),
                    self.model.content.ilike(pattern)
                )
            )

        # Build execution list query
        query = select(self.model).filter(*base_filter)
        
        # Build counting query sharing the exact same query parameters
        count_query = select(func.count(self.model.id)).filter(*base_filter)

        # Apply tag filter joins
        if tag:
            cleaned_tag = tag.strip().lower()
            if cleaned_tag.startswith("#"):
                cleaned_tag = cleaned_tag[1:]
            
            # Join tags inside queries
            query = query.join(self.model.tags).filter(Tag.name == cleaned_tag)
            count_query = count_query.join(self.model.tags).filter(Tag.name == cleaned_tag)

        # 1. Fetch total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # 2. Fetch paginated records using selectinload (O(1) queries for relationships)
        # Order by newly created notes first
        query = (
            query.options(selectinload(self.model.tags))
            .order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

class TagRepository(BaseRepository[Tag]):
    """
    Repository handling database actions for Tag entities.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Tag, db)

    async def get_by_name(self, name: str) -> Optional[Tag]:
        """
        Retrieves a Tag by its clean lowercase name.
        """
        result = await self.db.execute(
            select(self.model).filter(self.model.name == name.strip().lower())
        )
        return result.scalars().first()

    async def get_or_create_by_name(self, name: str) -> Tag:
        """
        Idempotent fetch or insert operation for Tag tags.
        Guarantees lowercase tag string formats, stripping leading hashtag characters.
        """
        cleaned_name = name.strip().lower()
        if cleaned_name.startswith("#"):
            cleaned_name = cleaned_name[1:]

        # Idempotent lookup
        tag = await self.get_by_name(cleaned_name)
        if not tag:
            tag = await self.create(obj_in={"name": cleaned_name})
        return tag
