"""Day 4 Integration and Regression Test Suite for FloodLens AI.

Validates:
1. Facilities API: Shelters and hospitals with map-ready coordinates, EPSG:4326 GeoJSON, verification states, empty data handling.
2. Route Hazard Assessment: Geographic spatial intersection screening, LineString validation, active vs cleared hazards, flood extent overlap, safe route false clean prevention.
3. Event Analytics: Evaluation.event_id filtering, multi-evaluation scoping, missing events, honest model status.
4. Historical Event Replay Timeline: Chronological sequencing, forecast vs observation vs evaluation, coverage summaries, no invented records.
5. Impact Report & Downloadable Exports: Event-scoped metrics, genuine downloadable JSON & CSV exports, Content-Disposition headers.
6. Security Regressions: Day 3 auth, role permissions, simulated-only alert dispatch, citizen privacy.
"""
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import uuid
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.spatial import to_wkt_element
from app.models.asset import Facility, RoadHazard
from app.models.enums import DataQuality, OperationalMode, RiskLevel
from app.models.evaluation import Evaluation
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.models.satellite import FloodExtent


# ==============================================================================
# 1. FACILITIES TESTS
# ==============================================================================

def test_shelters_retrieval_with_coordinates_and_verification(client: TestClient, db_session: Session):
    """Retrieve shelter facilities with map-ready GeoJSON Point coordinates, capacity, and limitations."""
    # 1. Verified shelter with coordinates
    shelter_1 = Facility(
        id=f"fac_sh_1_{uuid.uuid4().hex[:6]}",
        type="shelter",
        name="Janakpur Community Emergency Shelter",
        location=to_wkt_element({"type": "Point", "coordinates": [85.924, 26.728]}, expected_type="POINT"),
        verification_status="verified",
        status_checked_at=datetime.now(timezone.utc),
        capacity=500,
        contact_info="+977-41-520111",
        details={"source": "DHM Nepal", "amenities": ["generator", "potable_water"]},
    )
    # 2. Unverified shelter with coordinates
    shelter_2 = Facility(
        id=f"fac_sh_2_{uuid.uuid4().hex[:6]}",
        type="shelter",
        name="Jaleshwar School Hall",
        location=to_wkt_element({"type": "Point", "coordinates": [85.801, 26.647]}, expected_type="POINT"),
        verification_status="unverified",
        status_checked_at=None,
        capacity=None,
        contact_info=None,
        details={"notes": "Reported during 2024 monsoon"},
    )
    # 3. Demo-labeled shelter without geometry
    shelter_3 = Facility(
        id=f"fac_sh_3_{uuid.uuid4().hex[:6]}",
        type="shelter",
        name="Simulated Flood Relief Camp",
        location=None,
        verification_status="demo_labeled",
        capacity=200,
        contact_info="demo@floodlens.internal",
        details={"source": "simulation_engine"},
    )
    db_session.add_all([shelter_1, shelter_2, shelter_3])
    db_session.commit()

    resp = client.get("/api/v1/facilities/shelters")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["count"] >= 3
    assert "shelters" in data
    assert "data_notes" in data

    # Find created shelters
    sh_map = {s["id"]: s for s in data["shelters"]}
    assert shelter_1.id in sh_map
    s1 = sh_map[shelter_1.id]
    assert s1["name"] == "Janakpur Community Emergency Shelter"
    assert s1["verification_status"] == "verified"
    assert s1["capacity"] == 500
    assert s1["contact_info"] == "+977-41-520111"
    assert s1["location"] == {"type": "Point", "coordinates": [85.924, 26.728]}
    assert s1["longitude"] == 85.924
    assert s1["latitude"] == 26.728
    assert s1["source"] == "DHM Nepal"

    # Verify unverified caveats
    s2 = sh_map[shelter_2.id]
    assert s2["verification_status"] == "unverified"
    assert any("not been verified" in lim for lim in s2["limitations"])
    assert any("Capacity unknown" in lim for lim in s2["limitations"])

    # Verify missing geometry handling
    s3 = sh_map[shelter_3.id]
    assert s3["location"] is None
    assert s3["longitude"] is None
    assert s3["latitude"] is None
    assert any("coordinates are missing" in lim for lim in s3["limitations"])
    assert any("Simulated demonstration facility" in lim for lim in s3["limitations"])


def test_shelters_filter_by_verification_status(client: TestClient, db_session: Session):
    """Filter shelters by verified and unverified state."""
    uid = uuid.uuid4().hex[:6]
    f1 = Facility(
        id=f"fac_v_{uid}",
        type="shelter",
        name="Verified Alpha",
        verification_status="verified",
        details={},
    )
    f2 = Facility(
        id=f"fac_u_{uid}",
        type="shelter",
        name="Unverified Beta",
        verification_status="unverified",
        details={},
    )
    db_session.add_all([f1, f2])
    db_session.commit()

    resp = client.get("/api/v1/facilities/shelters?verification_status=verified")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    ids = [s["id"] for s in data["shelters"]]
    assert f1.id in ids
    assert f2.id not in ids


def test_hospitals_retrieval_and_empty_dataset(client: TestClient, db_session: Session):
    """Retrieve hospital records and verify empty dataset handling."""
    # Query with non-existent verification filter to verify empty dataset handling
    resp_empty = client.get("/api/v1/facilities/hospitals?verification_status=non_existent_status_xyz")
    assert resp_empty.status_code == status.HTTP_200_OK
    data_empty = resp_empty.json()
    assert data_empty["count"] == 0
    assert data_empty["hospitals"] == []

    # Insert a verified hospital
    hosp = Facility(
        id=f"fac_hosp_{uuid.uuid4().hex[:6]}",
        type="hospital",
        name="Janakpur Zonal Hospital",
        location=to_wkt_element({"type": "Point", "coordinates": [85.928, 26.732]}, expected_type="POINT"),
        verification_status="verified",
        status_checked_at=datetime.now(timezone.utc),
        contact_info="+977-41-520133",
        details={"icu_beds": 12, "source": "Ministry of Health"},
    )
    db_session.add(hosp)
    db_session.commit()

    resp = client.get("/api/v1/facilities/hospitals")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["count"] >= 1
    found = next((h for h in data["hospitals"] if h["id"] == hosp.id), None)
    assert found is not None
    assert found["name"] == "Janakpur Zonal Hospital"
    assert found["type"] == "hospital"
    assert found["location"] == {"type": "Point", "coordinates": [85.928, 26.732]}
    assert found["contact_info"] == "+977-41-520133"


# ==============================================================================
# 2. ROUTE HAZARD ASSESSMENT TESTS
# ==============================================================================

def test_route_assess_invalid_geometry_inputs(client: TestClient):
    """Validate candidate route input schema constraints."""
    # 1. Not a LineString
    resp1 = client.post(
        "/api/v1/routes/assess",
        json={"route": {"type": "Point", "coordinates": [85.0, 26.0]}},
    )
    assert resp1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. Fewer than 2 coordinates
    resp2 = client.post(
        "/api/v1/routes/assess",
        json={"route": {"type": "LineString", "coordinates": [[85.0, 26.0]]}},
    )
    assert resp2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 3. Coordinates out of range (longitude > 180)
    resp3 = client.post(
        "/api/v1/routes/assess",
        json={"route": {"type": "LineString", "coordinates": [[185.0, 26.0], [85.0, 26.0]]}},
    )
    assert resp3.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 4. Latitude out of range
    resp4 = client.post(
        "/api/v1/routes/assess",
        json={"route": {"type": "LineString", "coordinates": [[85.0, -95.0], [85.0, 26.0]]}},
    )
    assert resp4.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_route_assess_intersects_active_road_hazard(client: TestClient, db_session: Session):
    """Route assessment detects intersection with an active road hazard."""
    # Route across Janakpur: (85.80, 26.70) -> (85.90, 26.70)
    # Hazard intersects: (85.85, 26.65) -> (85.85, 26.75)
    hazard_id = f"rh_act_{uuid.uuid4().hex[:6]}"
    hazard = RoadHazard(
        id=hazard_id,
        road_id="NH-02",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.85, 26.65], [85.85, 26.75]]},
            expected_type="LINESTRING",
        ),
        status="active",
        source="Copernicus_Emergency_Management",
        observed_at=datetime.now(timezone.utc),
        confidence=0.92,
    )
    db_session.add(hazard)
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.80, 26.70], [85.90, 26.70]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "buffer_meters": 50.0},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["route_status"] == "hazards_detected"
    assert data["assessment_status"] == "HAZARDS_INTERSECTED"
    assert data["hazards_intersected_count"] >= 1
    found_hazard = next((h for h in data["hazards_detected"] if h["hazard_id"] == hazard_id), None)
    assert found_hazard is not None
    assert found_hazard["hazard_type"] == "submerged"
    assert found_hazard["source_layer"] == "road_hazard"
    assert found_hazard["status"] == "active"
    assert found_hazard["confidence"] == 0.92


def test_route_assess_cleared_and_stale_hazards_excluded(client: TestClient, db_session: Session):
    """Cleared hazards and hazards observed after evaluation cutoff are excluded from screening."""
    now = datetime.now(timezone.utc)
    # 1. Cleared hazard
    rh_cleared = RoadHazard(
        id=f"rh_clr_{uuid.uuid4().hex[:6]}",
        hazard_type="debris",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.50, 26.50], [85.50, 26.60]]},
            expected_type="LINESTRING",
        ),
        status="cleared",
        observed_at=now - timedelta(hours=2),
    )
    # 2. Future hazard relative to cutoff
    rh_future = RoadHazard(
        id=f"rh_fut_{uuid.uuid4().hex[:6]}",
        hazard_type="bridge_closed",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.50, 26.50], [85.50, 26.60]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=now,
    )
    db_session.add_all([rh_cleared, rh_future])
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.45, 26.55], [85.55, 26.55]],
    }
    # Cutoff time set to 1 hour ago (excludes rh_future)
    cutoff = (now - timedelta(hours=1)).isoformat()
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "evaluation_time": cutoff},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    intersected_ids = [h["hazard_id"] for h in data["hazards_detected"]]
    assert rh_cleared.id not in intersected_ids
    assert rh_future.id not in intersected_ids


def test_route_assess_intersects_event_flood_extent(client: TestClient, db_session: Session, authority_token: str):
    """Route assessment screens against satellite flood extent polygons for a requested event."""
    evt_id = f"evt_route_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "dhanusha",
            "name": "Route Flood Test Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Ingest flood polygon covering (85.80, 26.70) to (85.85, 26.75)
    ext_id = f"ext_route_{uuid.uuid4().hex[:6]}"
    client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json={
            "id": ext_id,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "MNDWI",
            "area_km2": 15.0,
            "confidence": 0.95,
            "source_scene_ids": ["S2A_TEST_01"],
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [85.80, 26.70],
                        [85.85, 26.70],
                        [85.85, 26.75],
                        [85.80, 26.75],
                        [85.80, 26.70],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Candidate route crossing through the flood extent
    route_inundated = {
        "type": "LineString",
        "coordinates": [[85.78, 26.72], [85.87, 26.72]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": route_inundated, "event_id": evt_id},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["route_status"] == "hazards_detected"
    assert data["assessment_status"] == "HAZARDS_INTERSECTED"
    extent_hazard = next((h for h in data["hazards_detected"] if h["hazard_id"] == ext_id), None)
    assert extent_hazard is not None
    assert extent_hazard["source_layer"] == "flood_extent"
    assert extent_hazard["hazard_type"] == "observed_flood_extent"


def test_route_assess_no_intersections_never_claims_safe(client: TestClient, db_session: Session):
    """Route without intersections returns 'conditional' and explicit disclaimers, never 'safe'."""
    # Insert an active hazard far away
    hazard = RoadHazard(
        id=f"rh_far_{uuid.uuid4().hex[:6]}",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.00, 27.00], [87.05, 27.00]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(hazard)
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.10, 25.10], [85.15, 25.10]],
    }
    resp = client.post("/api/v1/routes/assess", json={"route": candidate_route})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["route_status"] == "conditional"
    assert data["assessment_status"] == "NO_KNOWN_INTERSECTIONS"
    assert data["hazards_intersected_count"] == 0
    # Crucial safety requirement: Never infer safe from absence of intersections
    assert any("NEVER infer that a candidate route is safe" in lim for lim in data["limitations"])


def test_route_assess_missing_event_returns_404(client: TestClient):
    """Assessing route against a non-existent event ID returns 404 EVENT_NOT_FOUND."""
    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.10, 25.10], [85.15, 25.10]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "event_id": "nonexistent-event-9999"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    err = resp.json()["error"]
    assert err["code"] == "EVENT_NOT_FOUND"


# ==============================================================================
# 3. EVENT ANALYTICS TESTS
# ==============================================================================

def test_analytics_event_scoped_filtering(client: TestClient, db_session: Session, authority_token: str):
    """Analytics strictly filters evaluations by Evaluation.event_id == event_id."""
    evt1_id = f"evt_an1_{uuid.uuid4().hex[:6]}"
    evt2_id = f"evt_an2_{uuid.uuid4().hex[:6]}"

    for eid in (evt1_id, evt2_id):
        client.post(
            "/api/v1/flood-events",
            json={
                "id": eid,
                "region_id": "terai_basin",
                "name": f"Analytics Test {eid}",
                "start_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={"Authorization": f"Bearer {authority_token}"},
        )

    # Evaluations for Event 1
    eval1 = Evaluation(
        id=f"ev_1_{uuid.uuid4().hex[:6]}",
        event_id=evt1_id,
        target_type="flood_extent",
        baseline_version="baseline-v1",
        candidate_version="candidate-v2",
        metrics={"iou": 0.84, "f1_score": 0.91, "precision": 0.89},
        reference_id="ref_copernicus_ground_truth",
        notes="Evaluated against Copernicus EMS rapid mapping",
    )
    eval2 = Evaluation(
        id=f"ev_2_{uuid.uuid4().hex[:6]}",
        event_id=evt1_id,
        target_type="risk_forecast",
        baseline_version="baseline-v1",
        candidate_version=None,
        metrics={"lead_time_hours": 6, "brier_score": 0.12},
        reference_id="gauge_sensor_observed",
    )
    # Evaluation for Event 2 (must be excluded from Event 1 query)
    eval_unrelated = Evaluation(
        id=f"ev_unrelated_{uuid.uuid4().hex[:6]}",
        event_id=evt2_id,
        target_type="flood_extent",
        baseline_version="baseline-v1",
        metrics={"iou": 0.45},
    )
    db_session.add_all([eval1, eval2, eval_unrelated])
    db_session.commit()

    resp = client.get(f"/api/v1/analytics/events/{evt1_id}")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["event_id"] == evt1_id
    assert data["evaluations_count"] == 2
    assert data["status"] == "evaluations_available"

    result_ids = [r["id"] for r in data["results"]]
    assert eval1.id in result_ids
    assert eval2.id in result_ids
    assert eval_unrelated.id not in result_ids

    ev1_res = next(r for r in data["results"] if r["id"] == eval1.id)
    assert ev1_res["target_type"] == "flood_extent"
    assert ev1_res["baseline_version"] == "baseline-v1"
    assert ev1_res["candidate_version"] == "candidate-v2"
    assert ev1_res["metrics"]["iou"] == 0.84
    assert ev1_res["reference_id"] == "ref_copernicus_ground_truth"


def test_analytics_missing_event_returns_404(client: TestClient):
    """Querying analytics for a non-existent event returns 404 EVENT_NOT_FOUND."""
    resp = client.get("/api/v1/analytics/events/unknown-event-id-999")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_analytics_empty_evaluations_distinction(client: TestClient, authority_token: str):
    """Event with zero evaluations returns empty list with status 'no_evaluations_recorded'."""
    evt_id = f"evt_empty_eval_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "terai_basin",
            "name": "Empty Eval Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    resp = client.get(f"/api/v1/analytics/events/{evt_id}")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["evaluations_count"] == 0
    assert data["results"] == []
    assert data["status"] == "no_evaluations_recorded"


def test_models_listing_honest_status(client: TestClient):
    """Listing models clearly marks baseline-v1 as demonstration prototype and era5-v1 as offline benchmark."""
    resp = client.get("/api/v1/models")
    assert resp.status_code == status.HTTP_200_OK
    models = resp.json()
    assert len(models) == 2
    versions = [m["version"] for m in models]
    assert "baseline-v1" in versions
    assert "era5-v1" in versions
    assert "candidate-v2" not in versions  # Fiction removed

    baseline = next(m for m in models if m["version"] == "baseline-v1")
    assert baseline["type"] == "demo_prototype"
    assert baseline["status"] == "demo_ready"
    assert any("PIPELINE TEST ONLY" in lim for lim in baseline["limitations"])

    era5 = next(m for m in models if m["version"] == "era5-v1")
    assert era5["type"] == "offline_benchmark"
    assert era5["status"] == "offline_research"
    assert any("RESEARCH PROTOTYPE" in lim for lim in era5["limitations"])


def test_models_training_job_returns_501_not_implemented(client: TestClient, authority_token: str, citizen_token: str):
    """POST /models/training-jobs must not claim queued jobs and must return 501 Not Implemented."""
    # 1. Citizen cannot access
    resp_cit = client.post(
        "/api/v1/models/training-jobs",
        json={"candidate_version": "era5-v1"},
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert resp_cit.status_code == status.HTTP_403_FORBIDDEN

    # 2. Authority gets 501 Not Implemented with truthful explanation
    resp_auth = client.post(
        "/api/v1/models/training-jobs",
        json={"candidate_version": "era5-v1"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert resp_auth.status_code == status.HTTP_501_NOT_IMPLEMENTED
    err = resp_auth.json()["error"]
    assert err["code"] == "TRAINING_NOT_IMPLEMENTED"
    assert "not implemented" in err["message"].lower()
    assert err["details"]["execution_environment"] == "offline_research_only"


# ==============================================================================
# 4. HISTORICAL EVENT REPLAY TIMELINE TESTS
# ==============================================================================

def test_event_timeline_chronological_ordering(client: TestClient, db_session: Session, authority_token: str):
    """Timeline orders event start, forecast runs, satellite extents, evaluations, and end chronologically."""
    evt_id = f"evt_timeline_{uuid.uuid4().hex[:6]}"
    t0 = datetime(2024, 8, 15, 2, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 8, 15, 4, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 8, 15, 6, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 8, 15, 8, 0, 0, tzinfo=timezone.utc)
    t4 = datetime(2024, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

    # Create FloodEvent
    event = FloodEvent(
        id=evt_id,
        region_id="koshi_basin",
        name="August 2024 Koshi Historical Episode",
        start_at=t0,
        end_at=t4,
        mode=OperationalMode.HISTORICAL_DEMO,
        source_refs={"dhm": "DHM_BULLETIN_20240815"},
        description="Historical monsoon flood episode in Koshi basin",
    )
    db_session.add(event)
    db_session.commit()

    # Need location for prediction
    loc_id = f"loc_tl_{uuid.uuid4().hex[:6]}"
    loc = Location(id=loc_id, name="Koshi Flood Zone", admin_level=3, crs_source="EPSG:4326", metadata_json={})
    db_session.add(loc)
    db_session.commit()

    # 1. ForecastRun at t1
    fc_run = ForecastRun(
        id=f"fc_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        issued_at=t1,
        model_version="baseline-v1",
        mode=OperationalMode.HISTORICAL_DEMO,
        status="completed",
        limitations=["Upstream tributary gauge offline"],
    )
    db_session.add(fc_run)
    db_session.commit()

    pred1 = RiskPrediction(
        id=f"pred_1_{uuid.uuid4().hex[:6]}",
        forecast_run_id=fc_run.id,
        location_id=loc_id,
        valid_at=t1 + timedelta(hours=1),
        horizon_hours=1,
        risk_level=RiskLevel.LOW,
        calibrated_probability=0.2,
        data_quality=DataQuality.PARTIAL,
    )
    pred3 = RiskPrediction(
        id=f"pred_3_{uuid.uuid4().hex[:6]}",
        forecast_run_id=fc_run.id,
        location_id=loc_id,
        valid_at=t1 + timedelta(hours=3),
        horizon_hours=3,
        risk_level=RiskLevel.HIGH,
        calibrated_probability=0.75,
        data_quality=DataQuality.PARTIAL,
    )
    db_session.add_all([pred1, pred3])
    db_session.commit()

    # 2. FloodExtent observed at t2
    extent = FloodExtent(
        id=f"ext_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        observed_at=t2,
        method="MNDWI",
        area_km2=28.4,
        source_scene_ids=["S2A_20240815_T45RVP"],
        confidence=0.94,
    )
    db_session.add(extent)
    db_session.commit()

    # 3. Evaluation recorded at t3
    evaluation = Evaluation(
        id=f"eval_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        target_type="flood_extent",
        baseline_version="baseline-v1",
        metrics={"iou": 0.81, "f1": 0.89},
        reference_id="ground_truth_mask_v1",
        notes="Post-flood retrospective benchmark",
        created_at=t3,
    )
    db_session.add(evaluation)
    db_session.commit()

    resp = client.get(f"/api/v1/flood-events/{evt_id}/timeline")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["event_id"] == evt_id
    assert data["total_entries"] == 5  # event_start, forecast, extent, evaluation, event_end
    assert data["coverage"]["has_forecasts"] is True
    assert data["coverage"]["has_flood_extents"] is True
    assert data["coverage"]["has_evaluations"] is True

    # Verify chronological order
    timestamps = [e["timestamp"] for e in data["entries"]]
    sorted_ts = sorted(timestamps)
    assert timestamps == sorted_ts

    entry_types = [e["entry_type"] for e in data["entries"]]
    assert entry_types == ["event_start", "forecast_issued", "flood_observation", "evaluation_recorded", "event_end"]

    # Verify forecast entry details separate issue time from horizon valid times
    fc_entry = next(e for e in data["entries"] if e["entry_type"] == "forecast_issued")
    assert fc_entry["resource_id"] == fc_run.id
    horizons = fc_entry["details"]["prediction_horizons"]
    assert len(horizons) == 2
    assert horizons[0]["hours"] == 1
    assert horizons[1]["hours"] == 3
    assert fc_entry["data_quality"] == "PARTIAL"

    # Verify event_start and event_end do not fabricate FULL data quality
    start_entry = next(e for e in data["entries"] if e["entry_type"] == "event_start")
    assert start_entry["data_quality"] is None
    assert len(start_entry["limitations"]) > 0

    end_entry = next(e for e in data["entries"] if e["entry_type"] == "event_end")
    assert end_entry["title"].startswith("Historical Episode End:")
    assert "Recorded end timestamp" in end_entry["description"]
    assert "official conclusion" not in end_entry["description"].lower()
    assert end_entry["data_quality"] is None

    # Verify satellite flood extent has SATELLITE_DERIVED quality, not FULL
    extent_entry = next(e for e in data["entries"] if e["entry_type"] == "flood_observation")
    assert extent_entry["data_quality"] == "SATELLITE_DERIVED"
    assert any("Derived via MNDWI satellite processing" in lim for lim in extent_entry["limitations"])

    # Verify evaluation benchmark has BENCHMARK_DERIVED quality
    eval_entry = next(e for e in data["entries"] if e["entry_type"] == "evaluation_recorded")
    assert eval_entry["data_quality"] == "BENCHMARK_DERIVED"


def test_event_timeline_missing_event_returns_404(client: TestClient):
    """Querying timeline for an unknown event returns 404 EVENT_NOT_FOUND."""
    resp = client.get("/api/v1/flood-events/nonexistent-evt-timeline-999/timeline")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"


def test_event_timeline_empty_partial_records(client: TestClient, authority_token: str):
    """Event with only start/end boundaries returns timeline gracefully without fabricated entries."""
    evt_id = f"evt_tl_empty_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "siraha",
            "name": "Partial History Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    resp = client.get(f"/api/v1/flood-events/{evt_id}/timeline")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total_entries"] == 1  # Only event_start
    assert data["coverage"]["has_forecasts"] is False
    assert data["coverage"]["has_flood_extents"] is False
    assert data["coverage"]["has_evaluations"] is False
    assert any("No AI risk forecast runs" in n for n in data["notes"])
    assert any("No satellite flood extents" in n for n in data["notes"])


# ==============================================================================
# 5. IMPACT REPORT AND EXPORT TESTS
# ==============================================================================

def test_report_export_downloadable_json_and_csv(client: TestClient, authority_token: str):
    """Report export endpoint generates physical JSON and CSV attachments with Content-Disposition."""
    evt_id = f"evt_exp_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "saptari",
            "name": "Export Benchmark Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json={
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "NDWI",
            "area_km2": 45.2,
            "confidence": 0.91,
            "source_scene_ids": ["S2A_MSI_2024"],
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [86.70, 26.50],
                        [86.90, 26.50],
                        [86.90, 26.70],
                        [86.70, 26.70],
                        [86.70, 26.50],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 1. Download JSON export
    resp_json = client.get(f"/api/v1/flood-events/{evt_id}/report/export?format=json")
    assert resp_json.status_code == status.HTTP_200_OK
    assert "application/json" in resp_json.headers["Content-Type"]
    assert f'attachment; filename="floodlens_impact_report_{evt_id}.json"' in resp_json.headers["Content-Disposition"]
    json_data = resp_json.json()
    assert json_data["event_id"] == evt_id
    assert json_data["extent_area_km2"] == 45.2
    assert json_data["status"] == "summary_available"

    # 2. Download CSV export
    resp_csv = client.get(f"/api/v1/flood-events/{evt_id}/report/export?format=csv")
    assert resp_csv.status_code == status.HTTP_200_OK
    assert "text/csv" in resp_csv.headers["Content-Type"]
    assert f'attachment; filename="floodlens_impact_report_{evt_id}.csv"' in resp_csv.headers["Content-Disposition"]
    csv_text = resp_csv.text
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 2  # header + data row
    header = rows[0]
    data_row = rows[1]
    assert "event_id" in header
    assert "extent_area_km2" in header
    assert data_row[0] == evt_id
    assert float(data_row[header.index("extent_area_km2")]) == 45.2


def test_report_export_missing_event_returns_404(client: TestClient):
    """Exporting a report for an unknown event returns 404 EVENT_NOT_FOUND."""
    resp = client.get("/api/v1/flood-events/nonexistent-evt-export/report/export")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"]["code"] == "EVENT_NOT_FOUND"


# ==============================================================================
# 6. SECURITY AND PRIVACY REGRESSIONS
# ==============================================================================

def test_security_regressions_preserved_day3_guarantees(
    client: TestClient,
    authority_token: str,
    citizen_token: str,
):
    """Verify Day 3 security rules remain strictly enforced on Day 4."""
    # 1. Public endpoints must be accessible without token
    assert client.get("/api/v1/facilities/shelters").status_code == status.HTTP_200_OK
    assert client.get("/api/v1/facilities/hospitals").status_code == status.HTTP_200_OK
    assert client.get("/api/v1/models").status_code == status.HTTP_200_OK

    # 2. Protected endpoints reject unauthenticated or unauthorized citizen requests
    assert client.post("/api/v1/flood-events", json={}).status_code == status.HTTP_401_UNAUTHORIZED
    resp_cit = client.post(
        "/api/v1/flood-events",
        json={"name": "Forbidden Citizen Event"},
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert resp_cit.status_code == status.HTTP_403_FORBIDDEN

    # 3. Model training job initiation requires authority and returns 501 Not Implemented
    resp_train_cit = client.post(
        "/api/v1/models/training-jobs",
        json={},
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert resp_train_cit.status_code == status.HTTP_403_FORBIDDEN

    resp_train_auth = client.post(
        "/api/v1/models/training-jobs",
        json={"candidate_version": "era5-v1"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert resp_train_auth.status_code == status.HTTP_501_NOT_IMPLEMENTED
    assert resp_train_auth.json()["error"]["code"] == "TRAINING_NOT_IMPLEMENTED"


# ==============================================================================
# 7. DAY 4 CODE REVIEW REGRESSION TESTS
# ==============================================================================

def test_impact_report_flood_extent_without_geometry(client: TestClient, db_session: Session, authority_token: str):
    """When a flood extent exists without valid geometry, status is no_extent_geometry and report is incomplete_evidence."""
    evt_id = f"evt_nogeom_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "siraha",
            "name": "No Geometry Test Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Ingest extent record WITHOUT geometry
    ext = FloodExtent(
        id=f"ext_nogeom_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        observed_at=datetime.now(timezone.utc),
        method="SAR_CHANGE",
        area_km2=12.5,
        confidence=0.88,
        geometry=None,
    )
    db_session.add(ext)
    db_session.commit()

    # 1. Assets endpoint returns no_extent_geometry
    resp_assets = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert resp_assets.status_code == status.HTTP_200_OK
    assert resp_assets.json()["status"] == "no_extent_geometry"

    # 2. Settlements endpoint returns no_extent_geometry
    resp_settlements = client.get(f"/api/v1/flood-events/{evt_id}/settlements")
    assert resp_settlements.status_code == status.HTTP_200_OK
    assert resp_settlements.json()["status"] == "no_extent_geometry"

    # 3. Report endpoint returns incomplete_evidence
    resp_rep = client.get(f"/api/v1/flood-events/{evt_id}/report")
    assert resp_rep.status_code == status.HTTP_200_OK
    data_rep = resp_rep.json()
    assert data_rep["status"] == "incomplete_evidence"
    assert data_rep["settlements_data_status"] == "no_extent_geometry"
    assert data_rep["assets_data_status"] == "no_extent_geometry"

    # 4. JSON export matches incomplete_evidence
    resp_json = client.get(f"/api/v1/flood-events/{evt_id}/report/export?format=json")
    assert resp_json.status_code == status.HTTP_200_OK
    assert resp_json.json()["status"] == "incomplete_evidence"

    # 5. CSV export matches incomplete_evidence
    resp_csv = client.get(f"/api/v1/flood-events/{evt_id}/report/export?format=csv")
    assert resp_csv.status_code == status.HTTP_200_OK
    csv_rows = list(csv.reader(io.StringIO(resp_csv.text)))
    header = csv_rows[0]
    data_row = csv_rows[1]
    assert data_row[header.index("status")] == "incomplete_evidence"


def test_impact_report_distinguishes_missing_geometry_from_measured_zero_exposure(client: TestClient, db_session: Session, authority_token: str):
    """Distinguishes no_extent_geometry, no_assets_available, and completed with zero exposure."""
    from app.models.asset import Asset
    # Create event
    evt_id = f"evt_assets_test_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "rautahat",
            "name": "Asset Zero Exposure Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 1. Extent without geometry returns no_extent_geometry
    ext_nogeom = FloodExtent(
        id=f"ext_nogeom_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        observed_at=datetime(2024, 7, 10, 10, 0, tzinfo=timezone.utc),
        method="MNDWI",
        area_km2=5.0,
        confidence=0.8,
        geometry=None,
    )
    db_session.add(ext_nogeom)
    db_session.commit()

    resp_nogeom = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert resp_nogeom.status_code == status.HTTP_200_OK
    assert resp_nogeom.json()["status"] == "no_extent_geometry"

    # Add an extent with valid geometry observed later (85.20 to 85.30)
    ext_valid = FloodExtent(
        id=f"ext_valid_{uuid.uuid4().hex[:6]}",
        event_id=evt_id,
        observed_at=datetime(2024, 7, 10, 12, 0, tzinfo=timezone.utc),
        method="MNDWI",
        area_km2=8.0,
        confidence=0.9,
        geometry=to_wkt_element({
            "type": "Polygon",
            "coordinates": [[[85.20, 27.00], [85.30, 27.00], [85.30, 27.10], [85.20, 27.10], [85.20, 27.00]]],
        }),
    )
    db_session.add(ext_valid)
    db_session.commit()

    # 2. When no usable mapped assets exist in inventory -> returns no_assets_available
    db_session.query(Asset).delete()
    db_session.commit()

    resp_empty = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert resp_empty.status_code == status.HTTP_200_OK
    assert resp_empty.json()["status"] == "no_assets_available"

    # 3. Add an asset far outside (86.00, 27.00)
    far_asset = Asset(
        id=f"ast_far_{uuid.uuid4().hex[:6]}",
        asset_type="road",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[86.00, 27.00], [86.05, 27.00]]},
            expected_type="LINESTRING",
        ),
        metadata_json={"road_name": "Far Highway"},
    )
    db_session.add(far_asset)
    db_session.commit()

    resp_measured = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert resp_measured.status_code == status.HTTP_200_OK
    data_measured = resp_measured.json()
    # Mapped assets were evaluated, and zero intersected: status must be 'completed' with 0.0 values
    assert data_measured["status"] == "completed"
    assert data_measured["roads_exposed_km"] == 0.0
    assert len(data_measured["exposed_assets"]) == 0

    # Report status reflects summary_available with completed assets
    resp_rep = client.get(f"/api/v1/flood-events/{evt_id}/report")
    assert resp_rep.status_code == status.HTTP_200_OK
    assert resp_rep.json()["status"] == "summary_available"
    assert resp_rep.json()["assets_data_status"] == "completed"

    # 4. Add an intersecting asset inside the extent (85.25, 27.05)
    near_asset = Asset(
        id=f"ast_near_{uuid.uuid4().hex[:6]}",
        asset_type="road",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.22, 27.05], [85.28, 27.05]]},
            expected_type="LINESTRING",
        ),
        metadata_json={"road_name": "Submerged Highway"},
    )
    db_session.add(near_asset)
    db_session.commit()

    resp_intersecting = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert resp_intersecting.status_code == status.HTTP_200_OK
    data_intersecting = resp_intersecting.json()
    assert data_intersecting["status"] == "completed"
    assert data_intersecting["roads_exposed_km"] > 0.0
    assert len(data_intersecting["exposed_assets"]) == 1


def test_route_assess_temporal_event_scoping_excludes_unrelated_hazards(client: TestClient, db_session: Session):
    """Hazards outside the historical event window (event.start_at - 24h to event.end_at) are excluded."""
    # Historical event: August 15, 2024
    evt_id = f"evt_temp_{uuid.uuid4().hex[:6]}"
    t_start = datetime(2024, 8, 15, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2024, 8, 16, 0, 0, tzinfo=timezone.utc)
    event = FloodEvent(
        id=evt_id,
        region_id="morang",
        name="August 2024 Historical Morang Event",
        start_at=t_start,
        end_at=t_end,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add(event)

    # 1. Unrelated old hazard from July 2024 (1.5 months earlier) crossing the route
    rh_old = RoadHazard(
        id=f"rh_old_{uuid.uuid4().hex[:6]}",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.25, 26.65], [87.25, 26.75]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 7, 1, 10, 0, tzinfo=timezone.utc),
    )
    # 2. In-event hazard observed during the August 15 event crossing the route
    rh_event = RoadHazard(
        id=f"rh_in_event_{uuid.uuid4().hex[:6]}",
        hazard_type="bridge_closed",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.25, 26.65], [87.25, 26.75]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 8, 15, 12, 0, tzinfo=timezone.utc),
    )
    # 3. Future hazard observed in 2026
    rh_future = RoadHazard(
        id=f"rh_future_{uuid.uuid4().hex[:6]}",
        hazard_type="debris",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.25, 26.65], [87.25, 26.75]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([rh_old, rh_event, rh_future])
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[87.20, 26.70], [87.30, 26.70]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "event_id": evt_id},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    detected_ids = [h["hazard_id"] for h in data["hazards_detected"]]
    assert rh_event.id in detected_ids
    assert rh_old.id not in detected_ids  # Excluded due to temporal mismatch
    assert rh_future.id not in detected_ids  # Excluded due to temporal mismatch


def test_route_assess_distinguishes_direct_intersection_from_proximity_warning(client: TestClient, db_session: Session):
    """Route screening distinguishes direct intersections (0.0m) from proximity warnings with geodesic meter distance."""
    # Candidate route along latitude 26.7000: (85.80, 26.7000) -> (85.90, 26.7000)
    # 1. Hazard directly intersecting route at (85.85, 26.7000)
    rh_direct = RoadHazard(
        id=f"rh_dir_{uuid.uuid4().hex[:6]}",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.85, 26.6990], [85.85, 26.7010]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime.now(timezone.utc),
    )
    # 2. Hazard ~22 meters north of route (0.0002 deg lat ~ 22m), not directly intersecting
    rh_prox = RoadHazard(
        id=f"rh_prox_{uuid.uuid4().hex[:6]}",
        hazard_type="debris",
        geometry=to_wkt_element(
            {"type": "Point", "coordinates": [85.85, 26.7002]},
            expected_type="POINT",
        ),
        status="active",
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add_all([rh_direct, rh_prox])
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.80, 26.7000], [85.90, 26.7000]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "buffer_meters": 50.0},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["route_status"] == "hazards_detected"

    h_direct = next(h for h in data["hazards_detected"] if h["hazard_id"] == rh_direct.id)
    assert h_direct["match_type"] == "direct_intersection"
    assert h_direct["proximity_distance_meters"] == 0.0
    assert h_direct["intersection_details"] is not None

    h_prox = next(h for h in data["hazards_detected"] if h["hazard_id"] == rh_prox.id)
    assert h_prox["match_type"] == "proximity_warning"
    assert 10.0 < h_prox["proximity_distance_meters"] < 35.0
    assert "buffer corridor" in h_prox["notes"]


def test_route_assess_never_classifies_unverified_route_as_safe(client: TestClient, db_session: Session):
    """Absence of hazards returns 'conditional', never 'safe', with mandatory disclaimers."""
    rh_away = RoadHazard(
        id=f"rh_away_{uuid.uuid4().hex[:6]}",
        hazard_type="bridge_closed",
        geometry=to_wkt_element(
            {"type": "Point", "coordinates": [88.0, 27.5]},
            expected_type="POINT",
        ),
        status="active",
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(rh_away)
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.0, 26.0], [85.05, 26.0]],
    }
    resp = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "buffer_meters": 25.0},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["route_status"] == "conditional"
    assert data["assessment_status"] == "NO_KNOWN_INTERSECTIONS"
    assert "safe" not in data["route_status"].lower()
    assert any("NEVER infer that a candidate route is safe" in lim for lim in data["limitations"])
    assert any("NEVER classify an unverified route as safe" in lim for lim in data["limitations"])


def test_route_assess_clamps_cutoff_to_event_end(client: TestClient, db_session: Session):
    """Clamps effective cutoff to event.end_at and excludes post-event hazards even if requested cutoff is later."""
    # Historical event: August 10, 2024 to August 12, 2024 12:00 UTC
    evt_id = f"evt_clamp_{uuid.uuid4().hex[:6]}"
    t_start = datetime(2024, 8, 10, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2024, 8, 12, 12, 0, tzinfo=timezone.utc)
    event = FloodEvent(
        id=evt_id,
        region_id="rautahat",
        name="August 2024 Rautahat Bounded Event",
        start_at=t_start,
        end_at=t_end,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add(event)

    # 1. Hazard observed DURING the event (Aug 11 10:00)
    rh_during = RoadHazard(
        id=f"rh_during_{uuid.uuid4().hex[:6]}",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.30, 27.00], [85.30, 27.10]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 8, 11, 10, 0, tzinfo=timezone.utc),
    )
    # 2. Hazard observed AFTER the event ended (Aug 13 10:00 - 22h after t_end)
    rh_post = RoadHazard(
        id=f"rh_post_{uuid.uuid4().hex[:6]}",
        hazard_type="bridge_closed",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.30, 27.00], [85.30, 27.10]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 8, 13, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([rh_during, rh_post])
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[85.25, 27.05], [85.35, 27.05]],
    }

    # Request assessment with cutoff_time 3 days after event ended (Aug 15)
    resp = client.post(
        "/api/v1/routes/assess",
        json={
            "route": candidate_route,
            "event_id": evt_id,
            "cutoff_time": "2024-08-15T00:00:00Z",
        },
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Effective cutoff was clamped to event.end_at
    assert data["cutoff_time_applied"].startswith("2024-08-12T12:00:00")
    assert data["provenance"]["effective_cutoff_applied"].startswith("2024-08-12T12:00:00")
    assert data["provenance"]["raw_cutoff_requested"].startswith("2024-08-15T00:00:00")

    detected_ids = [h["hazard_id"] for h in data["hazards_detected"]]
    assert rh_during.id in detected_ids
    # Post-event hazard MUST NOT be included because cutoff was clamped to event.end_at
    assert rh_post.id not in detected_ids

    # Documented limitation must be present
    assert any("RoadHazard records lack a relational event_id foreign key" in lim for lim in data["limitations"])


def test_route_assess_overlapping_events_and_temporal_correlation_limitation(client: TestClient, db_session: Session):
    """Verifies hazard matching across overlapping event temporal windows and documents non-relational linkage."""
    # Event A: Aug 1 to Aug 8
    evt_a_id = f"evt_a_{uuid.uuid4().hex[:6]}"
    evt_a = FloodEvent(
        id=evt_a_id,
        region_id="sunsari",
        name="Event A (Aug 1-8)",
        start_at=datetime(2024, 8, 1, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2024, 8, 8, 0, 0, tzinfo=timezone.utc),
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    # Event B: Aug 5 to Aug 12 (overlaps Event A between Aug 5 and Aug 8)
    evt_b_id = f"evt_b_{uuid.uuid4().hex[:6]}"
    evt_b = FloodEvent(
        id=evt_b_id,
        region_id="sunsari",
        name="Event B (Aug 5-12)",
        start_at=datetime(2024, 8, 5, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2024, 8, 12, 0, 0, tzinfo=timezone.utc),
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add_all([evt_a, evt_b])

    # Hazard 1: In the overlap period (Aug 6)
    rh_overlap = RoadHazard(
        id=f"rh_ovl_{uuid.uuid4().hex[:6]}",
        hazard_type="debris",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.10, 26.60], [87.10, 26.70]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 8, 6, 12, 0, tzinfo=timezone.utc),
    )
    # Hazard 2: In Event B only (Aug 10 - after Event A ended)
    rh_b_only = RoadHazard(
        id=f"rh_b_only_{uuid.uuid4().hex[:6]}",
        hazard_type="submerged",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[87.10, 26.60], [87.10, 26.70]]},
            expected_type="LINESTRING",
        ),
        status="active",
        observed_at=datetime(2024, 8, 10, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([rh_overlap, rh_b_only])
    db_session.commit()

    candidate_route = {
        "type": "LineString",
        "coordinates": [[87.05, 26.65], [87.15, 26.65]],
    }

    # 1. Screen against Event A: only rh_overlap is included (rh_b_only is after Event A ended)
    resp_a = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "event_id": evt_a_id},
    )
    assert resp_a.status_code == status.HTTP_200_OK
    data_a = resp_a.json()
    ids_a = [h["hazard_id"] for h in data_a["hazards_detected"]]
    assert rh_overlap.id in ids_a
    assert rh_b_only.id not in ids_a

    # 2. Screen against Event B: BOTH hazards are included (both within Event B window)
    resp_b = client.post(
        "/api/v1/routes/assess",
        json={"route": candidate_route, "event_id": evt_b_id},
    )
    assert resp_b.status_code == status.HTTP_200_OK
    data_b = resp_b.json()
    ids_b = [h["hazard_id"] for h in data_b["hazards_detected"]]
    assert rh_overlap.id in ids_b
    assert rh_b_only.id in ids_b

    # Both responses document the non-relational linkage limitation
    assert any("RoadHazard records lack a relational event_id foreign key" in lim for lim in data_a["limitations"])
    assert any("RoadHazard records lack a relational event_id foreign key" in lim for lim in data_b["limitations"])

