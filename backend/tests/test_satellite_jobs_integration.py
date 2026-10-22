"""Comprehensive integration tests for Satellite Processing Pipeline -> FastAPI Integration.

Validates all Task 2 requirements:
1. Authority can create a valid satellite job.
2. Citizen and anonymous users cannot create jobs (401/403).
3. Invalid scene IDs are rejected (404/400).
4. Unsupported processing methods are rejected (MNDWI, invalid method, modality mismatch, temporal/geographic incompatibility).
5. Missing input artifacts fail safely.
6. Job status persists across database sessions.
7. Valid processing produces a real output artifact with measurable area.
8. Flood extent is correctly persisted in PostGIS with valid EPSG:4326 geometry and UTM 45N metric area.
9. Duplicate job requests maintain idempotency without creating duplicate outputs.
10. Worker errors produce FAILED status and sanitized error messages.
11. Jobs remain recoverable after simulated worker restarts.
12. Existing satellite scene and event extent APIs remain fully compatible.
13. Complete End-to-End Acceptance Test sequence from scene registration to GeoJSON retrieval.
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
from app.services.satellite_processor import (
    compute_metric_area_km2,
    process_satellite_job,
    recover_pending_jobs,
)


@pytest.fixture
def test_optical_scene(db_session: Session) -> SatelliteScene:
    """Create a verified optical scene pointing to the precomputed web flood polygons."""
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
    """Create a verified SAR scene pointing to the precomputed radar flood polygons."""
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
def test_flood_event(db_session: Session) -> FloodEvent:
    """Create a standard flood event record."""
    event = FloodEvent(
        id=f"evt_test_{uuid.uuid4().hex[:8]}",
        region_id="nepal_terai",
        name="Nepal Terai Monsoon Event",
        start_at=datetime(2017, 8, 11, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture
def small_geotiff_fixture(tmp_path: Path) -> Path:
    """Create a minimal synthetic GeoTIFF flood mask (100x100 pixels, UTM Zone 45N)."""
    if not HAS_RASTERIO or rasterio is None:
        pytest.skip("rasterio is not installed")
    file_path = tmp_path / "synthetic_flood_mask.tif"
    width, height = 100, 100
    # 10m resolution in UTM Zone 45N near Koshi basin
    transform = from_origin(500000, 2900000, 10, 10)
    data = np.zeros((height, width), dtype=np.uint8)
    # Mark a 40x40 pixel square as flooded (value = 1) -> 1600 pixels * 100m² = 0.16 km²
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
    """Authority user can submit a valid NDWI processing job and receive HTTP 202."""
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
):
    """Anonymous (401) and citizen (403) requests must be rejected."""
    payload = {"scene_id": test_optical_scene.id, "method": "NDWI"}

    # Anonymous
    anon_res = client.post("/api/v1/satellite/jobs", json=payload)
    assert anon_res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    # Citizen
    cit_res = client.post(
        "/api/v1/satellite/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert cit_res.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# 2. Input Parameter & Integrity Validation (Requirements 3 & 4)
# ==============================================================================
def test_invalid_scene_ids_rejected(client: TestClient, authority_token: str):
    """Unknown scene IDs return 404; missing scene ID returns 400."""
    # Unknown ID
    res = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": "scene_nonexistent_xyz_999", "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["error"]["code"] == "SCENE_NOT_FOUND"

    # Missing ID
    res2 = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": None, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert res2.json()["error"]["code"] == "MISSING_SCENE_ID"


def test_unsupported_methods_rejected(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
):
    """MNDWI and unknown methods are rejected with actionable 400 errors."""
    # MNDWI unsupported in current optical pipeline
    res_mndwi = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_optical_scene.id, "method": "MNDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_mndwi.status_code == status.HTTP_400_BAD_REQUEST
    assert res_mndwi.json()["error"]["code"] == "UNSUPPORTED_PROCESSING_METHOD"
    assert "SWIR band required" in res_mndwi.json()["error"]["message"]

    # Unknown method
    res_unknown = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_optical_scene.id, "method": "UNRECOGNIZED_METHOD"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_unknown.status_code == status.HTTP_400_BAD_REQUEST
    assert res_unknown.json()["error"]["code"] == "INVALID_PROCESSING_METHOD"


def test_modality_incompatibility_rejected(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
    test_radar_scene: SatelliteScene,
):
    """NDWI requires optical; SAR_CHANGE requires radar."""
    # NDWI on SAR scene
    res1 = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_radar_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res1.status_code == status.HTTP_400_BAD_REQUEST
    assert res1.json()["error"]["code"] == "MODALITY_INCOMPATIBILITY"

    # SAR_CHANGE on optical scene
    res2 = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_optical_scene.id, "method": "SAR_CHANGE"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res2.status_code == status.HTTP_400_BAD_REQUEST
    assert res2.json()["error"]["code"] == "MODALITY_INCOMPATIBILITY"


def test_temporal_and_geographic_incompatibility_rejected(
    client: TestClient,
    authority_token: str,
    db_session: Session,
):
    """Baseline scene must precede target scene and overlap geographically."""
    now = datetime.now(timezone.utc)
    target = SatelliteScene(
        id=f"scene_target_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=now,
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [[[87.0, 26.0], [87.5, 26.0], [87.5, 26.5], [87.0, 26.5], [87.0, 26.0]]],
        },
    )
    # Inverted temporal: baseline captured AFTER target
    inverted_base = SatelliteScene(
        id=f"scene_base_inv_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=now + timedelta(days=5),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [[[87.0, 26.0], [87.5, 26.0], [87.5, 26.5], [87.0, 26.5], [87.0, 26.0]]],
        },
    )
    # Disjoint geographic footprint
    disjoint_base = SatelliteScene(
        id=f"scene_base_disj_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=now - timedelta(days=5),
        asset_ref="backend/tests/fixtures/optical_flood_sample.geojson",
        bbox_geojson={
            "type": "Polygon",
            "coordinates": [[[80.0, 20.0], [80.5, 20.0], [80.5, 20.5], [80.0, 20.5], [80.0, 20.0]]],
        },
    )
    db_session.add_all([target, inverted_base, disjoint_base])
    db_session.commit()

    # Inverted temporal test
    res_time = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": target.id, "baseline_scene_id": inverted_base.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_time.status_code == status.HTTP_400_BAD_REQUEST
    assert res_time.json()["error"]["code"] == "TEMPORAL_INCOMPATIBILITY"

    # Disjoint geography test
    res_geo = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": target.id, "baseline_scene_id": disjoint_base.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_geo.status_code == status.HTTP_400_BAD_REQUEST
    assert res_geo.json()["error"]["code"] == "GEOGRAPHIC_INCOMPATIBILITY"


def test_security_path_traversal_and_thumbnails_rejected(
    client: TestClient,
    authority_token: str,
    db_session: Session,
):
    """Path traversal is blocked and preview thumbnails are rejected for SAR processing."""
    now = datetime.now(timezone.utc)
    traversal_scene = SatelliteScene(
        id=f"scene_traversal_{uuid.uuid4().hex[:6]}",
        provider="Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=now,
        asset_ref="../../etc/passwd",
    )
    thumbnail_scene = SatelliteScene(
        id=f"scene_thumb_{uuid.uuid4().hex[:6]}",
        provider="Copernicus",
        sensor="Sentinel-1 SAR",
        modality="sar",
        captured_at=now,
        asset_ref="ml/gis_processing/downloads/sentinel1_pre_flood_thumbnail.png",
    )
    db_session.add_all([traversal_scene, thumbnail_scene])
    db_session.commit()

    # Traversal test
    res_trav = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": traversal_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_trav.status_code == status.HTTP_400_BAD_REQUEST
    assert res_trav.json()["error"]["code"] == "SECURITY_VIOLATION"

    # Thumbnail test
    res_thumb = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": thumbnail_scene.id, "method": "SAR_CHANGE"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_thumb.status_code == status.HTTP_400_BAD_REQUEST
    assert res_thumb.json()["error"]["code"] == "INVALID_INPUT_ARTIFACT"
    assert "browse images" in res_thumb.json()["error"]["message"]


# ==============================================================================
# 3. Missing Artifact Safety & Persistence (Requirements 5 & 6)
# ==============================================================================
def test_missing_input_artifacts_fail_safely(
    client: TestClient,
    authority_token: str,
    db_session: Session,
):
    """Missing file references fail safely at job submission."""
    missing_scene = SatelliteScene(
        id=f"scene_missing_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime.now(timezone.utc),
        asset_ref="ml/gis_processing/downloads/non_existent_band_file_xyz.tif",
    )
    db_session.add(missing_scene)
    db_session.commit()

    res = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": missing_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["error"]["code"] == "MISSING_INPUT_ARTIFACTS"


def test_job_status_persists_across_sessions(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
):
    """Job status persists durably in the database and is readable via GET."""
    post_res = client.post(
        "/api/v1/satellite/jobs",
        json={"scene_id": test_optical_scene.id, "method": "NDWI"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    job_id = post_res.json()["job_id"]

    # Poll status
    get_res = client.get(f"/api/v1/satellite/jobs/{job_id}")
    assert get_res.status_code == status.HTTP_200_OK
    detail = get_res.json()
    assert detail["job_id"] == job_id
    assert detail["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert detail["method"] == "NDWI"
    assert detail["created_at"] is not None


# ==============================================================================
# 4. GIS Algorithms, Artifact Outputs & PostGIS (Requirements 7 & 8)
# ==============================================================================
def test_valid_raster_processing_produces_real_output_and_postgis_extent(
    db_session: Session,
    test_flood_event: FloodEvent,
    small_geotiff_fixture: Path,
):
    """Processing a GeoTIFF raster mask produces real output polygons and persists in PostGIS."""
    scene = SatelliteScene(
        id=f"scene_geotiff_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime.now(timezone.utc),
        asset_ref=str(small_geotiff_fixture),
    )
    job = SatelliteJob(
        id=f"sat_job_geotiff_{uuid.uuid4().hex[:6]}",
        event_id=test_flood_event.id,
        scene_id=scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="qa_tester@floodlens.org",
    )
    db_session.add_all([scene, job])
    db_session.commit()

    # Execute processing worker
    process_satellite_job(job.id, db_session=db_session)

    # Verify job completed
    db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.progress_percent == 100.0
    assert job.output_extent_id is not None

    # Verify FloodExtent in PostGIS
    extent = db_session.query(FloodExtent).filter(FloodExtent.id == job.output_extent_id).first()
    assert extent is not None
    assert extent.event_id == test_flood_event.id
    assert extent.method == "NDWI"
    assert extent.area_km2 > 0.0
    assert extent.geometry is not None
    # 40x40 pixels @ 10m = 0.16 km²
    assert 0.10 <= extent.area_km2 <= 0.25


def test_metric_area_calculation_consistency():
    """Verify UTM Zone 45N metric projection area computation."""
    # Simple 0.01 x 0.01 degree square in Nepal Terai (~1.1 km x 1.0 km ~ 1.1 km²)
    poly = Polygon([[87.0, 26.5], [87.01, 26.5], [87.01, 26.51], [87.0, 26.51], [87.0, 26.5]])
    area_km2 = compute_metric_area_km2(poly)
    assert 1.0 <= area_km2 <= 1.3


# ==============================================================================
# 5. Idempotency & Duplicate Request Protection (Requirement 9)
# ==============================================================================
def test_duplicate_job_requests_and_idempotent_postgis_updates(
    client: TestClient,
    authority_token: str,
    test_optical_scene: SatelliteScene,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Duplicate job submissions do not duplicate work or database rows."""
    payload = {
        "event_id": test_flood_event.id,
        "scene_id": test_optical_scene.id,
        "method": "NDWI",
        "threshold": 0.10,
    }

    # Initial request
    res1 = client.post(
        "/api/v1/satellite/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    job_id_1 = res1.json()["job_id"]

    # Duplicate submission while pending
    res2 = client.post(
        "/api/v1/satellite/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res2.status_code == status.HTTP_202_ACCEPTED
    assert res2.json()["job_id"] == job_id_1
    assert "already in progress" in res2.json()["message"]

    # Process job to completion
    process_satellite_job(job_id_1, db_session=db_session)

    # Re-run process_satellite_job idempotency check
    initial_extents_count = db_session.query(FloodExtent).filter(FloodExtent.event_id == test_flood_event.id).count()
    process_satellite_job(job_id_1, db_session=db_session)
    final_extents_count = db_session.query(FloodExtent).filter(FloodExtent.event_id == test_flood_event.id).count()
    assert initial_extents_count == final_extents_count


# ==============================================================================
# 6. Worker Error Handling & Restart Recovery (Requirements 10 & 11)
# ==============================================================================
def test_worker_errors_produce_failed_status_and_sanitized_message(
    db_session: Session,
    test_flood_event: FloodEvent,
    tmp_path: Path,
):
    """Corrupted inputs cause job to fail safely without exposing internal paths."""
    corrupted_file = tmp_path / "corrupted_file.geojson"
    corrupted_file.write_text("{ this is corrupted invalid json }}}", encoding="utf-8")

    scene = SatelliteScene(
        id=f"scene_corrupt_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime.now(timezone.utc),
        asset_ref=str(corrupted_file),
    )
    job = SatelliteJob(
        id=f"sat_job_corrupt_{uuid.uuid4().hex[:6]}",
        event_id=test_flood_event.id,
        scene_id=scene.id,
        method="NDWI",
        status="QUEUED",
        requested_by="qa_tester@floodlens.org",
        max_retries=1,
    )
    db_session.add_all([scene, job])
    db_session.commit()

    # Process job
    process_satellite_job(job.id, db_session=db_session)

    db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.error_message is not None
    # Ensure sensitive paths are sanitized
    assert str(Path.cwd()) not in job.error_message


def test_jobs_remain_recoverable_after_simulated_worker_restart(db_session: Session):
    """Simulated worker restart re-queues active jobs and fails jobs exceeding max retries."""
    now = datetime.now(timezone.utc)
    # Job 1: below max retries
    job_retryable = SatelliteJob(
        id=f"sat_job_restart_1_{uuid.uuid4().hex[:6]}",
        method="NDWI",
        status="RUNNING",
        started_at=now,
        retry_count=0,
        max_retries=2,
        requested_by="admin@floodlens.org",
    )
    # Job 2: at max retries
    job_exhausted = SatelliteJob(
        id=f"sat_job_restart_2_{uuid.uuid4().hex[:6]}",
        method="NDWI",
        status="RUNNING",
        started_at=now,
        retry_count=2,
        max_retries=2,
        requested_by="admin@floodlens.org",
    )
    db_session.add_all([job_retryable, job_exhausted])
    db_session.commit()

    # Worker recovery trigger
    recovered_count = recover_pending_jobs(db_session)
    assert recovered_count == 2

    db_session.refresh(job_retryable)
    db_session.refresh(job_exhausted)

    # Job 1 re-queued
    assert job_retryable.status == "QUEUED"
    assert job_retryable.retry_count == 1
    assert "Recovered after worker restart" in job_retryable.error_message

    # Job 2 failed
    assert job_exhausted.status == "FAILED"
    assert "maximum retry limit exceeded" in job_exhausted.error_message


# ==============================================================================
# 7. Complete End-to-End Acceptance Test (Requirement 10)
# ==============================================================================
def test_end_to_end_acceptance_workflow(
    client: TestClient,
    authority_token: str,
    test_flood_event: FloodEvent,
    db_session: Session,
):
    """Execute complete 8-step Task 2 End-to-End Acceptance sequence."""
    # Step 1: Register valid historical satellite scene
    scene_id = f"scene_e2e_opt_{uuid.uuid4().hex[:6]}"
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

    # Step 4: Execute background worker
    process_satellite_job(job_id, db_session=db_session)

    # Step 5: Poll job status until completion
    status_res = client.get(f"/api/v1/satellite/jobs/{job_id}")
    assert status_res.status_code == status.HTTP_200_OK
    status_body = status_res.json()
    assert status_body["status"] == "COMPLETED"
    assert status_body["progress_percent"] == 100.0
    extent_id = status_body["output_extent_id"]
    assert extent_id is not None
    assert status_body["provenance"] == "IMPORTED_PRECOMPUTED"

    # Step 6 & 7: Retrieve resulting flood extent and verify PostGIS geometry
    db_session.expire_all()
    extent = db_session.query(FloodExtent).filter(FloodExtent.id == extent_id).first()
    assert extent is not None
    assert extent.event_id == test_flood_event.id
    assert extent.area_km2 > 0.0
    assert extent.source_scene_ids == [scene_id]

    # Step 8: Retrieve flood extent GeoJSON through existing API
    get_extent_res = client.get(f"/api/v1/flood-events/{test_flood_event.id}/extent")
    assert get_extent_res.status_code == status.HTTP_200_OK
    extent_json = get_extent_res.json()
    assert extent_json["id"] == extent_id
    assert extent_json["method"] == "NDWI"
    assert extent_json["area_km2"] > 0.0
    assert extent_json["geometry"]["type"] in ("MultiPolygon", "Polygon")
    assert len(extent_json["geometry"]["coordinates"]) > 0
