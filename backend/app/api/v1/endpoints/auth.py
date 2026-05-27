from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from app.core.database import get_db
from app.core.redis import get_redis
from app.schemas.user import UserCreate, UserResponse
from app.schemas.token import Token, TokenRefreshRequest
from app.services.user import UserService
from app.services.auth import AuthService
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new platform user with MEMBER access.
    """
    user_service = UserService(db)
    return await user_service.register_user(user_in)

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Standard OAuth2 compatible login. Validates credentials and returns
    access and refresh tokens. Fits uvicorn/docs default execution out of the box.
    """
    auth_service = AuthService(db, cache)
    user = await auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password
    )
    access_token, refresh_token = await auth_service.login_user(user)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Session revocation endpoint. Deletes the refresh token from Redis.
    """
    auth_service = AuthService(db, cache)
    await auth_service.logout_user(current_user.id)

@router.post("/refresh", response_model=Token)
async def refresh(
    refresh_in: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
):
    """
    Rotates active token sessions when supplied with a valid, non-revoked refresh token.
    """
    auth_service = AuthService(db, cache)
    access_token, refresh_token = await auth_service.refresh_session(
        refresh_in.refresh_token
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
