from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, users, workspaces, notes, chat, jobs, ai

api_router = APIRouter()

# Register endpoint sub-routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(notes.router, tags=["notes"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
