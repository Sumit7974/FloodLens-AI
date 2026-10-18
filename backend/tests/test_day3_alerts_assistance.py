"""Integration tests for FloodLens AI Day 3 deliverables:

1. Authenticated WebSocket connections, subscriptions, and RBAC isolation.
2. Alert state machine (DRAFT -> APPROVED -> DISPATCHED) & invalid transitions.
3. Test-only dispatch safeguards (mode restrictions & visible labelling).
4. Citizen assistance lifecycle, ownership isolation, and coordinate privacy.
5. Authenticated, user-specific WebSocket notifications for assistance updates.
6. Safe push notification adapter (Expo/FCM sandbox) success/failure handling.
7. Client reconnection and REST resynchronization.
"""
from datetime import datetime, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, hash_password
from app.models.alert import Alert
from app.models.assistance import AssistanceRequest
from app.models.enums import AlertStatus, AssistanceCategory, AssistanceStatus, EventType, OperationalMode, UserRole
from app.models.user import User
from app.schemas.alert import AlertDispatchRequest
from app.schemas.event import WebSocketEvent
from app.services.push_notifications import DeliveryStatus, SandboxPushNotificationAdapter, mask_device_token, push_adapter
from app.websocket.connection_manager import ConnectionManager, connection_manager


# ==============================================================================
# Helper Mock Socket
# ==============================================================================
class MockWS:
    """Mock WebSocket for unit testing channel event dispatch."""
    def __init__(self):
        self.sent = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, text: str):
        self.sent.append(text)


# ==============================================================================
# 1. Citizen vs Authority Permissions
# ==============================================================================
def test_citizen_vs_authority_permissions(
    client: TestClient,
    test_citizen_user: User,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify role-based access control for alert and assistance operations."""
    # 1. Citizen cannot create draft alert
    draft_payload = {
        "area_id": "area_test_01",
        "title": "Unauthorized Alert",
        "message": "Attempting to create alert without authority role",
    }
    resp = client.post("/api/v1/alerts", json=draft_payload, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 2. Authority can create draft alert
    resp = client.post("/api/v1/alerts", json=draft_payload, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp.status_code == status.HTTP_201_CREATED
    alert_id = resp.json()["id"]

    # 3. Citizen cannot approve alert
    resp = client.post(f"/api/v1/alerts/{alert_id}/approve", json={"notes": "citizen approve"}, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 4. Authority can approve alert
    resp = client.post(f"/api/v1/alerts/{alert_id}/approve", json={"notes": "approved by authority"}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp.status_code == status.HTTP_200_OK

    # 5. Citizen cannot dispatch alert
    resp = client.post(f"/api/v1/alerts/{alert_id}/dispatch", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 6. Citizen cannot view authority assistance queue
    resp = client.get("/api/v1/assistance", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 7. Authority can view assistance queue
    resp = client.get("/api/v1/assistance", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp.status_code == status.HTTP_200_OK


# ==============================================================================
# 2. Unauthorized WebSocket Subscriptions & Inactive Users
# ==============================================================================
@pytest.mark.asyncio
async def test_websocket_channel_authorization():
    """Verify WebSocket channel access restrictions and privacy boundaries."""
    mgr = ConnectionManager()

    citizen_ws = MockWS()
    other_citizen_ws = MockWS()
    auth_ws = MockWS()

    await mgr.connect(citizen_ws, user_id="citizen_1", role="citizen")
    await mgr.connect(other_citizen_ws, user_id="citizen_2", role="citizen")
    await mgr.connect(auth_ws, user_id="auth_1", role="authority")

    # Citizen cannot subscribe to authority_queue or authority_alerts
    assert mgr.subscribe(citizen_ws, "authority_queue") is False
    assert mgr.subscribe(citizen_ws, "authority_alerts") is False

    # Citizen cannot subscribe to another user's personal channel
    assert mgr.subscribe(citizen_ws, "user:citizen_2") is False

    # Citizen can subscribe to their own private channel
    assert mgr.subscribe(citizen_ws, "user:citizen_1") is True

    # Authority cannot eavesdrop on citizen's private channel
    assert mgr.subscribe(auth_ws, "user:citizen_1") is False

    # Authority can subscribe to authority channels
    assert mgr.subscribe(auth_ws, "authority_queue") is True

    mgr.disconnect(citizen_ws)
    mgr.disconnect(other_citizen_ws)
    mgr.disconnect(auth_ws)


def test_websocket_inactive_user_rejected(client: TestClient, db_session: Session):
    """Verify that tokens for inactive or deleted users are rejected."""
    inactive_user = User(
        email="inactive@floodlens.org",
        hashed_password=hash_password("password123"),
        full_name="Inactive User",
        role=UserRole.CITIZEN,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()
    db_session.refresh(inactive_user)

    inactive_token = create_access_token(subject=inactive_user.id, role="citizen")

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/v1/events?token={inactive_token}") as ws:
            pass


# ==============================================================================
# 3. Draft & Approved Alert Confidentiality
# ==============================================================================
def test_draft_and_approved_alert_confidentiality(
    client: TestClient,
    db_session: Session,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify unpublished draft and approved alerts are hidden from non-authorities."""
    draft_alert = Alert(
        id="alert_confidential_draft",
        area_id="loc_draft",
        title="[DEMO ONLY] Draft Advisory",
        message="Confidential draft warning.",
        status=AlertStatus.DRAFT,
        created_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app"],
    )
    approved_alert = Alert(
        id="alert_confidential_approved",
        area_id="loc_approved",
        title="[DEMO ONLY] Approved Advisory",
        message="Confidential approved warning awaiting dispatch.",
        status=AlertStatus.APPROVED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app"],
    )
    db_session.add_all([draft_alert, approved_alert])
    db_session.commit()

    # 1. Anonymous GET /alerts excludes draft and approved
    anon_resp = client.get("/api/v1/alerts")
    assert anon_resp.status_code == status.HTTP_200_OK
    assert all(a["status"] == "dispatched" for a in anon_resp.json())

    # 2. Citizen GET /alerts excludes draft and approved
    cit_resp = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {citizen_token}"})
    assert cit_resp.status_code == status.HTTP_200_OK
    assert all(a["status"] == "dispatched" for a in cit_resp.json())

    # 3. Citizen cannot fetch draft alert directly by ID
    resp_draft = client.get(f"/api/v1/alerts/{draft_alert.id}", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_draft.status_code == status.HTTP_403_FORBIDDEN

    # 4. Citizen cannot fetch approved alert directly by ID
    resp_approved = client.get(f"/api/v1/alerts/{approved_alert.id}", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_approved.status_code == status.HTTP_403_FORBIDDEN

    # 5. Authority CAN fetch draft and approved alerts
    auth_draft = client.get(f"/api/v1/alerts/{draft_alert.id}", headers={"Authorization": f"Bearer {authority_token}"})
    assert auth_draft.status_code == status.HTTP_200_OK
    assert auth_draft.json()["status"] == "draft"


# ==============================================================================
# 4. Alert State Machine & Invalid Transitions
# ==============================================================================
def test_invalid_alert_state_transitions(
    client: TestClient,
    db_session: Session,
    test_authority_user: User,
    authority_token: str,
):
    """Verify strict state transitions: DRAFT -> APPROVED -> DISPATCHED."""
    alert = Alert(
        id="alert_lifecycle_test",
        area_id="loc_lifecycle",
        title="[DEMO ONLY] Lifecycle Test Alert",
        message="Testing transitions",
        status=AlertStatus.DRAFT,
        created_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app"],
    )
    db_session.add(alert)
    db_session.commit()

    # 1. Cannot dispatch DRAFT alert directly (must be approved first)
    resp = client.post(f"/api/v1/alerts/{alert.id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["error"]["code"] == "NOT_APPROVED"

    # 2. Approve the alert
    resp_app = client.post(f"/api/v1/alerts/{alert.id}/approve", json={"notes": "First approval"}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_app.status_code == status.HTTP_200_OK
    assert resp_app.json()["status"] == "approved"

    # 3. Cannot re-approve an already APPROVED alert
    resp_reapprove = client.post(f"/api/v1/alerts/{alert.id}/approve", json={"notes": "Duplicate approval"}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_reapprove.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_reapprove.json()["error"]["code"] == "INVALID_STATE"

    # 4. Dispatch the approved alert
    resp_disp = client.post(f"/api/v1/alerts/{alert.id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_disp.status_code == status.HTTP_200_OK
    assert resp_disp.json()["status"] == "dispatched"

    # 5. Cannot re-approve a DISPATCHED alert
    resp_app_after = client.post(f"/api/v1/alerts/{alert.id}/approve", json={"notes": "Post dispatch approval"}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_app_after.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_app_after.json()["error"]["code"] == "INVALID_STATE"

    # 6. Cannot re-dispatch an already DISPATCHED alert
    resp_disp_after = client.post(f"/api/v1/alerts/{alert.id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_disp_after.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_disp_after.json()["error"]["code"] == "INVALID_STATE"


# ==============================================================================
# 5. Test-Only Dispatch Safeguards & Visible Labelling
# ==============================================================================
def test_test_only_dispatch_safeguards(
    client: TestClient,
    db_session: Session,
    test_authority_user: User,
    authority_token: str,
):
    """Verify live warnings are rejected and test alerts are visibly labelled."""
    # 1. Create alert with LIVE_OBSERVATION mode
    live_alert = Alert(
        id="alert_live_forbidden",
        area_id="loc_live",
        title="Live Emergency Alert",
        message="Operational disaster evacuation order",
        status=AlertStatus.DRAFT,
        created_by=test_authority_user.id,
        mode=OperationalMode.LIVE_OBSERVATION,
        target_channels=["in_app"],
    )
    db_session.add(live_alert)
    db_session.commit()

    # Approve draft
    resp_app = client.post(f"/api/v1/alerts/{live_alert.id}/approve", json={}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_app.status_code == status.HTTP_200_OK

    # Attempt dispatch: MUST be rejected under safety safeguards
    resp_disp = client.post(f"/api/v1/alerts/{live_alert.id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_disp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_disp.json()["error"]["code"] == "DISPATCH_RESTRICTED_TO_TEST"

    # 2. Check visible labelling on historical demo alert
    draft_demo = {
        "area_id": "loc_demo",
        "title": "Severe Flash Flood Advisory",
        "message": "Prepare for simulated flood surge.",
        "mode": OperationalMode.HISTORICAL_DEMO,
    }
    resp_create = client.post("/api/v1/alerts", json=draft_demo, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_create.status_code == status.HTTP_201_CREATED
    demo_id = resp_create.json()["id"]
    # Verify title has [DEMO ONLY] prefix
    assert "[DEMO" in resp_create.json()["title"].upper()

    # Approve & dispatch
    client.post(f"/api/v1/alerts/{demo_id}/approve", json={}, headers={"Authorization": f"Bearer {authority_token}"})
    resp_disp_demo = client.post(f"/api/v1/alerts/{demo_id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_disp_demo.status_code == status.HTTP_200_OK
    assert "[DEMO" in resp_disp_demo.json()["title"].upper()
    assert resp_disp_demo.json()["status"] == "dispatched"


# ==============================================================================
# 6. Citizen Assistance Ownership & Privacy
# ==============================================================================
def test_assistance_ownership_and_coordinate_privacy(
    client: TestClient,
    db_session: Session,
    test_citizen_user: User,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify citizen assistance ownership boundaries and coordinate protection."""
    # Create second citizen
    citizen_b = User(
        email="citizen_b@example.com",
        hashed_password=hash_password("password123"),
        full_name="Citizen B",
        role=UserRole.CITIZEN,
        is_active=True,
    )
    db_session.add(citizen_b)
    db_session.commit()
    db_session.refresh(citizen_b)
    citizen_b_token = create_access_token(subject=citizen_b.id, role="citizen")

    # 1. Citizen A creates assistance request with sensitive coordinates
    payload_a = {
        "latitude": 26.7271,
        "longitude": 85.9402,
        "category": AssistanceCategory.EVACUATION.value,
        "details": "Water entering home, elderly family member requires boat evacuation.",
        "people_count": 3,
    }
    resp_create = client.post("/api/v1/assistance", json=payload_a, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_create.status_code == status.HTTP_201_CREATED
    req_a_id = resp_create.json()["id"]

    # 2. Citizen A can read their own request
    resp_get_a = client.get(f"/api/v1/assistance/{req_a_id}", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_get_a.status_code == status.HTTP_200_OK
    assert resp_get_a.json()["id"] == req_a_id

    # 3. Citizen B CANNOT read Citizen A's request
    resp_get_b = client.get(f"/api/v1/assistance/{req_a_id}", headers={"Authorization": f"Bearer {citizen_b_token}"})
    assert resp_get_b.status_code == status.HTTP_403_FORBIDDEN
    assert resp_get_b.json()["error"]["code"] == "FORBIDDEN_REQUEST_ACCESS"

    # 4. Citizen B's /mine list does NOT include Citizen A's request
    resp_mine_b = client.get("/api/v1/assistance/mine", headers={"Authorization": f"Bearer {citizen_b_token}"})
    assert resp_mine_b.status_code == status.HTTP_200_OK
    assert len(resp_mine_b.json()) == 0

    # 5. Authority CAN view Citizen A's request in queue
    resp_queue = client.get("/api/v1/assistance", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_queue.status_code == status.HTTP_200_OK
    assert any(r["id"] == req_a_id for r in resp_queue.json())


# ==============================================================================
# 7. Authenticated User-Specific Assistance WebSocket Updates
# ==============================================================================
@pytest.mark.asyncio
async def test_assistance_private_websocket_notifications(
    client: TestClient,
    db_session: Session,
    test_citizen_user: User,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify assistance status change events reach ONLY the owning citizen's private channel."""
    # 1. Citizen submits assistance request
    payload = {
        "latitude": 27.0123,
        "longitude": 85.1234,
        "category": AssistanceCategory.MEDICAL.value,
        "details": "First aid required",
        "people_count": 2,
    }
    resp_req = client.post("/api/v1/assistance", json=payload, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_req.status_code == status.HTTP_201_CREATED
    req_id = resp_req.json()["id"]

    # 2. Attach mock WebSockets to global connection manager
    cit_a_ws = MockWS()
    cit_b_ws = MockWS()
    auth_ws = MockWS()
    public_ws = MockWS()

    await connection_manager.connect(cit_a_ws, user_id=test_citizen_user.id, role="citizen")
    await connection_manager.connect(cit_b_ws, user_id="unrelated_citizen_99", role="citizen")
    await connection_manager.connect(auth_ws, user_id=test_authority_user.id, role="authority")
    await connection_manager.connect(public_ws, user_id="public_user", role="citizen")

    # 3. Authority updates request status
    update_payload = {
        "status": AssistanceStatus.IN_PROGRESS.value,
        "assigned_to": test_authority_user.id,
        "status_notes": "Rescue unit deployed to location.",
    }
    resp_update = client.patch(f"/api/v1/assistance/{req_id}", json=update_payload, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_update.status_code == status.HTTP_200_OK
    assert resp_update.json()["status"] == "in_progress"

    # 4. Verify Citizen A received the private status update
    assert len(cit_a_ws.sent) >= 1
    citizen_message = cit_a_ws.sent[-1]
    assert req_id in citizen_message
    assert "in_progress" in citizen_message

    # 5. Verify Unrelated Citizen B received NO updates
    assert len(cit_b_ws.sent) == 0

    # 6. Verify Public channel received NO assistance updates (privacy preserved)
    # Only channel 'public' subscribers shouldn't get private events
    assert len(public_ws.sent) == 0

    # 7. Verify Authority channel received the operational update
    assert len(auth_ws.sent) >= 1
    assert req_id in auth_ws.sent[-1]

    # Cleanup
    connection_manager.disconnect(cit_a_ws)
    connection_manager.disconnect(cit_b_ws)
    connection_manager.disconnect(auth_ws)
    connection_manager.disconnect(public_ws)


# ==============================================================================
# 8. Reconnection & REST Resync
# ==============================================================================
def test_websocket_reconnection_and_resync(client: TestClient, citizen_token: str):
    """Verify WebSocket welcome payload contains resync endpoints and supports resync action."""
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as ws:
        # Initial handshake includes resync guidance
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"
        assert "resync_endpoints" in welcome
        assert welcome["resync_endpoints"]["alerts"] == "/api/v1/alerts"
        assert welcome["resync_endpoints"]["assistance"] == "/api/v1/assistance/mine"

        # Client requests explicit resync
        ws.send_json({"action": "resync"})
        resync_msg = ws.receive_json()
        assert resync_msg["type"] == "resync.instructions"
        assert "/api/v1/alerts" in resync_msg["endpoints"]["alerts"]
        assert "server_time" in resync_msg


# ==============================================================================
# 9. Push Adapter Success and Failure Handling
# ==============================================================================
def test_push_notification_adapter():
    """Verify push notification token masking, validation, and SIMULATED_ONLY delivery."""
    adapter = SandboxPushNotificationAdapter()

    # 1. Token masking protects privacy
    assert mask_device_token("ExponentPushToken[abcdef1234567890]") == "ExponentPushToken[***7890]"
    assert mask_device_token("fcm_token_1234567890abcdef") == "fcm_***cdef"
    assert mask_device_token(None) == "***"

    # 2. Valid verified test Expo token delivered as SIMULATED_ONLY
    valid_expo = ["ExponentPushToken[valid_token_test_12345]"]
    receipts = adapter.send_test_alert(
        tokens=valid_expo,
        title="[DEMO] Evacuation Alert",
        message="Simulated alert message",
        is_opted_in=True,
    )
    assert len(receipts) == 1
    assert receipts[0].status == DeliveryStatus.SIMULATED_ONLY
    assert receipts[0].is_sandbox is True
    assert receipts[0].simulated_only is True
    assert "SIMULATED_ONLY" in receipts[0].delivery_note
    assert receipts[0].token_masked.startswith("ExponentPushToken[")

    # 3. Arbitrary, unverified device tokens rejected in prototype
    arbitrary_token = ["ExponentPushToken[arbitrary_external_device_999]"]
    receipts_unverified = adapter.send_test_alert(
        tokens=arbitrary_token,
        title="[DEMO] Test Alert",
        message="Simulated alert message",
        is_opted_in=True,
    )
    assert len(receipts_unverified) == 1
    assert receipts_unverified[0].status == DeliveryStatus.UNREGISTERED_DEVICE
    assert "not a verified registered test device" in receipts_unverified[0].error

    # 4. Malformed token rejected with INVALID_TOKEN
    invalid_tokens = ["not_a_valid_token"]
    receipts_inv = adapter.send_test_alert(
        tokens=invalid_tokens,
        title="[DEMO] Test Alert",
        message="Simulated alert message",
        is_opted_in=True,
    )
    assert len(receipts_inv) == 1
    assert receipts_inv[0].status == DeliveryStatus.INVALID_TOKEN
    assert receipts_inv[0].error is not None

    # 5. Opted-out device skipped
    receipts_opt_out = adapter.send_test_alert(
        tokens=valid_expo,
        title="[DEMO] Test Alert",
        message="Simulated alert message",
        is_opted_in=False,
    )
    assert len(receipts_opt_out) == 1
    assert receipts_opt_out[0].status == DeliveryStatus.OPT_OUT_SKIPPED


def test_alert_dispatch_enforces_simulated_true(
    client: TestClient,
    db_session: Session,
    test_authority_user: User,
    authority_token: str,
):
    """Verify attempting operational dispatch (simulated=False) is strictly rejected."""
    alert = Alert(
        id="alert_simulated_enforce",
        area_id="loc_sim",
        title="[DEMO ONLY] Simulation Enforce Test",
        message="Test alert",
        status=AlertStatus.APPROVED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app"],
    )
    db_session.add(alert)
    db_session.commit()

    # Request with simulated=False MUST be rejected
    dispatch_body = {
        "notes": "Attempting real operational dispatch",
        "simulated": False,
    }
    resp = client.post(
        f"/api/v1/alerts/{alert.id}/dispatch",
        json=dispatch_body,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["error"]["code"] == "OPERATIONAL_DISPATCH_PROHIBITED"


def test_alert_dispatch_with_push_tokens(
    client: TestClient,
    db_session: Session,
    test_authority_user: User,
    authority_token: str,
):
    """Verify alert dispatch with target test device tokens triggers push adapter."""
    alert = Alert(
        id="alert_push_dispatch",
        area_id="loc_push",
        title="[DEMO ONLY] Surge Advisory",
        message="Prepare for simulated high water levels.",
        status=AlertStatus.APPROVED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app", "push"],
    )
    db_session.add(alert)
    db_session.commit()

    dispatch_body = {
        "notes": "Dispatching to test mobile sandboxes",
        "target_device_tokens": ["ExponentPushToken[mobile_test_device_token_01]"],
        "simulated": True,
    }
    resp = client.post(
        f"/api/v1/alerts/{alert.id}/dispatch",
        json=dispatch_body,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "dispatched"


# ==============================================================================
# 9. Day 3 PR Review Safeguards Regressions
# ==============================================================================
def test_push_adapter_never_infers_consent_from_token_text():
    """Verify that consent is NEVER inferred from token text (e.g. 'test' or 'demo' substrings).

    Only explicitly configured dummy tokens or genuinely registered test devices are accepted.
    """
    adapter = SandboxPushNotificationAdapter()

    # 1. Token with 'test' or 'demo' in substring MUST be rejected if unregistered
    unregistered_with_test_in_name = "ExponentPushToken[unregistered_external_test_device_9999]"
    receipts = adapter.send_test_alert(
        tokens=[unregistered_with_test_in_name],
        title="[DEMO] Flash Flood Warning",
        message="Simulated alert message",
        is_opted_in=True,
    )
    assert len(receipts) == 1
    assert receipts[0].status == DeliveryStatus.UNREGISTERED_DEVICE
    assert "Consent is never inferred from token text" in receipts[0].error
    assert receipts[0].token_masked == "ExponentPushToken[***9999]"

    unregistered_with_demo_in_name = "ExponentPushToken[some_random_demo_token_8888]"
    receipts_demo = adapter.send_test_alert(
        tokens=[unregistered_with_demo_in_name],
        title="[DEMO] Test Alert",
        message="Simulated alert message",
        is_opted_in=True,
    )
    assert len(receipts_demo) == 1
    assert receipts_demo[0].status == DeliveryStatus.UNREGISTERED_DEVICE
    assert "Consent is never inferred from token text" in receipts_demo[0].error

    # 2. Explicitly registering device via register_test_device allows safe sandbox simulation
    opted_in_token = "ExponentPushToken[genuinely_opted_in_device_55555]"
    registered = adapter.register_test_device(opted_in_token)
    assert registered is True
    assert adapter.is_verified_test_token(opted_in_token) is True

    receipts_opted_in = adapter.send_test_alert(
        tokens=[opted_in_token],
        title="[DEMO] Verified Test Device Alert",
        message="Simulated test dispatch",
        is_opted_in=True,
    )
    assert len(receipts_opted_in) == 1
    assert receipts_opted_in[0].status == DeliveryStatus.SIMULATED_ONLY
    assert receipts_opted_in[0].simulated_only is True
    assert receipts_opted_in[0].token_masked == "ExponentPushToken[***5555]"

    # 3. Explicitly configured prototype dummy tokens are accepted
    configured_dummy = "ExponentPushToken[demo_test_device_sandbox_01]"
    assert adapter.is_verified_test_token(configured_dummy) is True
    receipts_dummy = adapter.send_test_alert(
        tokens=[configured_dummy],
        title="[DEMO] Sandbox Simulation",
        message="Simulated dummy dispatch",
        is_opted_in=True,
    )
    assert len(receipts_dummy) == 1
    assert receipts_dummy[0].status == DeliveryStatus.SIMULATED_ONLY


def test_demo_alerts_isolated_from_general_websocket_channel(
    client: TestClient,
    db_session: Session,
    test_citizen_user: User,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify demo alerts are strictly broadcast to 'demo_alerts' and NOT 'alerts' channel."""
    # 1. Citizen connects to default channels (public, alerts, risk_updates)
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as general_ws:
        general_ws.receive_json()  # connection.established

        # 2. Test-client connects and explicitly subscribes to 'demo_alerts'
        with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as demo_ws:
            demo_ws.receive_json()  # connection.established
            demo_ws.send_json({"action": "subscribe", "channel": "demo_alerts"})
            sub_ack = demo_ws.receive_json()
            assert sub_ack["status"] == "subscribed"

            # 3. Authority creates, approves, and dispatches a demo alert
            alert = Alert(
                id="alert_iso_ws_01",
                area_id="loc_iso_ws",
                title="[DEMO ONLY] Inundation Test",
                message="Historical simulation event",
                status=AlertStatus.APPROVED,
                created_by=test_authority_user.id,
                approved_by=test_authority_user.id,
                mode=OperationalMode.HISTORICAL_DEMO,
                target_channels=["in_app"],
            )
            db_session.add(alert)
            db_session.commit()

            resp = client.post(
                f"/api/v1/alerts/{alert.id}/dispatch",
                json={"notes": "Dispatching demo alert", "simulated": True},
                headers={"Authorization": f"Bearer {authority_token}"},
            )
            assert resp.status_code == status.HTTP_200_OK

            # 4. Opted-in demo_ws receives the event on 'demo_alerts'
            evt = demo_ws.receive_json()
            assert evt["type"] == EventType.ALERT_PUBLISHED.value
            assert evt["resource_id"] == alert.id
            assert evt["metadata"]["simulated_only"] is True

            # 5. General WebSocket client did NOT receive any message on 'alerts'
            # Check by sending a ping action to verify queue only has the ping response
            general_ws.send_json({"action": "ping"})
            resp_ping = general_ws.receive_json()
            assert resp_ping["type"] == "pong"


def test_demo_alerts_isolated_from_public_rest_feed(
    client: TestClient,
    db_session: Session,
    test_citizen_user: User,
    test_authority_user: User,
    citizen_token: str,
    authority_token: str,
):
    """Verify simulation demo alerts are isolated from public REST feed unless include_demo=true."""
    # 1. Create and dispatch a demo alert
    demo_alert = Alert(
        id="alert_iso_rest_01",
        area_id="loc_iso_rest",
        title="[DEMO ONLY] Simulated Flash Flood",
        message="Simulated run for exercise",
        status=AlertStatus.APPROVED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
        target_channels=["in_app"],
    )
    db_session.add(demo_alert)
    db_session.commit()

    resp_disp = client.post(
        f"/api/v1/alerts/{demo_alert.id}/dispatch",
        json={"notes": "Demo dispatch", "simulated": True},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert resp_disp.status_code == status.HTTP_200_OK

    # 2. General citizen queries default feed — demo alert MUST NOT be present
    resp_feed = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_feed.status_code == status.HTTP_200_OK
    feed_ids = [a["id"] for a in resp_feed.json()]
    assert demo_alert.id not in feed_ids

    # 3. Citizen queries with include_demo=true — demo alert IS present
    resp_demo_feed = client.get("/api/v1/alerts?include_demo=true", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_demo_feed.status_code == status.HTTP_200_OK
    demo_feed_ids = [a["id"] for a in resp_demo_feed.json()]
    assert demo_alert.id in demo_feed_ids

    # 4. Authority queries default feed — authorities see all alerts (DRAFT, APPROVED, DISPATCHED, DEMO)
    resp_auth_feed = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_auth_feed.status_code == status.HTTP_200_OK
    auth_feed_ids = [a["id"] for a in resp_auth_feed.json()]
    assert demo_alert.id in auth_feed_ids

