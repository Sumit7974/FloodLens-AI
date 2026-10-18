"""WebSocket router for real-time notifications endpoint /ws/v1/events."""
from datetime import datetime, timezone
import json
import logging
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


@ws_router.websocket("/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Bearer token for authentication"),
    db: Session = Depends(get_db),
) -> None:
    """Authenticated real-time WebSocket channel.

    Accepts token as query param, verifies user identity and active database status,
    and enables secure event streaming, topic subscriptions, and REST resync.
    """
    # 1. Validate JWT Token
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token subject")
            return
    except Exception as exc:
        logger.warning("WebSocket authentication failed: %s", str(exc))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    # 2. Validate Active User and Role in Database
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        logger.warning("WebSocket rejected: user %s not found or inactive", user_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User is inactive or not found")
        return

    role = user.role.value

    # 3. Accept and Register Connection
    await connection_manager.connect(websocket, user_id=user.id, role=role)

    # Send initial welcome confirmation with subscribed channels and resync endpoints
    try:
        subscribed = sorted(list(connection_manager.get_user_channels(websocket)))
        await websocket.send_json({
            "type": "connection.established",
            "user_id": user.id,
            "role": role,
            "subscribed_channels": subscribed,
            "resync_endpoints": {
                "alerts": "/api/v1/alerts",
                "assistance": "/api/v1/assistance/mine" if role == UserRole.CITIZEN.value else "/api/v1/assistance",
                "predictions": "/api/v1/predictions/latest",
            },
            "message": "Connected to FloodLens AI real-time event bus",
        })
    except Exception:
        connection_manager.disconnect(websocket)
        return

    # 4. Connection Message Loop
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

                elif action == "resync":
                    # REST resync instructions for client reconnection
                    await websocket.send_json({
                        "type": "resync.instructions",
                        "user_id": user.id,
                        "role": role,
                        "endpoints": {
                            "alerts": "/api/v1/alerts",
                            "assistance": "/api/v1/assistance/mine" if role == UserRole.CITIZEN.value else "/api/v1/assistance",
                            "predictions": "/api/v1/predictions/latest",
                        },
                        "server_time": datetime.now(timezone.utc).isoformat(),
                        "message": "Fetch latest state via REST endpoints to reconcile any missed events.",
                    })

                else:
                    await websocket.send_json({"type": "ack", "received": action})

            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON format"})

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("Unexpected WebSocket error: %s", str(exc))
        connection_manager.disconnect(websocket)
