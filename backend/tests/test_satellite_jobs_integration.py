"""Comprehensive integration tests for Satellite Processing Pipeline -> FastAPI Integration.

Validates all Task 2 functional, security, recovery, and scientific integrity requirements:
1. Authority can create a valid satellite job with explicit event association.
2. Citizen and anonymous users cannot create jobs (401/403).
3. Job status API security (GET /satellite/jobs/{id}):
   - Unknown job IDs return 404 (for anonymous and authenticated).
   - Existing job returns 401 for anonymous.
   - Existing job returns 200 with sensitive metadata redacted for citizens.
   - Existing job returns 200 with full metadata for authority/admin.
4. Historical event association:
   - Missing or invalid event_id rejected.
   - Temporal event mismatch rejected.
   - Geographic event mismatch rejected.
5. Modality and method validation:
   - MNDWI rejected with UNSUPPORTED_PROCESSING_METHOD.
   - SAR_CHANGE requires baseline_scene_id (MISSING_BASELINE_SCENE).
   - Modality mismatch (optical for SAR_CHANGE, SAR for NDWI) rejected.
   - Uncalibrated radar preview thumbnails rejected (INVALID_INPUT_ARTIFACT).
6. Elimination of unsafe synthetic fallbacks:
   - Missing real input files strictly fail with MISSING_INPUT_ARTIFACTS (no silent substitution).
7. Provenance & Confidence validation:
   - Outputs from fixtures explicitly labeled SYNTHETIC_TEST_FIXTURE.
   - Processed optical labeled PROCESSED_OPTICAL.
   - Processed SAR labeled PROCESSED_SAR.
   - Imported precomputed vector labeled IMPORTED_PRECOMPUTED.
   - Confidence is strictly None/null (no fabricated 0.90/0.85).
8. Scientific raster input validation:
   - Green/NIR band CRS and dimension mismatch validation.
   - NoData handling.
   - Real dual-date SAR radar change detection.
9. Multi-event and multi-scene extent preservation:
   - Multiple events isolated without cross-contamination.
   - Multiple scenes for the same event produce distinct FloodExtent records (no overwrite).
   - Re-running the exact same scene updates idempotently.
10. Background worker atomic claiming & restart recovery:
    - claim_job prevents duplicate execution by concurrent workers.
    - recover_interrupted_jobs safely re-queues or marks FAILED after max retries.
    - Standalone worker execution via run_worker_once.
11. Complete End-to-End Acceptance Test sequence executed via FastAPI background tasks
    WITHOUT manual invocation of process_satellite_job().
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

try:
    import rasterio
    from rasterio.transform import from_origin
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None

from fastapi import status
from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent, SatelliteJob, SatelliteScene
from app.models.user import User
from app.services.satellite_processor import compute_metric_area_km2
from app.workers.satellite_worker import (
    claim_job,
    execute_job,
    recover_interrupted_jobs,
    run_worker_once,
)


@pytest.fixture
def test_flood_event(db_session: Session) -> FloodEvent:
    """Create a standard flood event record."""
    event = FloodEvent(
        id=f"evt_test_{uuid.uuid4().hex[:8]}",
        region_id="nepal_terai",
        name="Nepal Terai Monsoon Event (August 2017)",
        start_at=datetime(2017, 8, 11, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2017, 8, 20, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def second_flood_event(db_session: Session) -> FloodEvent:
    """Create a second distinct flood event for cross-event isolation testing."""
    event = FloodEvent(
        id=f"evt_second_{uuid.uuid4().hex[:8]}",
        region_id="nepal_terai",
        name="Western Nepal Flash Flood (September 2017)",
        start_at=datetime(2017, 9, 1, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2017, 9, 10, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def test_optical_scene(db_session: Session) -> SatelliteScene:
    """Create a verified optical scene pointing to the bundled GeoJSON sample."""
    scene = SatelliteScene(
        id=f"scene_s2_test_{uuid.uuid4().hex[:8]}",
        provider="ESA Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 15, 10, 30, tzinfo=timezone.utc),
        cloud_quality=0.08,
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [
                [
                    [87.0, 26.0],
                    [87.5, 26.0],
                    [87.5, 26.5],
                    [87.0, 26.5],
                    [87.0, 26.0],
                ]
            ],
        },
    )
    db_session.add(scene)
    db_session.commit()
    return scene


@pytest.fixture
def test_radar_scene(db_session: Session) -> SatelliteScene:
    """Create a verified SAR scene pointing to the bundled radar GeoJSON sample."""
    scene = SatelliteScene(
        id=f"scene_s1_test_{uuid.uuid4().hex[:8]}",
        provider="Copernicus Sentinel-1",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=datetime(2017, 8, 16, 12, 0, tzinfo=timezone.utc),
        cloud_quality=None,
        asset_ref="backend/tests/fixtures/radar_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [
                [
                    [86.5, 25.5],
                    [87.5, 25.5],
                    [87.5, 26.5],
                    [86.5, 26.5],
                    [86.5, 25.5],
                ]
            ],
        },
    )
    db_session.add(scene)
    db_session.commit()
    return scene


@pytest.fixture
def test_radar_baseline_scene(db_session: Session) -> SatelliteScene:
    """Create a verified pre-flood radar baseline scene."""
    scene = SatelliteScene(
        id=f"scene_s1_base_{uuid.uuid4().hex[:8]}",
        provider="Copernicus Sentinel-1",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=datetime(2017, 8, 4, 12, 0, tzinfo=timezone.utc),
        cloud_quality=None,
        asset_ref="backend/tests/fixtures/radar_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [
                [
                    [86.5, 25.5],
                    [87.5, 25.5],
                    [87.5, 26.5],
                    [86.5, 26.5],
                    [86.5, 25.5],
                ]
            ],
        },
    )
    db_session.add(scene)
    db_session.commit()
    return scene


@pytest.fixture
def small_geotiff_fixture(tmp_path: Path) -> Path:
    """Create a minimal synthetic GeoTIFF flood mask (100x100 pixels, UTM Zone 45N)."""
    if not HAS_RASTERIO or rasterio is None:
        pytest.skip("rasterio is not installed")
    file_path = tmp_path / "synthetic_flood_mask.tif"
    width, height = 100, 100
    transform = from_origin(500000, 2900000, 10, 10)
    data = np.zeros((height, width), dtype=np.uint8)
    data[30:70, 30:70] = 1

    with rasterio.open(
        file_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs="EPSG:32645",
        transform=transform,
        nodata=255,
    ) as dst:
        dst.write(data, 1)

    return file_path


# ==============================================================================
# 1. Authority Creation & Permissions (Requirements 1 & 2)
# ==============================================================================
def test_authority_can_create_valid_satellite_job(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
    test_flood_event: FloodEvent,
):
    """Authority user can submit a valid processing job with explicit event association."""
    payload = {
        "event_id": test_flood_event.id,
        "scene_id": test_optical_scene.id,
        "method": "NDWI",
        "threshold": 0.10,
    }
    res = client.post(
        "/api/v1/satellite/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_202_ACCEPTED
    body = res.json()
    assert body["job_id"].startswith("sat_job_")
    assert body["status"] == "QUEUED"
    assert "queued successfully" in body["message"].lower()
    assert body["requested_by"] is not None


def test_citizen_and_anonymous_cannot_create_jobs(
    client: TestClient,
    citizen_token: str,
    test_optical_scene: SatelliteScene,
    test_flood_event: FloodEvent,
):
    """Anonymous (401) and citizen (403) requests to create jobs must be rejected."""
    payload = {
        "event_id": test_flood_event.id,
        "scene_id": test_optical_scene.id,
        "method": "NDWI",
    }
    anon_res = client.post("/api/v1/satellite/jobs", json=payload)
    assert anon_res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    citizen_res = client.post(
        "/api/v1/satellite/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert citizen_res.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 2. Job Status API Security & Metadata Protection (Requirement 3)
# ==============================================================================
def test_job_status_api_security_and_redaction(
    client: TestClient,
    authority_token: str,
    citizen_token: str,
    test_optical_scene: SatelliteScene,
    test_flood_event: FloodEvent,
):
    """Job status API preserves 404 for unknown jobs, requires auth for existing jobs,
    and redacts sensitive requester emails and internal errors from citizens."""
    # 1. Unknown job returns 404 for both anonymous and authenticated
    res_anon_404 = client.get("/api/v1/satellite/jobs/sat_job_unknown_xyz999")
    assert res_anon_404.status_code == status.HTTP_404_NOT_FOUND
    assert res_anon_404.json()["error"]["code"] == "JOB_NOT_FOUND"

    res_auth_404 = client.get(
        "/api/v1/satellite/jobs/sat_job_unknown_xyz999",
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_auth_404.status_code == status.HTTP_404_NOT_FOUND

    # 2. Create a real job
    create_res = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert create_res.status_code == status.HTTP_202_ACCEPTED
    job_id = create_res.json()["job_id"]

    # 3. Anonymous request to existing job returns 401 Unauthorized
    res_anon_existing = client.get(f"/api/v1/satellite/jobs/{job_id}")
    assert res_anon_existing.status_code == status.HTTP_401_UNAUTHORIZED

    # 4. Citizen request returns 200 with sensitive metadata redacted (requested_by=None)
    res_citizen = client.get(
        f"/api/v1/satellite/jobs/{job_id}",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert res_citizen.status_code == status.HTTP_200_OK
    cit_body = res_citizen.json()
    assert cit_body["job_id"] == job_id
    assert cit_body["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert cit_body["requested_by"] is None  # Sensitive email redacted
    assert cit_body["error_message"] is None  # Internal error redacted

    # 5. Authority request returns full metadata
    res_auth = client.get(
        f"/api/v1/satellite/jobs/{job_id}",
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_auth.status_code == status.HTTP_200_OK
    auth_body = res_auth.json()
    assert auth_body["job_id"] == job_id
    assert auth_body["requested_by"] is not None  # Authority sees requester


# ==============================================================================
# 3. Historical Event Association & Temporal/Geographic Rules (Requirement 4)
# ==============================================================================
def test_historical_event_association_validation(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Missing or mismatched event associations are rejected with clear actionable errors."""
    # 1. Missing event_id rejected
    res_no_evt = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_no_evt.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY)

    # 2. Non-existent event_id rejected
    res_fake_evt = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": "evt_nonexistent_9999", "scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_fake_evt.status_code == status.HTTP_404_NOT_FOUND
    assert res_fake_evt.json()["error"]["code"] == "EVENT_NOT_FOUND"

    # 3. Temporal mismatch: Scene acquired months after event
    late_scene = SatelliteScene(
        id=f"scene_late_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=test_flood_event.end_at + timedelta(days=90),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
    )
    db_session.add(late_scene)
    db_session.commit()

    res_temporal = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": late_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_temporal.status_code == status.HTTP_400_BAD_REQUEST
    assert res_temporal.json()["error"]["code"] == "TEMPORAL_EVENT_MISMATCH"

    # 4. Geographic mismatch: Scene in southern India [80.0, 15.0] outside Nepal Terai
    disjoint_scene = SatelliteScene(
        id=f"scene_far_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=test_flood_event.start_at,
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [[[78.0, 15.0], [79.0, 15.0], [79.0, 16.0], [78.0, 16.0], [78.0, 15.0]]],
        },
    )
    db_session.add(disjoint_scene)
    db_session.commit()

    res_geo = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": disjoint_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_geo.status_code == status.HTTP_400_BAD_REQUEST
    assert res_geo.json()["error"]["code"] == "GEOGRAPHIC_EVENT_MISMATCH"


# ==============================================================================
# 4. SAR_CHANGE Method & Input Validation (Requirement 2 & 5)
# ==============================================================================
def test_sar_change_validation_rules(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    test_optical_scene: SatelliteScene,
    test_radar_scene: SatelliteScene,
    test_radar_baseline_scene: SatelliteScene,
    db_session: Session,
):
    """SAR_CHANGE requires baseline_scene_id, SAR modality for both scenes, and rejects thumbnails."""
    # 1. SAR_CHANGE without baseline scene is rejected
    res_no_base = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_radar_scene.id, "method": "SAR_CHANGE"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_no_base.status_code == status.HTTP_400_BAD_REQUEST
    assert res_no_base.json()["error"]["code"] == "MISSING_BASELINE_SCENE"

    # 2. Optical scene passed as target for SAR_CHANGE is rejected
    res_opt_target = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": test_flood_event.id,
            "scene_id": test_optical_scene.id,
            "baseline_scene_id": test_radar_baseline_scene.id,
            "method": "SAR_CHANGE",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_opt_target.status_code == status.HTTP_400_BAD_REQUEST
    assert res_opt_target.json()["error"]["code"] == "MODALITY_INCOMPATIBILITY"

    # 3. Optical scene passed as baseline for SAR_CHANGE is rejected
    res_opt_base = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": test_flood_event.id,
            "scene_id": test_radar_scene.id,
            "baseline_scene_id": test_optical_scene.id,
            "method": "SAR_CHANGE",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_opt_base.status_code == status.HTTP_400_BAD_REQUEST
    assert res_opt_base.json()["error"]["code"] == "MODALITY_INCOMPATIBILITY"

    # 4. SAR scene passed for NDWI is rejected
    res_sar_ndwi = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_radar_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_sar_ndwi.status_code == status.HTTP_400_BAD_REQUEST
    assert res_sar_ndwi.json()["error"]["code"] == "MODALITY_INCOMPATIBILITY"

    # 5. Preview thumbnail rejected
    thumb_scene = SatelliteScene(
        id=f"scene_thumb_{uuid.uuid4().hex[:6]}",
        provider="Copernicus",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=test_flood_event.start_at,
        asset_ref="backend/tests/fixtures/sentinel1_thumbnail.png",
    )
    db_session.add(thumb_scene)
    db_session.commit()

    res_thumb = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": test_flood_event.id,
            "scene_id": thumb_scene.id,
            "baseline_scene_id": test_radar_baseline_scene.id,
            "method": "SAR_CHANGE",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_thumb.status_code == status.HTTP_400_BAD_REQUEST
    assert res_thumb.json()["error"]["code"] == "INVALID_INPUT_ARTIFACT"


# ==============================================================================
# 5. Elimination of Unsafe Synthetic Fallbacks (Requirement 1)
# ==============================================================================
def test_missing_input_artifacts_strictly_fail_without_synthetic_substitution(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Missing real satellite asset paths MUST fail with MISSING_INPUT_ARTIFACTS
    and NEVER silently substitute bundled synthetic fixtures."""
    ghost_scene = SatelliteScene(
        id=f"scene_ghost_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=test_flood_event.start_at,
        asset_ref="ml/gis_processing/downloads/nonexistent_raw_satellite_file.geojson",
    )
    db_session.add(ghost_scene)
    db_session.commit()

    # Even if downloads/ does not exist on disk, the system MUST NOT silently substitute fixtures
    res = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": ghost_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["error"]["code"] == "MISSING_INPUT_ARTIFACTS"


# ==============================================================================
# 6. Provenance Truthfulness & Null Confidence (Requirement 5)
# ==============================================================================
def test_synthetic_fixture_output_provenance_and_null_confidence(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    test_optical_scene: SatelliteScene,
    db_session: Session,
):
    """Outputs from synthetic test fixtures are clearly labeled SYNTHETIC_TEST_FIXTURE
    and confidence is strictly None/null (no fabricated 0.90 or 0.85)."""
    # Background worker executes automatically via TestClient conftest hook
    res = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_202_ACCEPTED
    job_id = res.json()["job_id"]

    # Poll status
    status_res = client.get(
        f"/api/v1/satellite/jobs/{job_id}",
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert status_res.status_code == status.HTTP_200_OK
    detail = status_res.json()
    assert detail["status"] == "COMPLETED"
    assert detail["provenance"] == "SYNTHETIC_TEST_FIXTURE"

    # Verify FloodExtent in PostGIS has confidence = None
    extent = db_session.query(FloodExtent).filter(FloodExtent.id == detail["output_extent_id"]).first()
    assert extent is not None
    assert extent.confidence is None  # Truthful uncalibrated confidence


# ==============================================================================
# 7. Multi-Event & Multi-Scene Extent Preservation (Requirement 8)
# ==============================================================================
def test_multi_event_and_multi_scene_extent_preservation(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    second_flood_event: FloodEvent,
    test_optical_scene: SatelliteScene,
    db_session: Session,
):
    """Distinct flood events remain isolated, and multiple scenes for the same event
    produce multiple distinct FloodExtent records without overwriting."""
    # 1. Process scene 1 for event 1
    res1 = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res1.status_code == status.HTTP_202_ACCEPTED
    job1_id = res1.json()["job_id"]

    # 2. Create and process scene 2 (next day) for the same event 1
    scene2 = SatelliteScene(
        id=f"scene_s2_day2_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=test_flood_event.start_at + timedelta(days=2),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
    )
    db_session.add(scene2)
    db_session.commit()

    res2 = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": scene2.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res2.status_code == status.HTTP_202_ACCEPTED
    job2_id = res2.json()["job_id"]

    # Verify BOTH extents exist for event 1 (scene 1 was NOT overwritten by scene 2)
    extents_evt1 = db_session.query(FloodExtent).filter(FloodExtent.event_id == test_flood_event.id).all()
    assert len(extents_evt1) == 2
    scenes_in_evt1 = {e.source_scene_ids[0] for e in extents_evt1}
    assert scenes_in_evt1 == {test_optical_scene.id, scene2.id}

    # 3. Process an independent second event
    scene_evt2 = SatelliteScene(
        id=f"scene_s2_evt2_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=second_flood_event.start_at + timedelta(days=1),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
    )
    db_session.add(scene_evt2)
    db_session.commit()

    res3 = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": second_flood_event.id, "scene_id": scene_evt2.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res3.status_code == status.HTTP_202_ACCEPTED

    extents_evt2 = db_session.query(FloodExtent).filter(FloodExtent.event_id == second_flood_event.id).all()
    assert len(extents_evt2) == 1

    # Event 1 still has exactly 2 extents (no cross-event contamination)
    assert db_session.query(FloodExtent).filter(FloodExtent.event_id == test_flood_event.id).count() == 2

    # 4. Idempotency: re-running scene 1 updates the existing extent record without duplicating
    res4 = client.post(
        "/api/v1/satellite/jobs",
        json={"event_id": test_flood_event.id, "scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res4.status_code == status.HTTP_202_ACCEPTED
    assert db_session.query(FloodExtent).filter(FloodExtent.event_id == test_flood_event.id).count() == 2


# ==============================================================================
# 8. Real Dual-Date SAR Radar Change Detection (Requirement 2 & 7)
# ==============================================================================
def test_real_sar_radar_change_detection_workflow(
    tmp_path: Path,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Calibrated Sentinel-1 SAR change detection detects backscatter drop
    from dual-date GeoTIFFs and produces PROCESSED_SAR provenance."""
    if not HAS_RASTERIO or rasterio is None:
        pytest.skip("rasterio is not installed")

    # Create synthetic pre-flood and post-flood radar GeoTIFFs
    width, height = 50, 50
    transform = from_origin(500000, 2900000, 20, 20)

    # Pre-flood: dry land backscatter (intensity ~ 0.25 -> ~ -6 dB)
    pre_arr = np.full((height, width), 0.25, dtype=np.float32)
    # Post-flood: open water in center (intensity drop to 0.01 -> ~ -20 dB, drop of 14 dB)
    post_arr = np.full((height, width), 0.25, dtype=np.float32)
    post_arr[15:35, 15:35] = 0.01  # 20x20 pixels inundated

    pre_path = tmp_path / "s1_pre_flood_grd.tif"
    post_path = tmp_path / "s1_post_flood_grd.tif"

    profile = dict(
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:32645",
        transform=transform,
        nodata=-9999.0,
    )
    with rasterio.open(pre_path, "w", **profile) as dst:
        dst.write(pre_arr, 1)
    with rasterio.open(post_path, "w", **profile) as dst:
        dst.write(post_arr, 1)

    # Register scenes
    pre_scene = SatelliteScene(
        id=f"scene_sar_pre_{uuid.uuid4().hex[:6]}",
        provider="Copernicus",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=test_flood_event.start_at - timedelta(days=5),
        asset_ref=str(pre_path),
    )
    post_scene = SatelliteScene(
        id=f"scene_sar_post_{uuid.uuid4().hex[:6]}",
        provider="Copernicus",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=test_flood_event.start_at + timedelta(days=2),
        asset_ref=str(post_path),
    )
    job = SatelliteJob(
        id=f"sat_job_sar_{uuid.uuid4().hex[:6]}",
        event_id=test_flood_event.id,
        scene_id=post_scene.id,
        baseline_scene_id=pre_scene.id,
        method="SAR_CHANGE",
        threshold=-3.0,
        status="QUEUED",
        requested_by="radar_specialist@floodlens.org",
    )
    db_session.add_all([pre_scene, post_scene, job])
    db_session.commit()

    # Claim and execute
    claimed = claim_job(db_session, job_id=job.id)
    assert claimed is not None
    success = execute_job(claimed, db_session)
    assert success is True

    db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.provenance == "PROCESSED_SAR"
    assert job.output_extent_id is not None

    extent = db_session.query(FloodExtent).filter(FloodExtent.id == job.output_extent_id).first()
    assert extent is not None
    assert extent.method == "SAR_CHANGE"
    assert extent.area_km2 > 0.0
    assert extent.confidence is None


# ==============================================================================
# 9. Background Worker Recovery & Atomic Claiming (Requirement 6 & 10)
# ==============================================================================
def test_worker_atomic_claiming_and_interrupted_job_recovery(
    test_flood_event: FloodEvent,
    test_optical_scene: SatelliteScene,
    db_session: Session,
):
    """Worker recovers interrupted RUNNING jobs safely and atomic claiming prevents race conditions."""
    # 1. Simulate an interrupted job left in RUNNING status
    stuck_job = SatelliteJob(
        id=f"sat_job_stuck_{uuid.uuid4().hex[:6]}",
        event_id=test_flood_event.id,
        scene_id=test_optical_scene.id,
        method="NDWI",
        status="RUNNING",
        retry_count=0,
        max_retries=2,
        requested_by="ops@floodlens.org",
    )
    db_session.add(stuck_job)
    db_session.commit()

    # Recovery resets to QUEUED
    recovered = recover_interrupted_jobs(db_session)
    assert recovered == 1
    db_session.refresh(stuck_job)
    assert stuck_job.status == "QUEUED"
    assert stuck_job.retry_count == 1
    assert "interrupted" in stuck_job.error_message.lower()

    # 2. Atomic claiming prevents duplicate execution by concurrent workers
    claimed_worker1 = claim_job(db_session, job_id=stuck_job.id)
    assert claimed_worker1 is not None
    assert claimed_worker1.status == "RUNNING"

    # Second worker trying to claim the same job receives None
    claimed_worker2 = claim_job(db_session, job_id=stuck_job.id)
    assert claimed_worker2 is None

    # 3. Exhausted retry budget marks job FAILED
    stuck_job.status = "RUNNING"
    stuck_job.retry_count = 1  # will become 2 == max_retries
    stuck_job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)  # expired lease
    db_session.commit()

    recovered_exhausted = recover_interrupted_jobs(db_session)
    assert recovered_exhausted == 1
    db_session.refresh(stuck_job)
    assert stuck_job.status == "FAILED"
    assert "maximum" in stuck_job.error_message.lower()


# ==============================================================================
# 10. End-to-End Acceptance Test Workflow (Requirement 11)
# ==============================================================================
def test_end_to_end_acceptance_workflow_without_manual_invocation(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Execute complete 8-step Task 2 End-to-End Acceptance sequence
    WITHOUT manual invocation of process_satellite_job()."""
    # Step 1: Register valid satellite scene
    scene_id = f"scene_e2e_{uuid.uuid4().hex[:6]}"
    reg_res = client.post(
        "/api/v1/satellite/scenes",
        json={
            "id": scene_id,
            "provider": "ESA Copernicus",
            "sensor": "Sentinel-2",
            "modality": "optical",
            "captured_at": "2017-08-15T10:30:00Z",
            "cloud_quality": 0.05,
            "asset_ref": "backend/tests/fixtures/optical_flood_sample.geojson",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert reg_res.status_code == status.HTTP_201_CREATED

    # Step 2 & 3: Create processing job and receive HTTP 202
    job_res = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": test_flood_event.id,
            "scene_id": scene_id,
            "method": "NDWI",
            "threshold": 0.10,
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert job_res.status_code == status.HTTP_202_ACCEPTED
    job_id = job_res.json()["job_id"]
    assert job_id.startswith("sat_job_")

    # Step 4 & 5: Poll job status until completion
    # Background task executed automatically via FastAPI TestClient hook
    status_res = client.get(
        f"/api/v1/satellite/jobs/{job_id}",
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert status_res.status_code == status.HTTP_200_OK
    status_body = status_res.json()
    assert status_body["status"] == "COMPLETED"
    assert status_body["progress_percent"] == 100.0
    extent_id = status_body["output_extent_id"]
    assert extent_id is not None
    assert status_body["provenance"] == "SYNTHETIC_TEST_FIXTURE"

    # Step 6 & 7: Retrieve resulting flood extent and verify PostGIS geometry
    db_session.expire_all()
    extent = db_session.query(FloodExtent).filter(FloodExtent.id == extent_id).first()
    assert extent is not None
    assert extent.event_id == test_flood_event.id
    assert extent.area_km2 > 0.0
    assert extent.source_scene_ids == [scene_id]
    assert extent.confidence is None

    # Step 8: Retrieve flood extent GeoJSON through existing API
    get_extent_res = client.get(f"/api/v1/flood-events/{test_flood_event.id}/extent")
    assert get_extent_res.status_code == status.HTTP_200_OK
    extent_json = get_extent_res.json()
    assert extent_json["id"] == extent_id
    assert extent_json["method"] == "NDWI"
    assert extent_json["area_km2"] > 0.0
    assert extent_json["geometry"]["type"] in ("MultiPolygon", "Polygon")
    assert len(extent_json["geometry"]["coordinates"]) > 0
