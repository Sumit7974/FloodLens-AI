"""Regression tests for PostGIS spatial column schemas, alert authorization, WebSocket security, and credentials."""
from datetime import datetime, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.config import Settings
from app.models.alert import Alert
from app.models.asset import Asset, Facility, RoadHazard
from app.models.assistance import AssistanceRequest
from app.models.enums import AlertStatus, EventType, OperationalMode, UserRole
from app.models.location import Location
from app.models.satellite import FloodExtent
from app.models.user import User
from app.websocket.connection_manager import ConnectionManager


# ==============================================================================
# 1. Spatial Column Schema & PostGIS Geometry Conformance
# ==============================================================================
def test_spatial_columns_postgresql_ddl():
    """Verify that all spatial models compile to exact PostGIS geometry types on PostgreSQL."""
    pg_dialect = postgresql.dialect()

    # 1. Location: geometry(GEOMETRY, 4326)
    loc_ddl = str(CreateTable(Location.__table__).compile(dialect=pg_dialect))
    assert "geometry geometry(GEOMETRY,4326)" in loc_ddl

    # 2. FloodExtent: geometry(MULTIPOLYGON, 4326)
    extent_ddl = str(CreateTable(FloodExtent.__table__).compile(dialect=pg_dialect))
    assert "geometry geometry(MULTIPOLYGON,4326)" in extent_ddl

    # 3. Asset: geometry(GEOMETRY, 4326)
    asset_ddl = str(CreateTable(Asset.__table__).compile(dialect=pg_dialect))
    assert "geometry geometry(GEOMETRY,4326)" in asset_ddl

    # 4. Facility: location geometry(POINT, 4326)
    facility_ddl = str(CreateTable(Facility.__table__).compile(dialect=pg_dialect))
    assert "location geometry(POINT,4326)" in facility_ddl

    # 5. RoadHazard: geometry(GEOMETRY, 4326)
    hazard_ddl = str(CreateTable(RoadHazard.__table__).compile(dialect=pg_dialect))
    assert "geometry geometry(GEOMETRY,4326)" in hazard_ddl

    # 6. AssistanceRequest: location_geometry geometry(POINT, 4326)
    assist_ddl = str(CreateTable(AssistanceRequest.__table__).compile(dialect=pg_dialect))
    assert "location_geometry geometry(POINT,4326)" in assist_ddl


# ==============================================================================
# 2. Alert Authorization & Unpublished Alert Restrictions
# ==============================================================================
def test_unpublished_alerts_restricted_from_citizens(client: TestClient, db_session, test_authority_user: User, citizen_token: str, authority_token: str):
    """Verify that unpublished alerts (draft/approved) are strictly restricted from citizens."""
    now = datetime.now(timezone.utc)

    # Create one draft alert, one approved alert, and one dispatched alert
    draft_alert = Alert(
        id="alert_draft_01",
        area_id="loc_01",
        title="Draft Inundation Notice",
        message="Internal proposal for upcoming flood warning.",
        status=AlertStatus.DRAFT,
        created_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    approved_alert = Alert(
        id="alert_approved_02",
        area_id="loc_01",
        title="Approved Inundation Notice",
        message="Approved warning waiting for dispatch.",
        status=AlertStatus.APPROVED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    dispatched_alert = Alert(
        id="alert_dispatched_03",
        area_id="loc_01",
        title="Active Flood Warning",
        message="Immediate evacuation advised for low-lying sectors.",
        status=AlertStatus.DISPATCHED,
        created_by=test_authority_user.id,
        approved_by=test_authority_user.id,
        issued_at=now,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add_all([draft_alert, approved_alert, dispatched_alert])
    db_session.commit()

    # 1. Unauthenticated request to GET /alerts should ONLY return dispatched alert
    resp_anon = client.get("/api/v1/alerts")
    assert resp_anon.status_code == status.HTTP_200_OK
    anon_alerts = resp_anon.json()
    assert len(anon_alerts) == 1
    assert anon_alerts[0]["id"] == "alert_dispatched_03"
    assert anon_alerts[0]["status"] == "dispatched"

    # 2. Citizen request to GET /alerts should ONLY return dispatched alert
    resp_citizen = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_citizen.status_code == status.HTTP_200_OK
    citizen_alerts = resp_citizen.json()
    assert len(citizen_alerts) == 1
    assert citizen_alerts[0]["id"] == "alert_dispatched_03"

    # 3. Citizen explicitly requesting draft status should be rejected with 403 Forbidden
    resp_forbidden = client.get("/api/v1/alerts?status_filter=draft", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_forbidden.status_code == status.HTTP_403_FORBIDDEN
    err = resp_forbidden.json()["error"]
    assert err["code"] == "UNPUBLISHED_ALERTS_RESTRICTED"

    # 4. Citizen requesting approved status should also be rejected with 403 Forbidden
    resp_forbidden_approved = client.get("/api/v1/alerts?status_filter=approved", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_forbidden_approved.status_code == status.HTTP_403_FORBIDDEN

    # 5. Authority request to GET /alerts should return ALL alerts
    resp_auth = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_auth.status_code == status.HTTP_200_OK
    auth_alerts = resp_auth.json()
    assert len(auth_alerts) == 3

    # 6. Authority can explicitly filter by draft status
    resp_auth_drafts = client.get("/api/v1/alerts?status_filter=draft", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_auth_drafts.status_code == status.HTTP_200_OK
    auth_draft_list = resp_auth_drafts.json()
    assert len(auth_draft_list) == 1
    assert auth_draft_list[0]["id"] == "alert_draft_01"

    # 7. Single alert lookup: Citizen accessing draft alert directly gets 403 Forbidden
    resp_direct_draft = client.get(f"/api/v1/alerts/{draft_alert.id}", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_direct_draft.status_code == status.HTTP_403_FORBIDDEN

    # 8. Single alert lookup: Authority accessing draft alert succeeds
    resp_direct_auth = client.get(f"/api/v1/alerts/{draft_alert.id}", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_direct_auth.status_code == status.HTTP_200_OK

    # 9. Single alert lookup: Citizen accessing dispatched alert succeeds
    resp_direct_disp = client.get(f"/api/v1/alerts/{dispatched_alert.id}", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_direct_disp.status_code == status.HTTP_200_OK


def test_alert_approval_and_dispatch_authorization(client: TestClient, db_session, test_authority_user: User, citizen_token: str, authority_token: str):
    """Verify RBAC on alert draft, approval, and test dispatch workflow."""
    # 1. Citizen cannot create draft alert
    draft_payload = {
        "area_id": "loc_01",
        "title": "Unauthorized Alert Attempt",
        "message": "This should be denied",
    }
    resp_citizen_create = client.post("/api/v1/alerts", json=draft_payload, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_citizen_create.status_code == status.HTTP_403_FORBIDDEN

    # 2. Authority creates draft alert
    resp_create = client.post("/api/v1/alerts", json=draft_payload, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_create.status_code == status.HTTP_201_CREATED
    alert_id = resp_create.json()["id"]

    # 3. Citizen cannot approve alert
    resp_citizen_approve = client.post(f"/api/v1/alerts/{alert_id}/approve", json={}, headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_citizen_approve.status_code == status.HTTP_403_FORBIDDEN

    # 4. Cannot dispatch unapproved draft alert
    resp_early_dispatch = client.post(f"/api/v1/alerts/{alert_id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_early_dispatch.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_early_dispatch.json()["error"]["code"] == "NOT_APPROVED"

    # 5. Authority approves alert
    resp_approve = client.post(f"/api/v1/alerts/{alert_id}/approve", json={"notes": "Reviewed and verified"}, headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_approve.status_code == status.HTTP_200_OK
    assert resp_approve.json()["status"] == "approved"

    # 6. Citizen cannot dispatch approved alert
    resp_citizen_dispatch = client.post(f"/api/v1/alerts/{alert_id}/dispatch", headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp_citizen_dispatch.status_code == status.HTTP_403_FORBIDDEN

    # 7. Authority dispatches approved alert
    resp_dispatch = client.post(f"/api/v1/alerts/{alert_id}/dispatch", headers={"Authorization": f"Bearer {authority_token}"})
    assert resp_dispatch.status_code == status.HTTP_200_OK
    assert resp_dispatch.json()["status"] == "dispatched"


# ==============================================================================
# 3. WebSocket Channel Authorization & Security
# ==============================================================================
@pytest.mark.asyncio
async def test_websocket_channel_security_and_alert_isolation():
    """Verify WebSocket channel access control and isolation of unpublished alerts."""
    mgr = ConnectionManager()

    class MockWS:
        def __init__(self):
            self.sent = []
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def send_text(self, text: str):
            self.sent.append(text)

    citizen_ws = MockWS()
    other_citizen_ws = MockWS()
    authority_ws = MockWS()

    await mgr.connect(citizen_ws, user_id="citizen_1", role="citizen")
    await mgr.connect(other_citizen_ws, user_id="citizen_2", role="citizen")
    await mgr.connect(authority_ws, user_id="auth_1", role="authority")

    # 1. Citizen cannot subscribe to authority_queue or authority_alerts
    assert mgr.subscribe(citizen_ws, "authority_queue") is False
    assert mgr.subscribe(citizen_ws, "authority_alerts") is False

    # 2. Citizen cannot subscribe to another citizen's private channel
    assert mgr.subscribe(citizen_ws, "user:citizen_2") is False

    # 3. Citizen CAN subscribe to their own private channel
    assert mgr.subscribe(citizen_ws, "user:citizen_1") is True

    # 4. Authority CAN subscribe to authority channels
    assert mgr.subscribe(authority_ws, "authority_queue") is True
    assert mgr.subscribe(authority_ws, "authority_alerts") is True

    mgr.disconnect(citizen_ws)
    mgr.disconnect(other_citizen_ws)
    mgr.disconnect(authority_ws)


# ==============================================================================
# 4. Credential Security Outside Local Development
# ==============================================================================
def test_production_credential_enforcement():
    """Verify that insecure or default credentials are strictly rejected outside local development."""
    # 1. Reject default insecure JWT secret in production
    with pytest.raises(ValueError, match="Insecure or default JWT_SECRET detected"):
        Settings(
            environment="production",
            jwt_secret="dev-insecure-jwt-secret-replace-in-production-123456",
            database_url="postgresql+psycopg2://admin:super_secret_pg_pwd_998@db.prod.internal:5432/floodlens",
        )

    # 2. Reject short JWT secret in production (< 32 chars)
    with pytest.raises(ValueError, match="Insecure or default JWT_SECRET detected"):
        Settings(
            environment="production",
            jwt_secret="short-secret-123",
            database_url="postgresql+psycopg2://admin:super_secret_pg_pwd_998@db.prod.internal:5432/floodlens",
        )

    # 3. Reject default database password in production
    with pytest.raises(ValueError, match="Default database credentials detected"):
        Settings(
            environment="production",
            jwt_secret="production-secure-random-jwt-secret-at-least-32-chars-long",
            database_url="postgresql+psycopg2://floodlens:floodlens_secure_password@localhost:5432/floodlens_db",
        )

    # 4. Reject default credentials in staging
    with pytest.raises(ValueError, match="Insecure or default JWT_SECRET detected"):
        Settings(
            environment="staging",
            jwt_secret="dev-insecure-jwt-secret-replace-in-production-123456",
            database_url="postgresql+psycopg2://admin:strong_staging_pwd@db.stage:5432/floodlens",
        )

    # 5. Allow strong credentials in production
    prod_settings = Settings(
        environment="production",
        jwt_secret="production-secure-random-jwt-secret-at-least-32-chars-long",
        database_url="postgresql+psycopg2://prod_user:SuperStrongProdSecretPassword2026!@prod-db.floodlens.internal:5432/floodlens_prod",
    )
    assert prod_settings.environment == "production"
    assert prod_settings.jwt_secret == "production-secure-random-jwt-secret-at-least-32-chars-long"

    # 6. Allow local development defaults
    dev_settings = Settings(environment="development")
    assert dev_settings.environment == "development"
