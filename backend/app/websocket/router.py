"""WebSocket router for real-time notifications endpoint /ws/v1/events."""
import json
import logging
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from app.core.security import decode_access_token
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


@ws_router.websocket("/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Bearer token for authentication"),
) -> None:
    """Authenticated real-time WebSocket channel.

    Accepts token as query param, verifies user identity and role, and enables event streaming and topic subscriptions.
    """
    # 1. Validate JWT Token
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        role = payload.get("role", "citizen")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token subject")
            return
    except Exception as exc:
        logger.warning("WebSocket authentication failed: %s", str(exc))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    # 2. Accept and Register Connection
    await connection_manager.connect(websocket, user_id=user_id, role=role)

    # Send initial welcome confirmation
    try:
        await websocket.send_json({
            "type": "connection.established",
            "user_id": user_id,
            "role": role,
            "message": "Connected to FloodLens AI real-time event bus",
        })
    except Exception:
        connection_manager.disconnect(websocket)
        return

    # 3. Connection Message Loop
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    channel = message.get("channel")
                    if channel:
                        success = connection_manager.subscribe(websocket, channel)
                        await websocket.send_json({
                            "type": "subscription.result",
                            "channel": channel,
                            "status": "subscribed" if success else "forbidden",
                        })

                elif action == "unsubscribe":
                    channel = message.get("channel")
                    if channel:
                        connection_manager.unsubscribe(websocket, channel)
                        await websocket.send_json({
                            "type": "subscription.result",
                            "channel": channel,
                            "status": "unsubscribed",
                        })

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

                else:
                    await websocket.send_json({"type": "ack", "received": action})

            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON format"})

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("Unexpected WebSocket error: %s", str(exc))
        connection_manager.disconnect(websocket)
