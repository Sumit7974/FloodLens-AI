"""WebSocket connection manager supporting authenticated sessions and topic channels."""
import json
import logging
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket
from app.models.enums import UserRole
from app.schemas.event import WebSocketEvent
from app.services.demo_participants import is_authorized_demo_user

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections, token authentication, and topic subscriptions."""

    def __init__(self) -> None:
        # Map websocket -> user_info dict: {"user_id": str, "role": str, "channels": Set[str]}
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        # Map channel -> Set of WebSockets
        self.channel_subscribers: Dict[str, Set[WebSocket]] = {
            "public": set(),
            "alerts": set(),
            "risk_updates": set(),
            "authority_queue": set(),
        }

    async def connect(self, websocket: WebSocket, user_id: str, role: str, email: Optional[str] = None) -> None:
        """Accept connection, store authenticated user identity, and join default channels."""
        await websocket.accept()
        user_info = {
            "user_id": user_id,
            "email": email,
            "role": role,
            "channels": {"public", "alerts", "risk_updates", f"user:{user_id}"},
        }

        # Authority and admin users join the authority queue by default
        if role in (UserRole.AUTHORITY.value, UserRole.ADMIN.value):
            user_info["channels"].add("authority_queue")

        self.active_connections[websocket] = user_info

        for ch in user_info["channels"]:
            if ch not in self.channel_subscribers:
                self.channel_subscribers[ch] = set()
            self.channel_subscribers[ch].add(websocket)

        logger.info(
            "WebSocket connected: user_id=%s, role=%s (active count: %d)",
            user_id,
            role,
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove connection and cleanup all topic subscriptions."""
        user_info = self.active_connections.pop(websocket, None)
        if user_info:
            for ch in user_info.get("channels", set()):
                if ch in self.channel_subscribers:
                    self.channel_subscribers[ch].discard(websocket)
            logger.info("WebSocket disconnected: user_id=%s", user_info.get("user_id"))

    def subscribe(self, websocket: WebSocket, channel: str) -> bool:
        """Subscribe an active connection to a specific channel (e.g. locations:village_01)."""
        if websocket not in self.active_connections:
            return False

        user_info = self.active_connections[websocket]
        user_role = user_info.get("role")
        user_id = user_info.get("user_id")
        user_email = user_info.get("email")

        # 1. Protect authority-only channels (e.g. authority_queue, authority_alerts)
        if channel.startswith("authority") and user_role not in (UserRole.AUTHORITY.value, UserRole.ADMIN.value):
            logger.warning("Unauthorized channel subscription attempt by user %s to %s", user_id, channel)
            return False

        # 2. Protect citizen private direct channels (e.g. user:{user_id})
        if channel.startswith("user:") and channel != f"user:{user_id}":
            logger.warning("User %s attempted unauthorized subscription to channel %s", user_id, channel)
            return False

        # 3. Protect demo_alerts channel: restricted to authority/admin or explicitly authorized demo participants
        if channel == "demo_alerts" and not is_authorized_demo_user(user_id=user_id, email=user_email, role=user_role):
            logger.warning(
                "Unauthorized subscription attempt to demo_alerts by user %s (role=%s). Explicit demo participant authorization required.",
                user_id,
                user_role,
            )
            return False

        if channel not in self.channel_subscribers:
            self.channel_subscribers[channel] = set()

        self.channel_subscribers[channel].add(websocket)
        user_info["channels"].add(channel)
        return True


    def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe an active connection from a channel."""
        if websocket in self.active_connections:
            self.active_connections[websocket]["channels"].discard(channel)
        if channel in self.channel_subscribers:
            self.channel_subscribers[channel].discard(websocket)

    async def send_personal_event(self, websocket: WebSocket, event: WebSocketEvent) -> None:
        """Send an event directly to a specific socket connection."""
        try:
            await websocket.send_text(event.model_dump_json())
        except Exception as exc:
            logger.error("Failed to send WebSocket message: %s", str(exc))
            self.disconnect(websocket)

    async def broadcast_to_channel(self, channel: str, event: WebSocketEvent) -> int:
        """Broadcast an event to all subscribers of a specific channel."""
        subscribers = self.channel_subscribers.get(channel, set()).copy()
        payload = event.model_dump_json()
        count = 0
        for ws in subscribers:
            try:
                await ws.send_text(payload)
                count += 1
            except Exception as exc:
                logger.warning("Error broadcasting to subscriber: %s", str(exc))
                self.disconnect(ws)
        return count

    async def broadcast(self, event: WebSocketEvent) -> int:
        """Broadcast an event to all active connections via the default public channel."""
        return await self.broadcast_to_channel("public", event)

    async def broadcast_to_role(self, role: str, event: WebSocketEvent) -> int:
        """Broadcast an event exclusively to connections with a given role."""
        payload = event.model_dump_json()
        count = 0
        for ws, info in list(self.active_connections.items()):
            if info.get("role") == role:
                try:
                    await ws.send_text(payload)
                    count += 1
                except Exception as exc:
                    logger.warning("Error sending to role %s: %s", role, str(exc))
                    self.disconnect(ws)
        return count

    def get_user_channels(self, websocket: WebSocket) -> Set[str]:
        """Return set of subscribed channels for a specific websocket connection."""
        if websocket in self.active_connections:
            return set(self.active_connections[websocket].get("channels", set()))
        return set()

    async def broadcast_to_user(self, user_id: str, event: WebSocketEvent) -> int:
        """Broadcast an event strictly to a specific user's private channel."""
        return await self.broadcast_to_channel(f"user:{user_id}", event)


# Singleton instance
connection_manager = ConnectionManager()
