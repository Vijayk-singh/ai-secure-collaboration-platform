import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from app.core.database import async_session_maker
from app.core.redis import redis_service
from app.core.config import settings
from app.core.security import decode_token
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceMemberRepository
from app.services.chat import ChatService
from app.websocket.manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/ws/workspace/{workspace_id}/room/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workspace_id: int,
    room_id: int,
):
    """
    WebSocket endpoint handling authentication handshake, real-time message routing,
    typing indicators, and workspace-wide presence states.
    """
    # 1. JWT Handshake (FastAPI socket query params extraction)
    token = websocket.query_params.get("token")
    if not token:
        logger.warning(f"WS Handshake Rejected: Missing token query parameter for room {room_id}.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Decode token claims using application Access Secret
    payload = decode_token(token, settings.JWT_SECRET_KEY)
    user_id_str = payload.get("sub")
    token_type = payload.get("type")

    if not user_id_str or token_type != "access":
        logger.warning("WS Handshake Rejected: Invalid or expired access token supplied.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_id = int(user_id_str)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Database & Cache Security Gate Checks
    # Sockets run outside standard Depends() lifecycle, so we instantiate transactional sessions manually
    async with async_session_maker() as db:
        user_repo = UserRepository(db)
        member_repo = WorkspaceMemberRepository(db)

        # Confirm user profile exists and is active
        user = await user_repo.get(user_id)
        if not user or not user.is_active:
            logger.warning(f"WS Handshake Rejected: User {user_id} is inactive or deleted.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Confirm workspace membership boundary
        membership = await member_repo.get_by_workspace_and_user(workspace_id, user_id)
        if not membership:
            logger.warning(f"WS Handshake Rejected: User {user_id} is not a member of Workspace {workspace_id}.")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # 3. Connection Accept & Presence Registration
    # Initialize cache client manually
    cache = redis_service.client
    if cache is None:
        redis_service.init_redis()
        cache = redis_service.client

    # Accept connection locally
    await connection_manager.connect(websocket, room_id)

    # Initialize async ChatService manually
    async with async_session_maker() as db:
        chat_service = ChatService(db, cache)
        
        # Register user in online presence Redis Sets
        await chat_service.track_user_connected(workspace_id, user_id)

    # 4. Receive Loop
    try:
        while True:
            # Block waiting for client message
            data_str = await websocket.receive_text()
            
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning(f"WS Parse Error: Received invalid JSON from User {user_id}.")
                continue

            event_type = event.get("type")

            # A. CHAT MESSAGE FLOW
            if event_type == "message":
                content = event.get("content", "").strip()
                if not content:
                    continue

                async with async_session_maker() as db:
                    chat_service = ChatService(db, cache)
                    # Persist message in PostgreSQL
                    msg = await chat_service.persist_message(room_id, user_id, content)

                    # Build serializable broadcast event payload
                    broadcast_event = {
                        "type": "message",
                        "id": msg.id,
                        "room_id": room_id,
                        "user_id": user_id,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat(),
                        "user": {
                            "id": user.id,
                            "email": user.email,
                            "full_name": user.full_name,
                            "role": user.role.value,
                            "is_active": user.is_active,
                            "created_at": user.created_at.isoformat(),
                            "updated_at": user.updated_at.isoformat(),
                        }
                    }

                    # Publish globally to Redis Pub/Sub (broadcasts to all nodes)
                    await chat_service.publish_event(workspace_id, room_id, broadcast_event)

            # B. TYPING INDICATOR FLOW (purely ephemeral, bypasses DB)
            elif event_type == "typing":
                is_typing = event.get("is_typing", False)
                typing_event = {
                    "type": "typing",
                    "user_id": user_id,
                    "full_name": user.full_name or user.email,
                    "is_typing": is_typing,
                }
                
                # Publish globally to Redis Pub/Sub
                async with async_session_maker() as db:
                    chat_service = ChatService(db, cache)
                    await chat_service.publish_event(workspace_id, room_id, typing_event)

    except WebSocketDisconnect:
        logger.info(f"WS Link Disconnected: User {user_id} closed socket in room {room_id}.")
    finally:
        # 5. Connection Teardown & Presence Cleanup
        connection_manager.disconnect(websocket, room_id)
        
        async with async_session_maker() as db:
            chat_service = ChatService(db, cache)
            # Remove user from online Redis Sets, publishing offline status
            await chat_service.track_user_disconnected(workspace_id, user_id)
