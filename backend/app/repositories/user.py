from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import BaseRepository
from app.models.user import User

class UserRepository(BaseRepository[User]):
    """
    Concrete Repository handling database access for the User model.
    """
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Queries and returns a User object matched by unique email.
        """
        result = await self.db.execute(select(self.model).filter(self.model.email == email))
        return result.scalars().first()
