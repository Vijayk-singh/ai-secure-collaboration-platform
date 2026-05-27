import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket
import redis.asyncio as redis
from app.core.redis import redis_service

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Tracks and manages local active WebSocket sessions mapped to room boundaries.
    """
    def __init__(self) -> None:
        # room_id -> set of active local WebSocket sessions
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: int) -> None:
        """
        Accepts and registers a new WebSocket session locally inside a room.
        """
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)
        logger.debug(f"Local WebSocket connected in Room {room_id}. Total local links: {len(self.active_connections[room_id])}")

    def disconnect(self, websocket: WebSocket, room_id: int) -> None:
        """
        Deregisters a WebSocket session from local active maps on disconnection.
        """
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
            logger.debug(f"Local WebSocket disconnected from Room {room_id}.")

    async def broadcast_local(self, payload: dict, room_id: int) -> None:
        """
        Concurrently broadcasts a JSON payload to all active local connections in a room.
        Automatically purges any dead or disconnected sockets.
        """
        sockets = self.active_connections.get(room_id, set())
        if not sockets:
            return

        dead_sockets = set()
        tasks = []

        # Build concurrent send calls
        for ws in list(sockets):
            async def send_payload(s=ws):
                try:
                    await s.send_json(payload)
                except Exception as e:
                    logger.debug(f"Failed to send local broadcast: {e}")
                    dead_sockets.add(s)

            tasks.append(send_payload())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Cleanup dead connections
        for ws in dead_sockets:
            self.disconnect(ws, room_id)

# Singleton local connection manager
connection_manager = ConnectionManager()

class RedisPubSubListener:
    """
    Background subscriber running a single Redis 'psubscribe' wildcard loop.
    Reads global redis broadcasts and delegates local dispatching to the ConnectionManager.
    """
    def __init__(self) -> None:
        self.task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """
        Spawns the background asyncio loop task.
        """
        self.task = asyncio.create_task(self._listen_loop())
        logger.info("Background Redis Pub/Sub Wildcard Listener started.")

    async def stop(self) -> None:
        """
        Terminates the background loop task.
        """
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            logger.info("Background Redis Pub/Sub Wildcard Listener stopped.")

    async def _listen_loop(self) -> None:
        """
        Subscription loop executing the Redis psubscribe listener.
        """
        # Obtain client pool
        client = redis_service.client
        if client is None:
            redis_service.init_redis()
            client = redis_service.client

        pubsub = client.pubsub()
        # Wildcard topic matches: workspace:{workspace_id}:room:{room_id}
        # Example: workspace:1:room:10
        await pubsub.psubscribe("workspace:*:room:*")

        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]  # e.g., "workspace:1:room:10"
                    data_str = message["data"]

                    try:
                        # Extract room ID dynamically from the channel string
                        parts = channel.split(":")
                        room_id = int(parts[3])
                        payload = json.loads(data_str)

                        # Broadcast locally to all connections on this node
                        await connection_manager.broadcast_local(payload, room_id)
                    except (ValueError, IndexError, json.JSONDecodeError) as e:
                        logger.error(f"Error parsing Pub/Sub message: {e}")
        except asyncio.CancelledError:
            await pubsub.punsubscribe("workspace:*:room:*")
            await pubsub.close()
            raise
        except Exception as e:
            logger.error(f"Redis Pub/Sub subscription encountered an error: {e}")
            # Recover after a brief cooldown delay
            await asyncio.sleep(2)
            self.start()

# Global background listener singleton
pubsub_listener = RedisPubSubListener()
