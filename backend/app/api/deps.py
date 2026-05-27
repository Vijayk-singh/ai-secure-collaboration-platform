import logging
from typing import AsyncGenerator, List
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.core.exceptions import (
    CredentialException,
    InactiveUserException,
    InsufficientPermissionsException,
)
from app.repositories.user import UserRepository
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Configure standard OAuth2 bearer token extractor
# In OpenAPI / Swagger, this links the authorization button to our login route
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

async def get_user_repository(
    db: AsyncSession = Depends(get_db)
) -> UserRepository:
    """
    Dependency returning an initialized UserRepository class.
    """
    return UserRepository(db)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that decodes the bearer token, retrieves the matching user
    from the database, and validates that their account is active.
    """
    payload = decode_token(token, settings.JWT_SECRET_KEY)
    user_id_str = payload.get("sub")
    token_type = payload.get("type")

    if not user_id_str or token_type != "access":
        raise CredentialException("Could not validate credentials: invalid token signature or type")

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise CredentialException("Could not validate credentials: invalid user claim format")

    user_repo = UserRepository(db)
    user = await user_repo.get(user_id)

    if not user:
        logger.warning(f"Access attempt failed: User with ID '{user_id}' not found.")
        raise CredentialException("User not found")

    if not user.is_active:
        logger.warning(f"Access attempt failed: User with ID '{user_id}' is deactivated.")
        raise InactiveUserException()

    return user

class RoleChecker:
    """
    Dependency-factory that checks whether the currently authenticated user
    possesses the role privileges needed for an endpoint.
    """
    def __init__(self, allowed_roles: List[UserRole]) -> None:
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            logger.warning(
                f"RBAC Denied: User {current_user.id} with role '{current_user.role.value}' "
                f"attempted to access an endpoint requiring {self.allowed_roles}."
            )
            raise InsufficientPermissionsException()
        return current_user
