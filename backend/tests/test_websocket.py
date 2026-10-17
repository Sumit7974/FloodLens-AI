"""Automated tests for authenticated WebSocket subscriptions and connection management."""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.models.enums import EventType, UserRole
from app.schemas.event import WebSocketEvent
from app.websocket.connection_manager import ConnectionManager


@pytest.mark.asyncio
async def test_connection_manager_channels():
    """Test connection manager channel subscriptions, access controls, and role-based filtering."""
    mgr = ConnectionManager()

    # Create mock WebSocket objects
    class MockWebSocket:
        def __init__(self):
            self.sent = []
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def send_text(self, text: str):
            self.sent.append(text)

    citizen_ws = MockWebSocket()
    authority_ws = MockWebSocket()

    # Connect citizen and authority
    await mgr.connect(citizen_ws, user_id="citizen_1", role="citizen")
    await mgr.connect(authority_ws, user_id="auth_1", role="authority")

    assert citizen_ws.accepted is True
    assert authority_ws.accepted is True

    # Citizen tries to join authority_queue (should be rejected)
    can_join = mgr.subscribe(citizen_ws, "authority_queue")
    assert can_join is False

    # Authority subscribes to specific location channel
    can_join_loc = mgr.subscribe(authority_ws, "locations:dhanusha")
    assert can_join_loc is True

    # Broadcast event to locations:dhanusha
    sample_event = WebSocketEvent(
        event_id="evt_test_001",
        type=EventType.RISK_UPDATED.value,
        timestamp=datetime.now(timezone.utc),
        location_id="dhanusha",
        resource_id="fc_001",
    )
    sent_count = await mgr.broadcast_to_channel("locations:dhanusha", sample_event)
    assert sent_count == 1
    assert len(authority_ws.sent) == 1
    assert len(citizen_ws.sent) == 0

    # Disconnect
    mgr.disconnect(authority_ws)
    mgr.disconnect(citizen_ws)
    assert len(mgr.active_connections) == 0


def test_websocket_endpoint_authentication(client: TestClient, citizen_token: str):
    """Test /ws/v1/events authentication requirements and connection handshake."""
    # 1. Reject without token
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/events") as ws:
            pass

    # 2. Reject with invalid token
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/events?token=invalid_jwt_token_here") as ws:
            pass

    # 3. Successful handshake with valid token
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as ws:
        # First message is connection.established
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"
        assert welcome["role"] == "citizen"

        # Send ping
        ws.send_json({"action": "ping"})
        reply = ws.receive_json()
        assert reply["type"] == "pong"
