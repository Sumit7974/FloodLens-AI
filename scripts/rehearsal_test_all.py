"""FloodLens AI — Task 9 End-to-End Rehearsal Verification Script.

Executes all core rehearsal checks in an isolated test harness:
- AI/ML candidate-leakfree-v1 inference
- Input validation & missing critical input safety
- Authenticated FastAPI ingestion & retrieval
- Multi-horizon risk mapping
- Spatial GIS & candidate route hazard screening
- Authority advisory drafting & approval workflow
- Citizen assistance triage & request ownership
- Negative / failure edge-case handling
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "rehearsal-secret-key-32-chars-minimum-floodlens"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import create_application
from app.models.asset import Asset, Facility, RoadHazard
from app.models.enums import OperationalMode, UserRole
from app.models.location import Location
from app.models.user import User
from app.services.demo_participants import demo_participant_registry
from ml.scripts.submit_demo_forecast import build_demo_forecast
from ml.src.predict import FloodRiskPredictor


def run_rehearsal():
    results = {}
    print("=" * 80)
    print("FLOODLENS AI — TASK 9 FULL REHEARSAL VERIFICATION")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # 1. AI/ML PREDICTION FLOW WITH candidate-leakfree-v1
    # --------------------------------------------------------------------------
    print("\n--- STEP 3: AI/ML Prediction Flow ---")
    predictor = FloodRiskPredictor(models_dir=REPO_ROOT / "ml" / "models", model_version="candidate-leakfree-v1")
    assert set(predictor.models.keys()) == {1, 3, 6}, f"Expected models {1, 3, 6}, got {list(predictor.models.keys())}"
    print(f"Loaded candidate-leakfree-v1 models for horizons: {list(predictor.models.keys())}")

    with open(REPO_ROOT / "ml" / "examples" / "historical_demo_inputs.json") as f:
        demo_inputs = json.load(f)

    # Valid prediction
    forecast = predictor.predict(
        features=demo_inputs,
        location_id="loc_sunsari_chatara",
        event_id="evt_historical_2024",
        mode="historical_demo",
    )
    print(f"Forecast ID: {forecast['forecast_id']}")
    print(f"Model version: {forecast['model_version']}")
    print(f"Data quality: {forecast['data_quality']}")
    print(f"Mode: {forecast['mode']}")
    for h in forecast["horizons"]:
        print(f"  +{h['hours']}h: risk_level={h['risk_level']}, calibrated_prob={h['calibrated_probability']}")
        assert h["calibrated_probability"] is None, "Leak-free uncalibrated RF must have calibrated_probability=None"
        assert h["risk_level"] in ["low", "moderate", "high", "critical"]

    results["ml_valid_horizons"] = [(h["hours"], h["risk_level"], h["calibrated_probability"]) for h in forecast["horizons"]]

    # Missing critical inputs safety check
    empty_features = {"temperature_c": 25.0}  # Missing river_stage_m, rainfall_rolling_24h_mm, rainfall_mm
    failed_forecast = predictor.predict(features=empty_features, location_id="loc_test")
    assert failed_forecast["data_quality"] == "UNAVAILABLE"
    assert all(h["risk_level"] == "unknown" for h in failed_forecast["horizons"])
    print("Missing critical inputs safety: REJECTED safely with data_quality='UNAVAILABLE' and risk='unknown'")
    results["ml_safety_guard"] = "PASS"

    # --------------------------------------------------------------------------
    # 2. ISOLATED TEST ENVIRONMENT & FASTAPI TESTCLIENT SETUP
    # --------------------------------------------------------------------------
    print("\n--- STEP 2 & 4: Authenticated Backend Persistence ---")
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    app = create_application()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    # Health check
    res_health = client.get("/api/v1/health")
    assert res_health.status_code == 200
    print(f"Liveness /health: {res_health.json()}")

    # Readiness check
    res_ready = client.get("/api/v1/ready")
    print(f"Readiness /ready: {res_ready.json()}")

    # Create test users
    authority_user = User(
        email="authority.demo@floodlens.org",
        hashed_password=hash_password("DemoAuthorityPassword123!"),
        full_name="EOC Rehearsal Lead",
        role=UserRole.AUTHORITY,
        is_active=True,
    )
    citizen_user = User(
        email="citizen.demo@floodlens.org",
        hashed_password=hash_password("DemoCitizenPassword123!"),
        full_name="Citizen Rehearsal User",
        role=UserRole.CITIZEN,
        is_active=True,
    )
    db.add_all([authority_user, citizen_user])
    db.commit()
    db.refresh(authority_user)
    db.refresh(citizen_user)

    auth_token = create_access_token(subject=authority_user.id, role=authority_user.role.value)
    citizen_token = create_access_token(subject=citizen_user.id, role=citizen_user.role.value)
    auth_headers = {"Authorization": f"Bearer {auth_token}"}
    citizen_headers = {"Authorization": f"Bearer {citizen_token}"}
    demo_participant_registry.register_participant(authority_user.id)
    demo_participant_registry.register_participant(citizen_user.id)

    # Register location
    loc_payload = {
        "id": "loc_sunsari_chatara",
        "name": "Chatara Headworks & Barahachhetra",
        "admin_level": 4,
        "crs_source": "EPSG:4326",
        "geometry": {"type": "Point", "coordinates": [87.150, 26.820]},
        "metadata_json": {"river": "Koshi", "district": "Sunsari"},
    }
    res_loc = client.post("/api/v1/locations", json=loc_payload, headers=auth_headers)
    assert res_loc.status_code == 201
    print("Registered location: loc_sunsari_chatara")

    # Ingest forecast
    forecast_ingest_payload = build_demo_forecast(demo_inputs, location_id="loc_sunsari_chatara", model_version="candidate-leakfree-v1")
    res_ingest = client.post("/api/v1/predictions/ingest", json=forecast_ingest_payload, headers=auth_headers)
    assert res_ingest.status_code == 201, f"Ingest failed: {res_ingest.text}"
    ingested = res_ingest.json()
    print(f"Ingested forecast ID: {ingested['forecast_id']} (HTTP 201)")
    results["backend_ingest"] = "PASS"

    # Retrieve latest forecast
    res_latest = client.get("/api/v1/predictions/latest?location_id=loc_sunsari_chatara")
    assert res_latest.status_code == 200
    retrieved = res_latest.json()
    assert retrieved["forecast_id"] == ingested["forecast_id"]
    assert len(retrieved["horizons"]) == 3
    print(f"Retrieved latest forecast: {retrieved['forecast_id']}, {len(retrieved['horizons'])} horizons matching")
    results["backend_retrieval"] = "PASS"

    # Multi-horizon risk map endpoint
    res_map = client.get("/api/v1/predictions/map")
    assert res_map.status_code == 200
    map_data = res_map.json()
    print(f"Risk map endpoint: active horizons={map_data.get('active_horizons', [])}, features count={len(map_data.get('features', []))}")
    results["backend_map"] = "PASS"

    # --------------------------------------------------------------------------
    # 3. GIS AND ROUTE ASSESSMENT REHEARSAL
    # --------------------------------------------------------------------------
    print("\n--- STEP 6: GIS and Candidate Route Hazard Screening ---")
    from app.core.spatial import to_wkt_element

    # Register event
    event_payload = {
        "id": "evt_2024_koshi_demo",
        "region_id": "koshi_basin",
        "name": "Historical Koshi Basin Flood Episode (2024)",
        "start_at": "2024-07-08T00:00:00Z",
        "end_at": "2024-07-12T23:59:59Z",
        "mode": "historical_demo",
        "source_refs": {"telemetry": "DHM"},
        "description": "Historical monsoon flood rehearsal.",
    }
    res_ev = client.post("/api/v1/flood-events", json=event_payload, headers=auth_headers)
    assert res_ev.status_code == 201

    # Ingest observed flood extent
    extent_payload = {
        "event_id": "evt_2024_koshi_demo",
        "observed_at": "2024-07-08T10:15:00Z",
        "area_km2": 38.4,
        "method": "SAR_CHANGE",
        "confidence": 0.92,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[87.10, 26.80], [87.20, 26.80], [87.20, 26.85], [87.10, 26.85], [87.10, 26.80]]],
        },
    }
    res_ext = client.post("/api/v1/flood-events/evt_2024_koshi_demo/extent", json=extent_payload, headers=auth_headers)
    assert res_ext.status_code == 201
    print("Ingested satellite flood extent: 38.4 km2")

    # Seed road hazard intersecting candidate route
    hazard = RoadHazard(
        id="rh_koshi_highway_km14",
        road_id="Koshi-Hwy-01",
        hazard_type="submerged",
        status="active",
        geometry=to_wkt_element({"type": "Point", "coordinates": [87.15, 26.82]}, expected_type="POINT"),
        observed_at=datetime(2024, 7, 8, 9, 0, tzinfo=timezone.utc),
        source="Field Observation",
        confidence=0.9,
    )
    db.add(hazard)
    db.commit()

    # Route screening (candidate path crosses the submerged section)
    route_req = {
        "route": {
            "type": "LineString",
            "coordinates": [[87.12, 26.81], [87.18, 26.83]],
        },
        "event_id": "evt_2024_koshi_demo",
        "buffer_meters": 150.0,
    }
    res_route = client.post("/api/v1/routes/assess", json=route_req)
    assert res_route.status_code == 200
    route_data = res_route.json()
    print(f"Candidate route screening status: {route_data['route_status']}, assessment={route_data['assessment_status']}, hazards={len(route_data['hazards_detected'])}")
    assert route_data["route_status"] == "hazards_detected"
    assert len(route_data["hazards_detected"]) >= 1
    # Verify non-guarantee disclaimer
    assert any("not" in lim.lower() and "safe" in lim.lower() for lim in route_data.get("limitations", [])), "Must state route is not a verified safe guarantee"
    results["gis_route_screening"] = "PASS"

    # --------------------------------------------------------------------------
    # 4. INTERNAL ADVISORY DRAFTING & SIMULATED ALERT WORKFLOW
    # --------------------------------------------------------------------------
    print("\n--- STEP 7: Internal Advisory & Alert Safety ---")
    alert_payload = {
        "area_id": "loc_sunsari_chatara",
        "title": "Koshi Basin Telemetry Surge Advisory",
        "message": "High discharge stage observed at Chatara headworks. Activate municipal EOC standby.",
        "mode": "historical_demo",
        "target_channels": ["in_app"],
    }
    # Draft alert
    res_draft = client.post("/api/v1/alerts", json=alert_payload, headers=auth_headers)
    assert res_draft.status_code == 201
    draft_alert = res_draft.json()
    assert draft_alert["status"] == "draft"
    print(f"Created internal advisory draft: ID={draft_alert['id']}, status='draft' (no public broadcast)")

    # Approve alert
    res_approve = client.post(f"/api/v1/alerts/{draft_alert['id']}/approve", json={"notes": "Approved for historical demo"}, headers=auth_headers)
    assert res_approve.status_code == 200
    approved = res_approve.json()
    assert approved["status"] == "approved"
    print(f"Approved advisory: status='approved'")

    # Simulated dispatch
    res_dispatch = client.post(f"/api/v1/alerts/{draft_alert['id']}/dispatch", json={"simulated": True, "notes": "Demo rehearsal"}, headers=auth_headers)
    assert res_dispatch.status_code == 200
    dispatched = res_dispatch.json()
    assert dispatched["status"] == "dispatched"
    assert "[DEMO" in dispatched["title"] or "[TEST" in dispatched["title"], "Dispatched alert title must enforce DEMO prefix"
    print(f"Simulated dispatch completed: status='dispatched', title='{dispatched['title']}' (no external SMS/sirens)")
    results["advisory_workflow"] = "PASS"

    # --------------------------------------------------------------------------
    # 5. CITIZEN APP WORKFLOW & ASSISTANCE PRIVACY
    # --------------------------------------------------------------------------
    print("\n--- STEP 8: Citizen Assistance Triage & Privacy ---")
    help_payload = {
        "latitude": 26.8210,
        "longitude": 87.1520,
        "category": "evacuation",
        "people_count": 4,
        "details": "[FLOODLENS HISTORICAL TEST ONLY - NOT AN EMERGENCY] Simulated shelter request",
    }
    res_help = client.post("/api/v1/assistance", json=help_payload, headers=citizen_headers)
    assert res_help.status_code == 201
    help_req = res_help.json()
    assert help_req["status"] == "pending"
    assert help_req["citizen_id"] == citizen_user.id
    print(f"Submitted test citizen assistance request: ID={help_req['id']}, status='pending'")

    # Citizen checks own request history
    res_my_requests = client.get("/api/v1/assistance/mine", headers=citizen_headers)
    assert res_my_requests.status_code == 200
    my_reqs = res_my_requests.json()
    assert any(r["id"] == help_req["id"] for r in my_reqs)
    print(f"Citizen retrieved private history: {len(my_reqs)} request(s) found")

    # Authority triage queue
    res_triage = client.get("/api/v1/assistance", headers=auth_headers)
    assert res_triage.status_code == 200
    queue = res_triage.json()
    assert any(r["id"] == help_req["id"] for r in queue)
    print(f"Authority triaged assistance queue: {len(queue)} request(s) visible to responders")
    results["citizen_assistance"] = "PASS"

    # --------------------------------------------------------------------------
    # 6. NEGATIVE & FAILURE TESTING SCENARIOS
    # --------------------------------------------------------------------------
    print("\n--- STEP 9: Negative & Safe Failure Handling ---")
    
    # Missing auth token
    res_no_auth = client.get("/api/v1/assistance/mine")
    assert res_no_auth.status_code == 401
    print("Unauthenticated request: HTTP 401 (rejected)")

    # Expired / invalid token
    res_bad_token = client.get("/api/v1/assistance/mine", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res_bad_token.status_code == 401
    print("Invalid JWT: HTTP 401 (rejected)")

    # Citizen trying to ingest forecast (RBAC violation)
    res_forbidden = client.post("/api/v1/predictions/ingest", json=forecast_ingest_payload, headers=citizen_headers)
    assert res_forbidden.status_code == 403
    print("Citizen role on authority endpoint: HTTP 403 Forbidden (RBAC enforced)")

    # Missing location forecast
    res_missing_loc = client.get("/api/v1/predictions/latest?location_id=nonexistent_loc_999")
    assert res_missing_loc.status_code == 404
    print("Missing forecast for location: HTTP 404 DataUnavailableError (graceful empty state)")

    # Invalid route coordinates
    res_bad_route = client.post("/api/v1/routes/assess", json={"route_id": "r1", "route_geometry": {"type": "Point", "coordinates": [0, 0]}})
    assert res_bad_route.status_code in [400, 422]
    print("Invalid geometry on route screening: HTTP 400/422 (rejected)")

    results["failure_testing"] = "PASS"

    print("\n" + "=" * 80)
    print("ALL REHEARSAL CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    return results


if __name__ == "__main__":
    res = run_rehearsal()
    print("Rehearsal summary:", json.dumps(res, indent=2))
