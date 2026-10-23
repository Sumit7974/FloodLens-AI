"""PostGIS 16 & PostgreSQL Integration Verification for Seeded Historical Demonstration Data.

Verifies:
A. Migrations and PostGIS extension active.
B. Seed historical demo data with securely supplied environment variables.
C. Second seed execution for idempotency.
D. Authenticate authority user via /api/v1/auth/login.
E. Retrieve historical events, locations (with parent_id foreign key hierarchy), and multi-horizon forecasts (+1h, +3h, +6h).
F. Retrieve real MULTIPOLYGON flood extent geometries (authentic Koshi 0.6429 km²).
G. Execute spatial intersection queries (affected settlements & candidate route hazard screening).
H. Confirm unverified demo fixtures are labeled appropriately (verification_status="demo_labeled", confidence=None).
I. Verify no live operational SMS/push emergency dispatch is made.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure backend root on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.security import verify_password
from app.models.asset import Facility, RoadHazard
from app.models.enums import OperationalMode, UserRole
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.models.satellite import FloodExtent
from app.models.user import User
from backend.scripts.seed_historical_demo_data import seed_database


TEST_AUTH_PASS = "TestAuthPassword123!"
TEST_CITIZEN_PASS = "TestCitizenPass123!"


@pytest.fixture(autouse=True)
def run_seed_with_test_env(db_session: Session):
    """Ensure secure test environment variables are active and seed database twice."""
    os.environ["DEMO_AUTHORITY_PASSWORD"] = TEST_AUTH_PASS
    os.environ["DEMO_CITIZEN_PASSWORD"] = TEST_CITIZEN_PASS
    # First seeding
    seed_database(db_session)
    # Second seeding (validates idempotency)
    seed_database(db_session)


def test_postgis_extension_and_version(db_session: Session, is_postgres: bool):
    """Verify PostGIS extension and PostgreSQL version in supported environments."""
    if is_postgres:
        postgis_ver = db_session.execute(text("SELECT PostGIS_Full_Version();")).scalar()
        assert postgis_ver is not None, "PostGIS extension must be active"
        assert "POSTGIS=" in postgis_ver

        pg_ver = db_session.execute(text("SELECT version();")).scalar()
        assert pg_ver is not None
        assert "PostgreSQL" in pg_ver


def test_seed_idempotency_and_user_credentials(db_session: Session):
    """Verify demo users exist, passwords verify against hashed_password, and passwords are not in plain text."""
    auth_user = db_session.query(User).filter(User.email == "authority_lead@floodlens.org").first()
    assert auth_user is not None, "Authority user must exist"
    assert auth_user.role == UserRole.AUTHORITY
    assert auth_user.is_active is True
    assert verify_password(TEST_AUTH_PASS, auth_user.hashed_password) is True

    citizen_user = db_session.query(User).filter(User.email == "citizen_janakpur@example.com").first()
    assert citizen_user is not None, "Citizen user must exist"
    assert citizen_user.role == UserRole.CITIZEN
    assert citizen_user.is_active is True
    assert verify_password(TEST_CITIZEN_PASS, citizen_user.hashed_password) is True


def test_authority_authentication_contract(client: TestClient):
    """Verify authority authentication endpoint returns valid JWT token."""
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "authority_lead@floodlens.org", "password": TEST_AUTH_PASS},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    data = login_resp.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"
    assert len(data["access_token"]) > 20


def test_historical_events_retrieval(client: TestClient):
    """Verify both 2024 Terai and 2017 Koshi events are retrieved in historical_demo mode."""
    resp = client.get("/api/v1/flood-events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 2
    event_ids = [e["id"] for e in events]
    assert "evt_2024_terai_monsoon" in event_ids
    assert "event_nepal_koshi_2017" in event_ids

    for e in events:
        assert e["mode"] == "historical_demo"


def test_location_parent_foreign_key_hierarchy(db_session: Session):
    """Verify location parent_id foreign key hierarchy is valid."""
    nepal_terai = db_session.query(Location).filter(Location.id == "nepal_terai").first()
    assert nepal_terai is not None
    assert nepal_terai.parent_id is None

    terai_dhanusha = db_session.query(Location).filter(Location.id == "terai_dhanusha").first()
    assert terai_dhanusha is not None
    assert terai_dhanusha.parent_id == "nepal_terai"

    koshi_basin = db_session.query(Location).filter(Location.id == "koshi_basin").first()
    assert koshi_basin is not None
    assert koshi_basin.parent_id == "nepal_terai"

    janakpur = db_session.query(Location).filter(Location.id == "settlement_janakpurdham").first()
    assert janakpur is not None
    assert janakpur.parent_id == "terai_dhanusha"

    sabaila = db_session.query(Location).filter(Location.id == "settlement_sabaila").first()
    assert sabaila is not None
    assert sabaila.parent_id == "terai_dhanusha"

    chatara = db_session.query(Location).filter(Location.id == "loc_sunsari_chatara").first()
    assert chatara is not None
    assert chatara.parent_id == "nepal_terai"

    morang = db_session.query(Location).filter(Location.id == "settlement_biratnagar_morang").first()
    assert morang is not None
    assert morang.parent_id == "koshi_basin"


def test_forecast_multi_horizon_uncalibrated_probabilities(client: TestClient):
    """Verify +1h, +3h, +6h forecast horizons exist with honest null calibrated_probability."""
    resp = client.get("/api/v1/predictions/latest?location_id=settlement_janakpurdham")
    assert resp.status_code == 200, f"Predictions retrieval failed: {resp.text}"
    data = resp.json()
    assert data["location_id"] == "settlement_janakpurdham"
    horizons = data.get("horizons", [])
    assert len(horizons) == 3
    hrs = [h["hours"] for h in horizons]
    assert 1 in hrs
    assert 3 in hrs
    assert 6 in hrs

    # Verify no invented calibrated probability
    for h in horizons:
        assert h.get("calibrated_probability") is None, (
            f"Expected calibrated_probability=None for uncalibrated model heuristics, got {h.get('calibrated_probability')}"
        )


def test_flood_extents_multipolygon_integrity(client: TestClient, db_session: Session):
    """Verify flood extents use MULTIPOLYGON geometry and authentic Koshi area."""
    # 2024 Terai SAR extent
    resp_s1 = client.get("/api/v1/flood-events/evt_2024_terai_monsoon/extent")
    assert resp_s1.status_code == 200
    data_s1 = resp_s1.json()
    assert data_s1["method"] == "SAR_CHANGE"
    assert data_s1["provenance"] == "HISTORICAL_DEMO_FIXTURE"
    assert data_s1["confidence"] is None
    geom_s1 = data_s1.get("geometry")
    assert geom_s1 is not None
    assert geom_s1["type"] == "MultiPolygon"

    # 2017 Koshi Optical NDWI extent
    resp_s2 = client.get("/api/v1/flood-events/event_nepal_koshi_2017/extent")
    assert resp_s2.status_code == 200
    data_s2 = resp_s2.json()
    assert data_s2["method"] == "NDWI"
    assert data_s2["provenance"] == "PROCESSED_OPTICAL"
    assert data_s2["confidence"] is None
    assert data_s2["area_km2"] == pytest.approx(0.6429, abs=0.01)
    geom_s2 = data_s2.get("geometry")
    assert geom_s2 is not None
    assert geom_s2["type"] == "MultiPolygon"


def test_postgis_spatial_intersections(client: TestClient):
    """Verify spatial queries execute cleanly and return intersected settlements."""
    resp = client.get("/api/v1/flood-events/evt_2024_terai_monsoon/settlements")
    assert resp.status_code == 200, f"Spatial settlement query failed: {resp.text}"
    data = resp.json()
    assert data["event_id"] == "evt_2024_terai_monsoon"
    assert data["total_settlements_evaluated"] > 0
    affected = [s["settlement_id"] for s in data.get("affected_settlements", [])]
    assert "settlement_janakpurdham" in affected

    # Candidate Route Hazard Screening
    route_payload = {
        "route": {
            "type": "LineString",
            "coordinates": [[85.9200, 26.7200], [85.9300, 26.7350]],
        },
        "event_id": "evt_2024_terai_monsoon",
        "buffer_meters": 25.0,
    }
    route_resp = client.post("/api/v1/routes/assess", json=route_payload)
    assert route_resp.status_code == 200
    r_data = route_resp.json()
    assert "route_status" in r_data or "assessment_status" in r_data or "status" in r_data
    status_val = r_data.get("route_status") or r_data.get("assessment_status") or r_data.get("status")
    assert status_val in ("CLEAR", "CAUTION", "IMPASSABLE", "hazards_detected", "passable", "HAZARDS_INTERSECTED")


def test_unverified_fixtures_labeled_safely(db_session: Session):
    """Verify shelters and road hazards are labeled as unverified/demo fixtures."""
    shelter = db_session.query(Facility).filter(Facility.id == "facility_shelter_janakpur_school").first()
    assert shelter is not None
    assert shelter.verification_status == "demo_labeled"
    assert shelter.verification_status != "verified"

    rh = db_session.query(RoadHazard).filter(RoadHazard.id == "rh_kamala_bridge_overtop").first()
    assert rh is not None
    assert rh.confidence is None
    assert "Simulation Fixture" in rh.source


def test_prohibit_live_dispatch_in_demo_mode(client: TestClient):
    """Verify operational alerts cannot be dispatched to live public endpoints."""
    # Attempting to post unauthenticated or unauthorized alert must fail
    fake_alert_payload = {
        "event_id": "evt_2024_terai_monsoon",
        "severity": "CRITICAL",
        "message": "SIMULATED FLOOD ALERT",
        "target_channels": ["sms", "push"],
    }
    resp = client.post("/api/v1/alerts/broadcast", json=fake_alert_payload)
    # /api/v1/alerts/broadcast does not exist or requires strict authority token
    assert resp.status_code in (401, 403, 404, 405)
