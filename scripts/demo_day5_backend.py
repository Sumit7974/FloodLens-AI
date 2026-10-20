"""FloodLens AI — Member 1, Day 5 Final Backend Release Candidate Demonstration.

Historical Nepal Terai Flood Intelligence Demonstration (July 2024 Episode).

DEMONSTRATES (13 Required Capabilities):
 1. Historical flood event registration (/flood-events)
 2. Settlement and geographic data ingestion (/locations)
 3. Multi-horizon historical prediction ingestion (+1h/+3h/+6h) (/predictions/ingest)
 4. Satellite-derived observed flood extent (/flood-events/{id}/extent)
 5. Published risk map retrieval (/predictions/map & /predictions/latest)
 6. Affected settlements assessment (/flood-events/{id}/settlements)
 7. Exposed assets assessment (/flood-events/{id}/assets)
 8. Route hazard screening (/routes/assess)
 9. Authority-controlled simulated alert lifecycle (draft -> approve -> simulated dispatch)
10. Citizen assistance request simulation & authority triage queue (/assistance)
11. Impact assessment report & JSON/CSV export (/flood-events/{id}/report & /export)
12. Historical event timeline (/flood-events/{id}/timeline)
13. Model evaluation retrieval (/analytics/events/{id})

SAFETY & METHODOLOGY BOUNDARIES:
- All data is deterministically seeded and explicitly labelled as synthetic demonstration fixtures.
- FloodLens provides intelligence and decision-support to authorities; it does NOT deploy rescue units.
- Operational dispatch is strictly prevented by software safeguards; all alerts are simulated.
- Forecast issue time is kept strictly distinct from valid_at verification timestamps.
- Zero external network dependencies; self-contained in-memory execution.
"""
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Ensure backend directory is in sys.path
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
from app.models.asset import Asset, Facility, RoadHazard
from app.models.enums import OperationalMode, UserRole
from app.models.evaluation import Evaluation
from app.models.location import Location
from app.models.user import User
from app.services.demo_participants import demo_participant_registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Day5ReleaseDemo")


def run_day5_demonstration() -> bool:
    """Execute end-to-end Day 5 release-candidate validation demonstration."""
    logger.info("=" * 80)
    logger.info("FLOODLENS AI — MEMBER 1, DAY 5 FINAL BACKEND DEMONSTRATION")
    logger.info("Historical Nepal Terai Flood Intelligence Release Candidate")
    logger.info("=" * 80)

    # --------------------------------------------------------------------------
    # STEP 0: TEST HARNESS & IN-MEMORY DATABASE SETUP
    # --------------------------------------------------------------------------
    logger.info("\n[STEP 0] Initializing In-Memory Test Database and FastAPI TestClient...")
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

    # Seed User Accounts
    authority_user = User(
        email="commander.terai@floodlens.org",
        hashed_password=hash_password("authoritypass123"),
        full_name="Disaster Management Authority Lead",
        role=UserRole.AUTHORITY,
        is_active=True,
    )
    citizen_user = User(
        email="citizen.janakpur@example.com",
        hashed_password=hash_password("citizenpass123"),
        full_name="Janakpur Resident",
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

    event_id = "evt_2024_terai_monsoon"
    region_id = "terai_dhanusha"

    # --------------------------------------------------------------------------
    # 1. HISTORICAL FLOOD EVENT REGISTRATION
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 1] Registering Historical Flood Event...")
    event_payload = {
        "id": event_id,
        "region_id": region_id,
        "name": "Historical Nepal Terai Monsoon Inundation (July 2024 Episode)",
        "start_at": "2024-07-08T00:00:00Z",
        "end_at": "2024-07-12T23:59:59Z",
        "mode": "historical_demo",
        "source_refs": {
            "hydrology_source": "Nepal Department of Hydrology and Meteorology (DHM) Telemetry",
            "satellite_sensor": "Copernicus Sentinel-1 SAR C-Band",
            "curation": "FloodLens Historical Benchmark Dataset v1.0",
        },
        "description": "Historical monsoon surge causing river overtopping across Kamala basin and Dhanusha lowlands.",
    }
    res = client.post("/api/v1/flood-events", headers=auth_headers, json=event_payload)
    assert res.status_code == 201, f"Expected 201 Created, got {res.status_code}: {res.text}"
    event_data = res.json()
    logger.info("  -> Event Created: id=%s, name='%s'", event_data["id"], event_data["name"])
    assert event_data["id"] == event_id
    assert event_data["mode"] == "historical_demo"

    # --------------------------------------------------------------------------
    # 2. SETTLEMENT AND GEOGRAPHIC DATA INGESTION
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 2] Ingesting Settlement GIS Data...")
    settlement_janakpur: dict[str, Any] = {
        "id": "settlement_janakpurdham",
        "name": "Janakpurdham Sub-Metropolitan",
        "admin_level": 3,
        "parent_id": region_id,
        "geometry": {
            "type": "Point",
            "coordinates": [85.9244, 26.7288],
        },
        "metadata_json": {
            "region_id": region_id,
            "population": 195438,
            "vulnerability_score": 0.82,
        },
    }
    settlement_sabaila: dict[str, Any] = {
        "id": "settlement_sabaila",
        "name": "Sabaila Municipality",
        "admin_level": 3,
        "parent_id": region_id,
        "geometry": {
            "type": "Point",
            "coordinates": [85.9620, 26.7980],
        },
        "metadata_json": {
            "region_id": region_id,
            "population": 35870,
            "vulnerability_score": 0.65,
        },
    }
    for s in [settlement_janakpur, settlement_sabaila]:
        res_loc = client.post("/api/v1/locations", headers=auth_headers, json=s)
        assert res_loc.status_code == 201, f"Failed to ingest location {s['id']}: {res_loc.text}"
        meta: dict[str, Any] = s["metadata_json"]
        logger.info("  -> Ingested settlement: %s (pop=%d, vuln=%.2f)", s["name"], int(meta["population"]), float(meta["vulnerability_score"]))

    # Seed Critical Infrastructure Assets (Roads, Structures, Hospitals) for spatial exposure assessment
    logger.info("  -> Seeding benchmark infrastructure assets into database...")
    from app.core.spatial import to_wkt_element

    asset_road = Asset(
        id="asset_road_kamala_link",
        asset_type="road",
        geometry=to_wkt_element(
            {"type": "LineString", "coordinates": [[85.9200, 26.7200], [85.9300, 26.7350]]},
            expected_type="LINESTRING",
        ),
        metadata_json={"road_name": "Kamala River Access Road (Section 4)", "length_km": 4.8},
    )
    asset_substation = Asset(
        id="asset_elec_substation",
        asset_type="critical_infrastructure",
        geometry=to_wkt_element(
            {"type": "Point", "coordinates": [85.9260, 26.7290]},
            expected_type="POINT",
        ),
        metadata_json={"name": "Janakpur Power Substation #2", "backup_power": True},
    )
    shelter_facility = Facility(
        id="facility_shelter_janakpur_school",
        type="shelter",
        name="Janakpur Community Higher Secondary School Shelter",
        verification_status="verified",
        capacity=600,
        location=to_wkt_element(
            {"type": "Point", "coordinates": [85.9180, 26.7250]},
            expected_type="POINT",
        ),
        details={"water_available": True},
    )
    hazard_road = RoadHazard(
        id="rh_kamala_bridge_overtop",
        road_id="Hulaki-Kamala-01",
        hazard_type="submerged",
        status="active",
        geometry=to_wkt_element(
            {"type": "Point", "coordinates": [85.9280, 26.7320]},
            expected_type="POINT",
        ),
        observed_at=datetime(2024, 7, 8, 9, 30, tzinfo=timezone.utc),
        source="DHM Field Telemetry",
        confidence=0.95,
    )
    db.add_all([asset_road, asset_substation, shelter_facility, hazard_road])
    db.commit()

    # --------------------------------------------------------------------------
    # 3. +1h/+3h/+6h MULTI-HORIZON HISTORICAL PREDICTION INGESTION
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 3] Ingesting +1h/+3h/+6h Multi-Horizon Forecast Run...")
    issue_time = datetime(2024, 7, 8, 8, 0, tzinfo=timezone.utc)
    forecast_payload = {
        "forecast_id": "fc_20240708_0800_kamala",
        "event_id": event_id,
        "location_id": "settlement_janakpurdham",
        "issued_at": issue_time.isoformat(),
        "input_data_cutoff_at": (issue_time - timedelta(minutes=30)).isoformat(),
        "mode": "historical_demo",
        "model_version": "baseline-v1",
        "data_quality": "PARTIAL",
        "horizons": [
            {
                "hours": 1,
                "risk_level": "moderate",
                "calibrated_probability": 0.58,
                "valid_at": (issue_time + timedelta(hours=1)).isoformat(),
            },
            {
                "hours": 3,
                "risk_level": "high",
                "calibrated_probability": 0.82,
                "valid_at": (issue_time + timedelta(hours=3)).isoformat(),
            },
            {
                "hours": 6,
                "risk_level": "critical",
                "calibrated_probability": 0.94,
                "valid_at": (issue_time + timedelta(hours=6)).isoformat(),
            },
        ],
        "limitations": [
            "PIPELINE TEST ONLY: Model calibrated on synthetic historical proxy data.",
            "Issued time strictly preserved: 2024-07-08T08:00:00Z.",
        ],
    }
    res_fc = client.post("/api/v1/predictions/ingest", headers=auth_headers, json=forecast_payload)
    assert res_fc.status_code == 201, f"Forecast ingestion failed: {res_fc.text}"
    fc_data = res_fc.json()
    logger.info("  -> Ingested Forecast: run_id=%s, horizons count=%d", fc_data["forecast_id"], len(fc_data["horizons"]))
    for hz in fc_data["horizons"]:
        logger.info("     * +%dh horizon -> risk=%s (prob=%.2f)", hz["hours"], hz["risk_level"], hz["calibrated_probability"] or 0.0)

    # --------------------------------------------------------------------------
    # 4. SATELLITE-DERIVED OBSERVED FLOOD EXTENT INGESTION
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 4] Ingesting Satellite-Derived Observed Flood Extent...")
    # Representative bounding polygon over Janakpur lowland coordinates
    synthetic_polygon_wkt = (
        "POLYGON(("
        "85.9100 26.7150, "
        "85.9450 26.7150, "
        "85.9450 26.7450, "
        "85.9100 26.7450, "
        "85.9100 26.7150"
        "))"
    )
    extent_payload = {
        "id": "ext_s1_20240708_1015",
        "observed_at": "2024-07-08T10:15:00Z",
        "method": "SAR_CHANGE",
        "area_km2": 42.6,
        "source_scene_ids": ["S1A_IW_GRDH_1SDV_20240708T1015_NEPAL_TERAI"],
        "confidence": 0.91,
        "geometry": synthetic_polygon_wkt,
    }
    res_ext = client.post(f"/api/v1/flood-events/{event_id}/extent", headers=auth_headers, json=extent_payload)
    assert res_ext.status_code == 201, f"Extent ingestion failed: {res_ext.text}"
    ext_data = res_ext.json()
    logger.info("  -> Flood Extent Ingested: id=%s, area=%.1f km2, method=%s", ext_data["id"], ext_data["area_km2"], ext_data["method"])

    # --------------------------------------------------------------------------
    # 5. RISK MAP RETRIEVAL
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 5] Retrieving Latest Multi-Horizon Risk Map...")
    res_map = client.get("/api/v1/predictions/map")
    assert res_map.status_code == 200, f"Map retrieval failed: {res_map.text}"
    map_data = res_map.json()
    logger.info("  -> Map Layer: id=%s, active horizons=%s, total features=%d", map_data["layer_id"], map_data["active_horizons"], len(map_data["features"]))

    res_latest = client.get("/api/v1/predictions/latest?location_id=settlement_janakpurdham")
    assert res_latest.status_code == 200, f"Latest forecast failed: {res_latest.text}"
    latest_fc = res_latest.json()
    assert latest_fc["location_id"] == "settlement_janakpurdham"
    logger.info("  -> Latest Settlement Forecast verified (model=%s, mode=%s)", latest_fc["model_version"], latest_fc["mode"])

    # --------------------------------------------------------------------------
    # 6. AFFECTED SETTLEMENTS ASSESSMENT
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 6] Computing Affected Settlements from Satellite Extent...")
    res_settlements = client.get(f"/api/v1/flood-events/{event_id}/settlements")
    assert res_settlements.status_code == 200, f"Settlements query failed: {res_settlements.text}"
    settlements_res = res_settlements.json()
    logger.info("  -> Settlements Assessment Status: '%s' (evaluated: %d, affected: %d)",
                settlements_res["status"], settlements_res["total_settlements_evaluated"], settlements_res["total_settlements_affected"])
    for aff in settlements_res["affected_settlements"]:
        logger.info("     * Settlement: %s (id=%s, exposure=%s)", aff["name"], aff["settlement_id"], aff["exposure_status"])

    # --------------------------------------------------------------------------
    # 7. EXPOSED ASSETS ASSESSMENT
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 7] Assessing Exposed Infrastructure Assets...")
    res_assets = client.get(f"/api/v1/flood-events/{event_id}/assets")
    assert res_assets.status_code == 200, f"Assets query failed: {res_assets.text}"
    assets_data = res_assets.json()
    logger.info("  -> Asset Assessment Status: '%s' (roads: %.1f km, structures: %d, cropland: %.1f ha)",
                assets_data["status"], assets_data["roads_exposed_km"], assets_data["structures_exposed_count"], assets_data["cropland_exposed_ha"])

    # --------------------------------------------------------------------------
    # 8. ROUTE HAZARD SCREENING
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 8] Screening Candidate Evacuation Route against Active Hazards...")
    candidate_route_payload = {
        "route": {
            "type": "LineString",
            "coordinates": [
                [85.9180, 26.7250],  # School Shelter
                [85.9280, 26.7320],  # Near Kamala causeway hazard
                [85.9400, 26.7450],  # Higher ground
            ],
        },
        "event_id": event_id,
        "buffer_meters": 100.0,
    }
    res_route = client.post("/api/v1/routes/assess", json=candidate_route_payload)
    assert res_route.status_code == 200, f"Route assessment failed: {res_route.text}"
    route_data = res_route.json()
    logger.info("  -> Route Assessment: status=%s, assessment=%s, hazards detected=%d",
                route_data["route_status"], route_data["assessment_status"], len(route_data["hazards_detected"]))
    for hz in route_data["hazards_detected"]:
        logger.info("     * Hazard Intersected: id=%s (%s, type=%s, match=%s)",
                    hz["hazard_id"], hz["source_layer"], hz["hazard_type"], hz["match_type"])

    # --------------------------------------------------------------------------
    # 9. AUTHORITY-CONTROLLED SIMULATED ALERT
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 9] Authority Simulated Alert Workflow (Draft -> Approve -> Simulated Dispatch)...")
    # A. Draft Alert
    alert_draft_payload = {
        "area_id": "terai_dhanusha",
        "title": "[DEMO] Flood Warning: Kamala River High Stage Simulation",
        "message": "Water levels at Kamala causeway exceed critical stage. Inhabitants of low-lying wards seek designated high ground shelters.",
        "mode": "historical_demo",
    }
    res_alert_draft = client.post("/api/v1/alerts", headers=auth_headers, json=alert_draft_payload)
    assert res_alert_draft.status_code == 201, f"Alert draft failed: {res_alert_draft.text}"
    draft_alert = res_alert_draft.json()
    alert_id = draft_alert["id"]
    logger.info("  -> 1. Draft Alert Created: id=%s, status=%s", alert_id, draft_alert["status"])

    # B. Authority Approval
    res_approve = client.post(
        f"/api/v1/alerts/{alert_id}/approve",
        headers=auth_headers,
        json={"comments": "Simulated flood intelligence validated against historical July 2024 episode."},
    )
    assert res_approve.status_code == 200, f"Alert approval failed: {res_approve.text}"
    approved_alert = res_approve.json()
    logger.info("  -> 2. Alert Approved: status=%s, approved_by=%s", approved_alert["status"], approved_alert["approved_by"])

    # C. Test/Simulated Dispatch
    res_dispatch = client.post(
        f"/api/v1/alerts/{alert_id}/dispatch",
        headers=auth_headers,
        json={"simulated": True},
    )
    assert res_dispatch.status_code == 200, f"Alert dispatch failed: {res_dispatch.text}"
    dispatched_alert = res_dispatch.json()
    logger.info("  -> 3. Alert Dispatched (Simulated): status=%s, issued_at=%s, title='%s'",
                dispatched_alert["status"], dispatched_alert["issued_at"], dispatched_alert["title"])

    # --------------------------------------------------------------------------
    # 10. CITIZEN ASSISTANCE REQUEST SIMULATION & AUTHORITY QUEUE REVIEW
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 10] Citizen Assistance Request Simulation & Authority Review...")
    help_payload = {
        "latitude": 26.7310,
        "longitude": 85.9270,
        "category": "evacuation",
        "details": "Ground floor flooded to 1.2 meters. Elderly resident and family requiring shelter guidance.",
        "people_count": 5,
    }
    res_help = client.post("/api/v1/assistance", headers=citizen_headers, json=help_payload)
    assert res_help.status_code == 201, f"Assistance submission failed: {res_help.text}"
    req_data = res_help.json()
    req_id = req_data["id"]
    logger.info("  -> Citizen Request Submitted: id=%s, status=%s, category=%s", req_id, req_data["status"], req_data["category"])

    # Authority views queue and updates status
    res_queue = client.get("/api/v1/assistance", headers=auth_headers)
    assert res_queue.status_code == 200, f"Queue lookup failed: {res_queue.text}"
    queue_items = res_queue.json()
    logger.info("  -> Authority Queue Retrieved: %d active request(s)", len(queue_items))

    res_triage = client.patch(
        f"/api/v1/assistance/{req_id}",
        headers=auth_headers,
        json={
            "status": "in_progress",
            "assigned_to": "Janakpur Municipal Disaster Relief Cell",
            "status_notes": "Directed family toward Janakpur Higher Secondary School Shelter.",
        },
    )
    assert res_triage.status_code == 200, f"Assistance triage failed: {res_triage.text}"
    triaged_data = res_triage.json()
    logger.info("  -> Request Triaged: status=%s, assigned_to='%s'", triaged_data["status"], triaged_data["assigned_to"])

    # --------------------------------------------------------------------------
    # 11. IMPACT REPORT AND JSON/CSV EXPORT
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 11] Generating Impact Assessment Report and Exports...")
    res_report = client.get(f"/api/v1/flood-events/{event_id}/report")
    assert res_report.status_code == 200, f"Report query failed: {res_report.text}"
    report_data = res_report.json()
    logger.info("  -> Synthesized Report: event='%s', status=%s, settlements_affected=%d",
                report_data["event_name"], report_data["status"], report_data["total_settlements_affected"])

    # JSON export
    res_export_json = client.get(f"/api/v1/flood-events/{event_id}/report/export?format=json")
    assert res_export_json.status_code == 200, f"JSON export failed: {res_export_json.text}"
    exported_json = res_export_json.json()
    logger.info("  -> JSON Export Verified: keys=%s", list(exported_json.keys()))

    # CSV export
    res_export_csv = client.get(f"/api/v1/flood-events/{event_id}/report/export?format=csv")
    assert res_export_csv.status_code == 200, f"CSV export failed: {res_export_csv.text}"
    assert "event_id" in res_export_csv.text
    logger.info("  -> CSV Export Verified: %d bytes returned", len(res_export_csv.text))

    # --------------------------------------------------------------------------
    # 12. HISTORICAL EVENT TIMELINE
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 12] Retrieving Chronological Event Timeline...")
    res_timeline = client.get(f"/api/v1/flood-events/{event_id}/timeline")
    assert res_timeline.status_code == 200, f"Timeline query failed: {res_timeline.text}"
    timeline_data = res_timeline.json()
    logger.info("  -> Timeline Entries: %d chronological events recorded", timeline_data["total_entries"])
    for entry in timeline_data["entries"]:
        logger.info("     [%s] %s: %s", entry["timestamp"], entry["entry_type"], entry["title"])

    # --------------------------------------------------------------------------
    # 13. MODEL EVALUATION RETRIEVAL
    # --------------------------------------------------------------------------
    logger.info("\n[CAPABILITY 13] Retrieving Model Evaluation Benchmark Metrics...")
    # Seed an evaluation benchmark comparing baseline-v1 against Sentinel-1 SAR reference
    eval_benchmark = Evaluation(
        id="eval_20240708_sar_benchmark",
        event_id=event_id,
        target_type="flood_extent_spatial",
        baseline_version="baseline-v1",
        candidate_version="era5-v1",
        reference_id="ext_s1_20240708_1015",
        metrics={
            "iou_jaccard": 0.742,
            "f1_score": 0.852,
            "precision": 0.884,
            "recall": 0.822,
            "spatial_resolution_meters": 30.0,
        },
        notes="Retrospective spatial benchmark evaluated against Sentinel-1 SAR change detection reference mask.",
    )
    db.add(eval_benchmark)
    db.commit()

    res_analytics = client.get(f"/api/v1/analytics/events/{event_id}")
    assert res_analytics.status_code == 200, f"Analytics query failed: {res_analytics.text}"
    analytics_data = res_analytics.json()
    logger.info("  -> Analytics Retrieved: %d evaluation(s) recorded, status=%s",
                analytics_data["evaluations_count"], analytics_data["status"])
    for res_item in analytics_data["results"]:
        logger.info("     * Model: %s (metrics: %s)", res_item["baseline_version"], res_item["metrics"])

    logger.info("\n" + "=" * 80)
    logger.info("ALL 13 DAY 5 BACKEND CAPABILITIES VERIFIED SUCCESSFULLY!")
    logger.info("=" * 80)
    return True


if __name__ == "__main__":
    success = run_day5_demonstration()
    sys.exit(0 if success else 1)
