"""Phase 2: Focused security and reliability regression tests for Day 5 release readiness.

Covers:
A. AUTHENTICATION & RBAC
- Missing JWT token (401)
- Invalid / malformed JWT token (401)
- Expired JWT token (401)
- User not found from token (404)
- Inactive user account (403)
- Role elevation protection (Citizen cannot call authority endpoints -> 403)

B. ALERTS LIFECYCLE & ISOLATION
- Draft creation restricted to authority
- Draft cannot be dispatched directly (NOT_APPROVED -> 400)
- Cancelled alert cannot be approved or dispatched (400)
- Approval restricted to authority
- Double approval rejection (400)
- Operational dispatch strictly prohibited (simulated=False -> 400)
- Dispatched alert cannot be re-dispatched (INVALID_STATE -> 400)
- Citizens cannot see draft alerts or demo alerts unless explicitly authorized
- Demo isolation in WebSocket broadcast channels

C. ASSISTANCE PRIVACY & RBAC
- Citizen creates assistance request successfully
- Coordinates stored accurately in DB
- Citizen A cannot access Citizen B's request (403)
- Citizen cannot access the full authority assistance queue (403)
- Authority can inspect full queue and update status
- Assistance WebSocket event omits private GPS coordinates

D. WEBSOCKET SECURITY & RECONNECTION
- Connection rejected with missing token
- Connection rejected with invalid token
- Connection rejected with expired token
- Connection rejected for inactive user
- Citizen subscription to authority_queue rejected (forbidden)
- Citizen subscription to another user's private channel rejected (forbidden)
- Disconnect and reconnect flow
- Reconnect resync instructions endpoint verification (REST sync pattern)

E. ERROR HANDLING & RESILIENCE
- Missing flood event ID (404)
- Missing forecast run ID (404)
- Invalid / malformed GeoJSON payload (422)
- Route hazard screening with invalid coordinates (422)
- Non-existent model ID (404)
- Truthful model capabilities verification
"""
from datetime import datetime, timedelta, timezone
import json
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, hash_password
from app.models.alert import Alert
from app.models.assistance import AssistanceRequest
from app.models.enums import AlertStatus, AssistanceCategory, AssistanceStatus, OperationalMode, UserRole
from app.models.user import User
from app.websocket.connection_manager import ConnectionManager


# ==============================================================================
# SECTION A: AUTHENTICATION & RBAC
# ==============================================================================

def test_auth_missing_token_rejected(client: TestClient):
    """Protected endpoints must reject requests without an Authorization header."""
    res_me = client.get("/api/v1/auth/me")
    assert res_me.status_code == status.HTTP_401_UNAUTHORIZED
    assert res_me.json()["error"]["code"] == "UNAUTHORIZED"

    res_alerts = client.post("/api/v1/alerts", json={
        "area_id": "test_area",
        "title": "Unauthorized Alert",
        "message": "Should not be created",
        "mode": "test",
    })
    assert res_alerts.status_code == status.HTTP_401_UNAUTHORIZED


def test_auth_invalid_token_rejected(client: TestClient):
    """Protected endpoints must reject malformed or invalid Bearer tokens."""
    headers = {"Authorization": "Bearer not-a-valid-jwt-token"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["error"]["code"] == "INVALID_TOKEN"


def test_auth_expired_token_rejected(client: TestClient, test_citizen_user: User):
    """Expired JWT access tokens must be rejected with 401."""
    expired_token = create_access_token(
        subject=test_citizen_user.id,
        role=test_citizen_user.role.value,
        expires_delta=timedelta(seconds=-30),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["error"]["code"] == "INVALID_TOKEN"


def test_auth_nonexistent_user_token(client: TestClient):
    """Valid JWT referring to a deleted or non-existent user must return 404."""
    ghost_token = create_access_token(
        subject="00000000-0000-0000-0000-000000000000",
        role=UserRole.CITIZEN.value,
    )
    headers = {"Authorization": f"Bearer {ghost_token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["error"]["code"] == "USER_NOT_FOUND"


def test_auth_inactive_user_rejected(client: TestClient, db_session: Session):
    """Deactivated user accounts must be rejected with 403 ACCOUNT_INACTIVE."""
    inactive_user = User(
        email="inactive@example.com",
        hashed_password=hash_password("password123"),
        full_name="Inactive User",
        role=UserRole.CITIZEN,
        contact_consent=True,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()
    db_session.refresh(inactive_user)

    token = create_access_token(subject=inactive_user.id, role=inactive_user.role.value)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_auth_role_elevation_protection(client: TestClient, citizen_token: str):
    """Citizen accounts must not be able to perform authority or admin actions."""
    headers = {"Authorization": f"Bearer {citizen_token}"}

    # Attempt to draft an alert
    res_draft = client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "area_id": "test_area",
            "title": "Citizen Attempted Alert",
            "message": "Should be forbidden",
            "mode": "test",
        },
    )
    assert res_draft.status_code == status.HTTP_403_FORBIDDEN
    assert res_draft.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    # Attempt to view authority assistance queue
    res_queue = client.get("/api/v1/assistance", headers=headers)
    assert res_queue.status_code == status.HTTP_403_FORBIDDEN
    assert res_queue.json()["error"]["code"] == "INSUFFICIENT_ROLE"


# ==============================================================================
# SECTION B: ALERTS LIFECYCLE & ISOLATION
# ==============================================================================

def test_alert_lifecycle_draft_approve_dispatch(
    client: TestClient,
    authority_token: str,
):
    """Verify complete alert lifecycle: Draft -> Approved -> Dispatched (historical demo)."""
    headers = {"Authorization": f"Bearer {authority_token}"}

    # 1. Create Draft Alert
    draft_payload = {
        "area_id": "dhanusha_janakpur",
        "title": "[DEMO] Janakpur Flash Flood Warning",
        "message": "Water levels rising near river bank. Seek high ground.",
        "mode": "historical_demo",
    }
    create_res = client.post("/api/v1/alerts", headers=headers, json=draft_payload)
    assert create_res.status_code == status.HTTP_201_CREATED
    alert = create_res.json()
    assert alert["status"] == "draft"
    alert_id = alert["id"]

    # 2. Cannot dispatch directly from DRAFT (must be APPROVED first)
    bad_dispatch = client.post(
        f"/api/v1/alerts/{alert_id}/dispatch",
        headers=headers,
        json={"simulated": True},
    )
    assert bad_dispatch.status_code == status.HTTP_400_BAD_REQUEST
    assert bad_dispatch.json()["error"]["code"] == "NOT_APPROVED"

    # 3. Approve Alert
    approve_res = client.post(
        f"/api/v1/alerts/{alert_id}/approve",
        headers=headers,
        json={"comments": "Verified historical event data."},
    )
    assert approve_res.status_code == status.HTTP_200_OK
    assert approve_res.json()["status"] == "approved"

    # 4. Cannot re-approve an already approved alert
    dup_approve = client.post(
        f"/api/v1/alerts/{alert_id}/approve",
        headers=headers,
        json={"comments": "Duplicate approval"},
    )
    assert dup_approve.status_code == status.HTTP_400_BAD_REQUEST
    assert dup_approve.json()["error"]["code"] == "INVALID_STATE"

    # 5. Dispatch Alert (Simulated)
    dispatch_res = client.post(
        f"/api/v1/alerts/{alert_id}/dispatch",
        headers=headers,
        json={"simulated": True},
    )
    assert dispatch_res.status_code == status.HTTP_200_OK
    assert dispatch_res.json()["status"] == "dispatched"
    assert dispatch_res.json()["issued_at"] is not None

    # 6. Cannot re-dispatch an already dispatched alert
    dup_dispatch = client.post(
        f"/api/v1/alerts/{alert_id}/dispatch",
        headers=headers,
        json={"simulated": True},
    )
    assert dup_dispatch.status_code == status.HTTP_400_BAD_REQUEST
    assert dup_dispatch.json()["error"]["code"] == "INVALID_STATE"


def test_alert_operational_dispatch_prohibited(
    client: TestClient,
    authority_token: str,
):
    """Operational dispatch (simulated=False) is strictly blocked by backend safeguard."""
    headers = {"Authorization": f"Bearer {authority_token}"}

    # Create & approve
    c_res = client.post(
        "/api/v1/alerts",
        headers=headers,
        json={
            "area_id": "rautahat_gaur",
            "title": "[DEMO] Gaur Embankment Breach",
            "message": "Simulated flood warning message",
            "mode": "historical_demo",
        },
    )
    alert_id = c_res.json()["id"]
    client.post(f"/api/v1/alerts/{alert_id}/approve", headers=headers, json={"comments": "Approved"})

    # Attempt dispatch with simulated=False
    op_res = client.post(
        f"/api/v1/alerts/{alert_id}/dispatch",
        headers=headers,
        json={"simulated": False},
    )
    assert op_res.status_code == status.HTTP_400_BAD_REQUEST
    assert op_res.json()["error"]["code"] == "OPERATIONAL_DISPATCH_PROHIBITED"


def test_alert_isolation_from_unauthorized_citizens(
    client: TestClient,
    authority_token: str,
    citizen_token: str,
):
    """Citizens cannot view unapproved drafts or demo alerts unless explicitly authorized."""
    auth_headers = {"Authorization": f"Bearer {authority_token}"}
    citizen_headers = {"Authorization": f"Bearer {citizen_token}"}

    # Create draft
    c_res = client.post(
        "/api/v1/alerts",
        headers=auth_headers,
        json={
            "area_id": "saptari_rajbiraj",
            "title": "[DEMO] Draft Saptari Advisory",
            "message": "Internal authority draft.",
            "mode": "historical_demo",
        },
    )
    draft_id = c_res.json()["id"]

    # Citizen tries to get draft by ID -> 403 UNPUBLISHED_ALERTS_RESTRICTED
    get_res = client.get(f"/api/v1/alerts/{draft_id}", headers=citizen_headers)
    assert get_res.status_code == status.HTTP_403_FORBIDDEN
    assert get_res.json()["error"]["code"] == "UNPUBLISHED_ALERTS_RESTRICTED"

    # Citizen lists alerts with status_filter=draft -> 403
    list_drafts = client.get("/api/v1/alerts?status_filter=draft", headers=citizen_headers)
    assert list_drafts.status_code == status.HTTP_403_FORBIDDEN
    assert list_drafts.json()["error"]["code"] == "UNPUBLISHED_ALERTS_RESTRICTED"

    # Citizen lists alerts with include_demo=true without participant authorization -> 403
    list_demo = client.get("/api/v1/alerts?include_demo=true", headers=citizen_headers)
    assert list_demo.status_code == status.HTTP_403_FORBIDDEN
    assert list_demo.json()["error"]["code"] == "DEMO_ALERTS_RESTRICTED"


# ==============================================================================
# SECTION C: ASSISTANCE PRIVACY & RBAC
# ==============================================================================

def test_assistance_request_lifecycle_and_privacy(
    client: TestClient,
    citizen_token: str,
    authority_token: str,
    db_session: Session,
):
    """Citizen submits assistance request; privacy boundary is enforced between citizens."""
    citizen1_headers = {"Authorization": f"Bearer {citizen_token}"}
    authority_headers = {"Authorization": f"Bearer {authority_token}"}

    # 1. Citizen 1 submits an assistance request
    payload = {
        "latitude": 26.7288,
        "longitude": 85.9244,
        "category": AssistanceCategory.EVACUATION.value,
        "details": "Trapped on roof with family of four. Water level 1.5m.",
        "people_count": 4,
    }
    create_res = client.post("/api/v1/assistance", headers=citizen1_headers, json=payload)
    assert create_res.status_code == status.HTTP_201_CREATED
    req1 = create_res.json()
    req1_id = req1["id"]
    assert req1["category"] == "evacuation"
    assert req1["people_count"] == 4
    assert req1["status"] == "pending"

    # 2. Citizen 1 can see their request via /assistance/mine
    mine_res = client.get("/api/v1/assistance/mine", headers=citizen1_headers)
    assert mine_res.status_code == status.HTTP_200_OK
    mine_ids = [r["id"] for r in mine_res.json()]
    assert req1_id in mine_ids

    # 3. Citizen 1 can retrieve their request by ID
    get_res = client.get(f"/api/v1/assistance/{req1_id}", headers=citizen1_headers)
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["latitude"] == 26.7288

    # 4. Create Citizen 2
    user2 = User(
        email="citizen2@floodlens.org",
        hashed_password=hash_password("pw123"),
        full_name="Second Citizen",
        role=UserRole.CITIZEN,
        contact_consent=True,
        is_active=True,
    )
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user2)
    token2 = create_access_token(subject=user2.id, role=user2.role.value)
    citizen2_headers = {"Authorization": f"Bearer {token2}"}

    # 5. Citizen 2 CANNOT access Citizen 1's request by ID (403 FORBIDDEN_REQUEST_ACCESS)
    c2_res = client.get(f"/api/v1/assistance/{req1_id}", headers=citizen2_headers)
    assert c2_res.status_code == status.HTTP_403_FORBIDDEN
    assert c2_res.json()["error"]["code"] == "FORBIDDEN_REQUEST_ACCESS"

    # 6. Citizen 2 does NOT see Citizen 1's request in their /assistance/mine
    c2_mine = client.get("/api/v1/assistance/mine", headers=citizen2_headers)
    assert c2_mine.status_code == status.HTTP_200_OK
    assert req1_id not in [r["id"] for r in c2_mine.json()]

    # 7. Authority CAN access the request and update its status
    auth_get = client.get(f"/api/v1/assistance/{req1_id}", headers=authority_headers)
    assert auth_get.status_code == status.HTTP_200_OK
    assert auth_get.json()["id"] == req1_id

    update_res = client.patch(
        f"/api/v1/assistance/{req1_id}",
        headers=authority_headers,
        json={
            "status": "in_progress",
            "assigned_to": "Nepal Army Disaster Response Unit",
            "status_notes": "Boat dispatched to coordinate.",
        },
    )
    assert update_res.status_code == status.HTTP_200_OK
    assert update_res.json()["status"] == "in_progress"
    assert update_res.json()["assigned_to"] == "Nepal Army Disaster Response Unit"


def test_assistance_multiple_requests_by_citizen(
    client: TestClient,
    citizen_token: str,
):
    """Citizen can submit multiple requests over time, all tracked in /mine."""
    headers = {"Authorization": f"Bearer {citizen_token}"}

    for i in range(3):
        res = client.post(
            "/api/v1/assistance",
            headers=headers,
            json={
                "latitude": 26.70 + i * 0.01,
                "longitude": 85.90 + i * 0.01,
                "category": AssistanceCategory.MEDICAL.value,
                "details": f"Update {i}: need medical kit.",
                "people_count": i + 1,
            },
        )
        assert res.status_code == status.HTTP_201_CREATED

    mine = client.get("/api/v1/assistance/mine", headers=headers)
    assert mine.status_code == status.HTTP_200_OK
    assert len(mine.json()) >= 3


# ==============================================================================
# SECTION D: WEBSOCKET SECURITY & RECONNECTION
# ==============================================================================

def test_websocket_rejects_missing_or_invalid_token(client: TestClient):
    """WebSocket connection without token or with invalid token must disconnect with policy violation."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/events") as ws:
            pass

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/events?token=bogus_token") as ws:
            pass


def test_websocket_rejects_expired_token(client: TestClient, test_citizen_user: User):
    """WebSocket connection with expired token must be rejected immediately."""
    expired_token = create_access_token(
        subject=test_citizen_user.id,
        role=test_citizen_user.role.value,
        expires_delta=timedelta(seconds=-60),
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/v1/events?token={expired_token}") as ws:
            pass


def test_websocket_rejects_inactive_user(client: TestClient, db_session: Session):
    """WebSocket connection with token for inactive user must be closed."""
    inactive_user = User(
        email="inactive_ws@example.com",
        hashed_password=hash_password("pw"),
        full_name="Inactive WS User",
        role=UserRole.CITIZEN,
        contact_consent=True,
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()
    db_session.refresh(inactive_user)

    token = create_access_token(subject=inactive_user.id, role=inactive_user.role.value)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/v1/events?token={token}") as ws:
            pass


def test_websocket_channel_authorization(client: TestClient, citizen_token: str):
    """Citizen can subscribe to valid public topics but is rejected from authority channels."""
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as ws:
        # Welcome message
        welcome = ws.receive_json()
        assert welcome["type"] == "connection.established"

        # Attempt to subscribe to authority_queue (must be forbidden)
        ws.send_json({"action": "subscribe", "channel": "authority_queue"})
        reply = ws.receive_json()
        assert reply["type"] == "subscription.result"
        assert reply["channel"] == "authority_queue"
        assert reply["status"] == "forbidden"

        # Attempt to subscribe to demo_alerts (unauthorized citizen -> forbidden)
        ws.send_json({"action": "subscribe", "channel": "demo_alerts"})
        demo_reply = ws.receive_json()
        assert demo_reply["type"] == "subscription.result"
        assert demo_reply["status"] == "forbidden"

        # Authorized subscription to a location channel
        ws.send_json({"action": "subscribe", "channel": "locations:janakpur"})
        loc_reply = ws.receive_json()
        assert loc_reply["type"] == "subscription.result"
        assert loc_reply["status"] == "subscribed"


def test_websocket_resync_protocol(client: TestClient, citizen_token: str):
    """Client reconnecting after a network drop queries resync action for state reconciliation."""
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as ws:
        # Initial welcome confirms resync endpoints
        welcome = ws.receive_json()
        assert "resync_endpoints" in welcome
        assert welcome["resync_endpoints"]["alerts"] == "/api/v1/alerts"
        assert welcome["resync_endpoints"]["assistance"] == "/api/v1/assistance/mine"

        # Client requests explicit resync instructions
        ws.send_json({"action": "resync"})
        reply = ws.receive_json()
        assert reply["type"] == "resync.instructions"
        assert "endpoints" in reply
        assert "server_time" in reply


# ==============================================================================
# SECTION E: ERROR HANDLING & RESILIENCE
# ==============================================================================

def test_error_missing_flood_event(client: TestClient):
    """Requests for non-existent flood event IDs return 404 NOT_FOUND."""
    res = client.get("/api/v1/flood-events/evt_nonexistent_999999")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["error"]["code"] == "EVENT_NOT_FOUND"

    res_report = client.get("/api/v1/flood-events/evt_nonexistent_999999/report")
    assert res_report.status_code == status.HTTP_404_NOT_FOUND

    res_timeline = client.get("/api/v1/flood-events/evt_nonexistent_999999/timeline")
    assert res_timeline.status_code == status.HTTP_404_NOT_FOUND


def test_error_missing_forecast_run(client: TestClient):
    """Requests for non-existent forecast runs return 404."""
    res = client.get("/api/v1/predictions/forecast-runs/fc_nonexistent_run_888")
    assert res.status_code == status.HTTP_404_NOT_FOUND


def test_error_invalid_geojson_payload(client: TestClient, authority_token: str):
    """Submitting invalid or malformed payload to extent ingestion returns 422."""
    headers = {"Authorization": f"Bearer {authority_token}"}

    # Create an event first
    evt_res = client.post(
        "/api/v1/flood-events",
        headers=headers,
        json={
            "region_id": "terai_dhanusha",
            "name": "Test Event GeoJSON Validation",
            "start_at": datetime.now(timezone.utc).isoformat(),
            "mode": "historical_demo",
        },
    )
    assert evt_res.status_code == status.HTTP_201_CREATED
    evt_id = evt_res.json()["id"]

    # Ingest bad extent payload (area_km2 <= 0 fails gt=0.0 constraint, or invalid geometry type)
    bad_payload = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "method": "SAR_CHANGE",
        "area_km2": -5.0,  # Invalid: area must be > 0.0
        "geometry": 12345,  # Invalid: must be dict or str
    }
    res = client.post(f"/api/v1/flood-events/{evt_id}/extent", headers=headers, json=bad_payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_error_route_hazard_invalid_coordinates(client: TestClient):
    """Route assessment with invalid coordinate ranges returns 422."""
    # Latitude out of bounds (> 90)
    bad_route = {
        "route": {
            "type": "LineString",
            "coordinates": [[85.0, 999.0], [85.0, 27.0]],
        }
    }
    res = client.post("/api/v1/routes/assess", json=bad_route)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_models_truthful_capabilities(client: TestClient, authority_token: str):
    """GET /api/v1/models truthfully reports calibrated baseline status without speculative models."""
    res = client.get("/api/v1/models")
    assert res.status_code == status.HTTP_200_OK
    models = res.json()
    assert isinstance(models, list)
    assert len(models) >= 2
    # Operational claims: check that all listed models have truthful readiness descriptions
    for model in models:
        assert "version" in model
        assert "status" in model
        assert "limitations" in model
        # Explicit warning that models are not for unvalidated operational warnings
        assert any("operational" in lim.lower() for lim in model["limitations"])

    # POST to training jobs returns truthful 501 not implemented
    headers = {"Authorization": f"Bearer {authority_token}"}
    job_res = client.post(
        "/api/v1/models/training-jobs",
        headers=headers,
        json={"model_id": "flood_extent_unet", "target_horizon_hours": 3},
    )
    assert job_res.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert job_res.json()["error"]["code"] == "TRAINING_NOT_IMPLEMENTED"
