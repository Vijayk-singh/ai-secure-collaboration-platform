import logging
from typing import Optional, Tuple
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user import UserRepository
from app.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.config import settings
from app.core.exceptions import InvalidCredentialsException, CredentialException

logger = logging.getLogger(__name__)

class AuthService:
    """
    Service layer orchestrating identity authentication, session creation,
    token renewal (rotation), and session revocation (logout).
    """
    def __init__(self, db: AsyncSession, cache: redis.Redis) -> None:
        self.db = db
        self.cache = cache
        self.user_repo = UserRepository(db)

    async def authenticate_user(self, email: str, password: str) -> User:
        """
        Validates credentials and returns the User object if successful.
        """
        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.warning(f"Authentication failed: User with email '{email}' not found.")
            raise InvalidCredentialsException()

        if not verify_password(password, user.hashed_password):
            logger.warning(f"Authentication failed: Invalid password supplied for email '{email}'.")
            raise InvalidCredentialsException()

        return user

    async def login_user(self, user: User) -> Tuple[str, str]:
        """
        Generates access and refresh tokens, caching the refresh token in Redis.
        Returns (access_token, refresh_token).
        """
        user_id_str = str(user.id)
        
        access_token = create_access_token(subject=user_id_str)
        refresh_token = create_refresh_token(subject=user_id_str)

        # Store refresh token in Redis with session TTL
        redis_key = f"refresh_token:{user_id_str}"
        ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        
        await self.cache.setex(name=redis_key, time=ttl_seconds, value=refresh_token)
        logger.info(f"User {user.id} logged in. Active refresh session saved in cache.")

        return access_token, refresh_token

    async def logout_user(self, user_id: int) -> None:
        """
        Deletes the user's active refresh session key, invalidating active sessions.
        """
        redis_key = f"refresh_token:{user_id}"
        await self.cache.delete(redis_key)
        logger.info(f"User {user_id} logged out. Active refresh session deleted from cache.")

    async def refresh_session(self, refresh_token: str) -> Tuple[str, str]:
        """
        Decodes incoming refresh token, checks whitelist state in Redis,
        performs security rotation, and returns a new (access_token, refresh_token) pair.
        """
        # Decode claims using refresh secret
        payload = decode_token(refresh_token, settings.JWT_REFRESH_SECRET_KEY)
        user_id_str = payload.get("sub")
        token_type = payload.get("type")

        if not user_id_str or token_type != "refresh":
            logger.warning("Token refresh failed: Invalid token claims presented.")
            raise CredentialException("Invalid refresh token")

        # Check if this token matches the one stored in Redis (whitelist state)
        redis_key = f"refresh_token:{user_id_str}"
        cached_token = await self.cache.get(redis_key)

        if not cached_token or cached_token != refresh_token:
            logger.warning(f"Token refresh failed: Presented refresh token for user {user_id_str} is revoked or expired.")
            raise CredentialException("Refresh token expired or revoked")

        # Fetch matching user profiles
        try:
            user_id = int(user_id_str)
        except ValueError:
            raise CredentialException("Invalid user identity claim")

        user = await self.user_repo.get(user_id)
        if not user or not user.is_active:
            logger.warning(f"Token refresh failed: User {user_id_str} is inactive or does not exist.")
            raise CredentialException("User is inactive or deleted")

        # Perform Refresh Token Rotation (RTR):
        # Create brand-new access and refresh tokens, saving the new refresh token in Redis
        new_access_token = create_access_token(subject=user_id_str)
        new_refresh_token = create_refresh_token(subject=user_id_str)

        ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await self.cache.setex(name=redis_key, time=ttl_seconds, value=new_refresh_token)
        logger.info(f"Refresh token rotated successfully for user {user_id}.")

        return new_access_token, new_refresh_token
