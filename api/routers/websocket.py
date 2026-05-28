"""WebSocket endpoint for live detection streaming."""

import asyncio
import json
import logging
from typing import Set

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, Query
from jose import jwt

from api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["stream"])

# Active WebSocket connections per stream
active_connections: dict[str, Set[WebSocket]] = {}
redis_client: aioredis.Redis | None = None


async def get_redis_client() -> aioredis.Redis:
    """Get Redis client (lazy singleton)."""
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(settings.redis_url)
    return redis_client


async def broadcast_to_stream(stream_id: str, message: dict) -> None:
    """Broadcast message to all connected clients for a stream."""
    if stream_id not in active_connections:
        return

    disconnected = set()
    for connection in active_connections[stream_id]:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            disconnected.add(connection)

    # Remove disconnected clients
    for conn in disconnected:
        active_connections[stream_id].discard(conn)


async def redis_listener(stream_id: str) -> None:
    """Listen to Redis channel and broadcast to WebSocket clients."""
    redis = await get_redis_client()
    channel = f"detections:{stream_id}"

    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to {channel}")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await broadcast_to_stream(stream_id, data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON from Redis: {message['data']}")
                except Exception as e:
                    logger.error(f"Error broadcasting: {e}")
    except Exception as e:
        logger.error(f"Redis listener error: {e}")
    finally:
        await pubsub.unsubscribe(channel)


async def verify_ws_token(token: str) -> bool:
    """Verify JWT token for WebSocket auth."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("user_id") is not None
    except Exception as e:
        logger.warning(f"Invalid token: {e}")
        return False


@router.websocket("/stream/{stream_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    stream_id: str,
    token: str = Query(None),
):
    """WebSocket endpoint for live stream detections.

    Args:
        websocket: WebSocket connection
        stream_id: Stream identifier
        token: JWT token (query param or header)
    """
    # Auth
    if not token:
        token = websocket.headers.get("authorization", "").replace("Bearer ", "")

    if not token or not await verify_ws_token(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        logger.warning(f"WebSocket auth failed for stream={stream_id}")
        return

    await websocket.accept()
    logger.info(f"Client connected to stream={stream_id}")

    # Add to active connections
    if stream_id not in active_connections:
        active_connections[stream_id] = set()
    active_connections[stream_id].add(websocket)

    # Start Redis listener task (per stream, singleton)
    listener_task = None
    if len(active_connections[stream_id]) == 1:
        # First client for this stream; start listener
        listener_task = asyncio.create_task(redis_listener(stream_id))

    try:
        # Keep connection alive; receive heartbeat pings
        while True:
            data = await websocket.receive_text()
            # Echo or handle control messages
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from stream={stream_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Remove from active connections
        active_connections[stream_id].discard(websocket)

        # Cancel listener if no more clients
        if not active_connections[stream_id]:
            if listener_task:
                listener_task.cancel()
            del active_connections[stream_id]
            logger.info(f"Closed stream={stream_id} (no clients)")
