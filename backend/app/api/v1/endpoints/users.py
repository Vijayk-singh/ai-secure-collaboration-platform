from fastapi import APIRouter, Depends, status
from app.schemas.user import UserResponse
from app.api.deps import get_current_user, RoleChecker
from app.models.user import User, UserRole

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Returns the currently authenticated user profile context.
    """
    return current_user

@router.get("/admin-only", response_model=dict)
async def test_admin_route(
    current_user: User = Depends(RoleChecker([UserRole.ADMIN]))
):
    """
    Protected test route to verify Role Based Access Control (RBAC) privileges.
    Returns 200 ONLY for admin roles.
    """
    return {
        "status": "success",
        "message": f"Welcome Admin {current_user.full_name or current_user.email}! RBAC validation succeeded."
    }
