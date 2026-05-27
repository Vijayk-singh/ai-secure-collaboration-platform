from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.models.user import User
from app.core.security import get_password_hash
from app.core.exceptions import EmailExistsException

class UserService:
    """
    Service layer encapsulating registration and profile querying logic.
    """
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    async def register_user(self, user_in: UserCreate) -> User:
        """
        Validates duplicate emails, encrypts the password, and inserts the user record.
        """
        # Ensure user does not already exist
        existing_user = await self.user_repo.get_by_email(user_in.email)
        if existing_user:
            raise EmailExistsException()

        # Build insertion dictionary
        hashed_pw = get_password_hash(user_in.password)
        obj_in = {
            "email": user_in.email,
            "hashed_password": hashed_pw,
            "full_name": user_in.full_name,
        }

        # Create record and commit transaction
        user = await self.user_repo.create(obj_in=obj_in)
        await self.db.commit()
        await self.db.refresh(user)

        # Enqueue welcome email task
        try:
            from app.services.notification import NotificationService
            notification_service = NotificationService()
            await notification_service.queue_welcome_email(user.email, user.full_name)
        except Exception as e:
            # Prevent failures in task queuing from rolling back user registration
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to queue welcome email task for {user.email}: {e}")

        return user

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Retrieves a user profile by ID.
        """
        return await self.user_repo.get(user_id)
