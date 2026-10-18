"""Demonstration script for FloodLens AI Day 3 deliverables.

Demonstrates:
Flow 1: Citizen sends assistance request -> Backend stores it -> Authority receives event
        -> Authority updates status -> Citizen receives private WebSocket update.
Flow 2: Authority creates demo alert -> Authorized approval -> Test-only dispatch
        -> Opted-in test client receives notification.

Safety Constraints:
- Dispatches restricted to historical-demo / test sandboxes.
- Visible [DEMO / TEST ONLY] labelling strictly enforced.
- Coordinates, citizen IDs, and personal details excluded from public channels.
- Push tokens safely masked in all receipts and logs.
"""
import asyncio
import json
import logging
import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

os.environ["ENVIRONMENT"] = "testing"
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-chars-minimum-length-floodlens")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import create_application
from app.models.enums import AlertStatus, AssistanceCategory, AssistanceStatus, OperationalMode, UserRole
from app.models.user import User
from app.services.push_notifications import mask_device_token
from app.websocket.connection_manager import connection_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Day3Demo")


def run_demonstration():
    logger.info("================================================================================")
    logger.info("STARTING FLOODLENS AI — DAY 3 BACKEND INTEGRATION DEMONSTRATION")
    logger.info("================================================================================")

    # 1. Setup Test Database using StaticPool for shared in-memory state
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    app = create_application()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # 2. Provision Test Accounts
    citizen_user = User(
        email="citizen.demo@example.com",
        hashed_password=hash_password("citizenpassword"),
        full_name="Janakpur Citizen",
        role=UserRole.CITIZEN,
        is_active=True,
    )
    participant_user = User(
        email="demo_participant@floodlens.internal",
        hashed_password=hash_password("participantpassword"),
        full_name="Authorized Demonstration Participant",
        role=UserRole.CITIZEN,
        is_active=True,
    )
    authority_user = User(
        email="commander.demo@floodlens.org",
        hashed_password=hash_password("authoritypassword"),
        full_name="Disaster Response Commander",
        role=UserRole.AUTHORITY,
        is_active=True,
    )
    db.add_all([citizen_user, participant_user, authority_user])
    db.commit()
    db.refresh(citizen_user)
    db.refresh(participant_user)
    db.refresh(authority_user)

    citizen_token = create_access_token(subject=citizen_user.id, role=citizen_user.role.value)
    participant_token = create_access_token(subject=participant_user.id, role=participant_user.role.value)
    authority_token = create_access_token(subject=authority_user.id, role=authority_user.role.value)

    logger.info("Test Accounts Created:")
    logger.info("  Citizen:     id=%s, role=%s", citizen_user.id, citizen_user.role.value)
    logger.info("  Participant: id=%s, email=%s, role=%s", participant_user.id, participant_user.email, participant_user.role.value)
    logger.info("  Authority:   id=%s, role=%s", authority_user.id, authority_user.role.value)

    # ==============================================================================
    # DEMONSTRATION FLOW 1: Citizen Assistance Lifecycle & Private WebSocket Update
    # ==============================================================================
    logger.info("\n--------------------------------------------------------------------------------")
    logger.info("DEMO FLOW 1: Citizen Assistance Lifecycle & User-Specific Private WebSocket Event")
    logger.info("--------------------------------------------------------------------------------")

    # Step 1: Open WebSocket connections
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as citizen_ws:
        cit_welcome = citizen_ws.receive_json()
        logger.info("[Citizen WS] Connected: role=%s, channels=%s", cit_welcome["role"], cit_welcome["subscribed_channels"])
        assert f"user:{citizen_user.id}" in cit_welcome["subscribed_channels"]

        with client.websocket_connect(f"/ws/v1/events?token={authority_token}") as auth_ws:
            auth_welcome = auth_ws.receive_json()
            logger.info("[Authority WS] Connected: role=%s, channels=%s", auth_welcome["role"], auth_welcome["subscribed_channels"])
            assert "authority_queue" in auth_welcome["subscribed_channels"]

            # Step 2: Citizen submits assistance request
            assistance_payload = {
                "latitude": 26.7271,
                "longitude": 85.9402,
                "category": AssistanceCategory.EVACUATION.value,
                "details": "Water entering ground floor, elderly residents need transport.",
                "people_count": 4,
            }
            logger.info("[Citizen] Submitting assistance request: category=evacuation, people=4")
            resp_create = client.post(
                "/api/v1/assistance",
                json=assistance_payload,
                headers={"Authorization": f"Bearer {citizen_token}"},
            )
            assert resp_create.status_code == 201
            req_data = resp_create.json()
            req_id = req_data["id"]
            logger.info("[Backend] Stored assistance request: id=%s, status=%s", req_id, req_data["status"])

            # Step 3: Authority receives event on authority_queue
            auth_event_raw = auth_ws.receive_text()
            auth_event = json.loads(auth_event_raw)
            logger.info("[Authority WS] Received event: type=%s, resource_id=%s, metadata=%s",
                        auth_event["type"], auth_event["resource_id"], auth_event.get("metadata"))
            assert auth_event["type"] == "assistance.created"
            assert auth_event["resource_id"] == req_id
            # Verify coordinates are NOT in event
            assert "latitude" not in str(auth_event) and "85.9402" not in str(auth_event)
            logger.info("[Privacy Check] Sensitive coordinates successfully excluded from WebSocket event.")

            # Step 4: Authority reviews queue and updates status
            update_payload = {
                "status": AssistanceStatus.IN_PROGRESS.value,
                "assigned_to": authority_user.id,
                "status_notes": "Rescue Boat Unit 3 dispatched to location.",
            }
            logger.info("[Authority] Updating request status to IN_PROGRESS (assigned to commander)")
            resp_update = client.patch(
                f"/api/v1/assistance/{req_id}",
                json=update_payload,
                headers={"Authorization": f"Bearer {authority_token}"},
            )
            assert resp_update.status_code == 200
            logger.info("[Backend] Updated status recorded in database: %s", resp_update.json()["status"])

            # Step 5: Citizen receives private WebSocket event
            cit_event_raw = citizen_ws.receive_text()
            cit_event = json.loads(cit_event_raw)
            logger.info("[Citizen WS] Received Private Event: type=%s, resource_id=%s, metadata=%s",
                        cit_event["type"], cit_event["resource_id"], cit_event.get("metadata"))
            assert cit_event["type"] == "assistance.updated"
            assert cit_event["resource_id"] == req_id
            assert cit_event["metadata"]["status"] == "in_progress"
            logger.info("[Verification] Citizen successfully received private assistance status update!")

    # ==============================================================================
    # DEMONSTRATION FLOW 2: Authority Demo Alert -> Approval -> Test Dispatch
    # ==============================================================================
    logger.info("\n--------------------------------------------------------------------------------")
    logger.info("DEMO FLOW 2: Authority Demo Alert -> Authorized Approval -> Test-Only Dispatch")
    logger.info("--------------------------------------------------------------------------------")

    # Negative Access Control Verification: Unrelated citizen cannot subscribe to demo_alerts
    with client.websocket_connect(f"/ws/v1/events?token={citizen_token}") as unauth_ws:
        unauth_ws.receive_json()  # connection.established
        unauth_ws.send_json({"action": "subscribe", "channel": "demo_alerts"})
        sub_rej = unauth_ws.receive_json()
        assert sub_rej["type"] == "subscription.result"
        assert sub_rej["channel"] == "demo_alerts"
        assert sub_rej["status"] == "forbidden"
        logger.info("[Access Control] Unrelated citizen subscription to 'demo_alerts' rejected: status=%s", sub_rej["status"])

    # Negative Access Control Verification: Unrelated citizen cannot query include_demo=true
    resp_unauth_inc = client.get("/api/v1/alerts?include_demo=true", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_unauth_inc.status_code == 403
    logger.info("[Access Control] Unrelated citizen ?include_demo=true query rejected: 403 Forbidden (%s)",
                resp_unauth_inc.json()["error"]["code"])

    # Authorized Demonstration Participant Flow
    with client.websocket_connect(f"/ws/v1/events?token={participant_token}") as test_client_ws:
        test_client_ws.receive_json()  # connection.established
        # Subscribe authorized test participant explicitly to isolated demo_alerts channel
        test_client_ws.send_json({"action": "subscribe", "channel": "demo_alerts"})
        sub_ack = test_client_ws.receive_json()
        assert sub_ack["type"] == "subscription.result"
        assert sub_ack["status"] == "subscribed"
        logger.info("[Test Participant WS] Authorized participant explicitly subscribed to 'demo_alerts'.")

        with client.websocket_connect(f"/ws/v1/events?token={authority_token}") as auth_ws:
            auth_ws.receive_json()  # connection.established

            # Step 1: Authority creates draft alert
            alert_draft_payload = {
                "area_id": "loc_janakpur_01",
                "title": "Jaladh River Rapid Inundation",
                "message": "Historical demonstration surge model indicates rising water level.",
                "mode": OperationalMode.HISTORICAL_DEMO.value,
                "target_channels": ["in_app", "push"],
            }
            logger.info("[Authority] Creating draft alert: '%s'", alert_draft_payload["title"])
            resp_draft = client.post(
                "/api/v1/alerts",
                json=alert_draft_payload,
                headers={"Authorization": f"Bearer {authority_token}"},
            )
            assert resp_draft.status_code == 201
            alert_data = resp_draft.json()
            alert_id = alert_data["id"]
            logger.info("[Backend] Draft alert created: id=%s, title='%s', status=%s",
                        alert_id, alert_data["title"], alert_data["status"])
            assert alert_data["title"].startswith("[DEMO ONLY]")

            # Step 2: Confidentiality verification — citizen cannot see draft
            resp_cit_alerts = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {citizen_token}"})
            assert all(a["id"] != alert_id for a in resp_cit_alerts.json())
            logger.info("[Confidentiality Check] Draft alert is strictly hidden from citizen query.")

            # Step 3: Authority approves alert
            logger.info("[Authority] Approving draft alert id=%s", alert_id)
            resp_approve = client.post(
                f"/api/v1/alerts/{alert_id}/approve",
                json={"notes": "Reviewed and approved for historical simulation run."},
                headers={"Authorization": f"Bearer {authority_token}"},
            )
            assert resp_approve.status_code == 200
            logger.info("[Backend] Alert status transitioned to: %s", resp_approve.json()["status"])

            # Authority queue received alert.approved event
            auth_alert_evt = json.loads(auth_ws.receive_text())
            assert auth_alert_evt["type"] == "alert.approved"
            logger.info("[Authority WS] Received event: type=%s, resource_id=%s",
                        auth_alert_evt["type"], auth_alert_evt["resource_id"])

            # Step 4: Authority dispatches alert with test device tokens
            test_push_token = "ExponentPushToken[demo_test_device_sandbox_01]"
            dispatch_body = {
                "notes": "Dispatching to registered test devices for demonstration",
                "target_device_tokens": [test_push_token],
                "simulated": True,
            }
            logger.info("[Authority] Dispatching alert with opted-in test push token: '%s'", mask_device_token(test_push_token))
            resp_dispatch = client.post(
                f"/api/v1/alerts/{alert_id}/dispatch",
                json=dispatch_body,
                headers={"Authorization": f"Bearer {authority_token}"},
            )
            assert resp_dispatch.status_code == 200
            dispatched_data = resp_dispatch.json()
            logger.info("[Backend] Alert dispatched successfully: id=%s, status=%s, issued_at=%s",
                        alert_id, dispatched_data["status"], dispatched_data["issued_at"])
            assert dispatched_data["status"] == "dispatched"

            # Step 5: Authorized participant receives alert.published event over isolated 'demo_alerts' WebSocket channel
            client_evt = json.loads(test_client_ws.receive_text())
            logger.info("[Test Participant WS] Received Demo Alert Event on isolated channel: type=%s, resource_id=%s, metadata=%s",
                        client_evt["type"], client_evt["resource_id"], client_evt.get("metadata"))
            assert client_evt["type"] == "alert.published"
            assert client_evt["resource_id"] == alert_id
            assert client_evt["metadata"]["is_test"] is True
            assert client_evt["metadata"]["simulation"] is True
            assert client_evt["metadata"]["simulated_only"] is True
            logger.info("[Test Participant WS] Verified SIMULATED_ONLY alert event received. No operational warnings issued.")

            # Step 6: Verify isolation and access control in REST feed
            # 6a: Default public feed excludes simulation demo alerts:
            resp_cit_normal = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {citizen_token}"})
            assert all(a["id"] != alert_id for a in resp_cit_normal.json())
            logger.info("[Isolation Check] Dispatched demo alert is excluded from standard public feed.")

            # 6b: Unrelated citizen direct GET of demo alert is rejected 403 Forbidden
            resp_cit_direct = client.get(f"/api/v1/alerts/{alert_id}", headers={"Authorization": f"Bearer {citizen_token}"})
            assert resp_cit_direct.status_code == 403
            logger.info("[Access Control] Unrelated citizen direct GET of demo alert rejected: 403 Forbidden (%s)",
                        resp_cit_direct.json()["error"]["code"])

            # 6c: Authorized demo participant queries with include_demo=true
            resp_part_demo = client.get("/api/v1/alerts?include_demo=true", headers={"Authorization": f"Bearer {participant_token}"})
            assert resp_part_demo.status_code == 200
            assert any(a["id"] == alert_id for a in resp_part_demo.json())
            logger.info("[REST Query] Authorized participant queried demo alert via ?include_demo=true successfully.")

            # 6d: Authorized demo participant retrieves demo alert by ID directly
            resp_part_direct = client.get(f"/api/v1/alerts/{alert_id}", headers={"Authorization": f"Bearer {participant_token}"})
            assert resp_part_direct.status_code == 200
            assert resp_part_direct.json()["id"] == alert_id
            logger.info("[REST Query] Authorized participant retrieved demo alert by ID directly.")

    logger.info("\n================================================================================")
    logger.info("ALL DAY 3 DEMONSTRATION FLOWS COMPLETED SUCCESSFULLY AND VERIFIED!")
    logger.info("================================================================================")


if __name__ == "__main__":
    run_demonstration()
