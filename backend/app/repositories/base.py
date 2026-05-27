from typing import Generic, TypeVar, Type, Any, Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import Base

# Generic variable bound to SQLAlchemy Declarative Base
ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """
    Abstract Base Repository encapsulating CRUD interfaces.
    """
    def __init__(self, model: Type[ModelType], db: AsyncSession) -> None:
        self.model = model
        self.db = db

    async def get(self, id: Any) -> Optional[ModelType]:
        """
        Fetches a single model instance by its primary key ID.
        """
        result = await self.db.execute(select(self.model).filter(self.model.id == id))
        return result.scalars().first()

    async def get_multi(self, *, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """
        Fetches multiple model records with pagination offsets.
        """
        result = await self.db.execute(select(self.model).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, *, obj_in: Dict[str, Any]) -> ModelType:
        """
        Creates a new model instance and flushes it to the transaction.
        """
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        await self.db.flush()  # Flushes changes to populate generated primary key ids
        return db_obj

    async def update(self, db_obj: ModelType, *, obj_in: Dict[str, Any]) -> ModelType:
        """
        Updates an existing model instance with dictionary changes.
        """
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.db.add(db_obj)
        await self.db.flush()
        return db_obj

    async def delete(self, id: Any) -> Optional[ModelType]:
        """
        Removes a model record by its ID.
        """
        obj = await self.get(id)
        if obj:
            await self.db.delete(obj)
            await self.db.flush()
        return obj
