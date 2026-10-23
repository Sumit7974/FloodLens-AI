"""Comprehensive unit and integration tests for reproducible optical flood detection.

Validates:
1. Valid pre/post Sentinel-2 bands (B03 Green, B08 NIR, SCL).
2. Missing baseline rejection for empirical optical new-flood jobs.
3. Invalid CRS mismatch rejection.
4. Exact affine-grid validation within scenes and across acquisitions.
5. Reprojection of multi-resolution SCL and shifted rasters onto target grid using rasterio.
6. Documented SCL quality policy: strict masking of Class 2 (dark features/shadow)
   and Class 7 (unclassified/ambiguous), with regression tests.
7. Sentinel-2 reflectance scaling and processing-baseline offsets (PB < 04.00 vs >= 04.00).
8. NoData and saturated pixel handling.
9. Persistent water exclusion from new inundation.
10. Newly inundated water extraction.
11. Missing valid shared coverage marked as unobserved (255), never dry land.
12. Metric flood area calculation in km² (EPSG:32645).
13. GeoTIFF metadata preservation (CRS, transform, NoData).
14. GeoJSON polygon validity in EPSG:4326.
15. FastAPI job endpoint integration and worker execution.
16. PostGIS flood extent persistence and readback (distinguishing SQLite from PostgreSQL).
17. Truthful provenance labeling.
18. Genuine empirical historical Koshi rerun test (executed locally, labeled NOT EXECUTED in CI).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pytest
import rasterio
from affine import Affine
from shapely.geometry import Polygon, MultiPolygon, shape
from sqlalchemy.orm import Session

from app.core.exceptions import FloodLensAPIException
from app.database import Base, engine
from app.models.enums import UserRole
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent, SatelliteJob, SatelliteScene
from app.models.user import User
from fastapi.testclient import TestClient

from app.schemas.satellite import SatelliteJobCreate
from app.services.satellite_processor import (
    _process_optical_bands,
    compute_artifact_checksum,
    compute_extent_identity,
    execute_satellite_pipeline,
    normalize_processing_parameters,
    validate_satellite_job_parameters,
    set_test_db_session,
    OUTPUT_DIR,
)
from app.workers.satellite_worker import claim_job, execute_job
from ml.gis_processing.calculate_ndwi import (
    affine_transforms_equal,
    classify_flood_dynamics,
    compute_ndwi,
    dn_to_reflectance,
    extract_scl_mask,
    process_optical_flood_pair,
    reproject_to_target_grid,
    validate_spatial_alignment,
    CONSERVATIVE_UNSUITABLE_SCL_CLASSES,
    PERMISSIVE_UNSUITABLE_SCL_CLASSES,
)


@pytest.fixture(scope="module")
def synthetic_optical_fixtures(tmp_path_factory):
    """Create lightweight, calibrated synthetic Sentinel-2 optical band fixtures for CI."""
    base_dir = tmp_path_factory.mktemp("optical_fixtures")
    pre_dir = base_dir / "pre_flood"
    post_dir = base_dir / "post_flood"
    pre_dir.mkdir(parents=True)
    post_dir.mkdir(parents=True)

    # 100x100 pixels at 10m resolution in UTM 45N (EPSG:32645)
    # Origin: x=580000, y=2920000 (Koshi study region)
    width, height = 100, 100
    transform = Affine(10.0, 0.0, 580000.0, 0.0, -10.0, 2920000.0)
    crs = "EPSG:32645"

    profile_10m = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "uint16",
        "crs": crs,
        "transform": transform,
        "nodata": 0,
        "compress": "deflate",
    }

    # Pre-flood baseline reflectance:
    # Most is vegetation/bare soil: Green ~ 1000, NIR ~ 3000 (NDWI = -0.50)
    # Permanent river in rows 0..20, cols 40..60: Green ~ 2000, NIR ~ 500 (NDWI = +0.60)
    pre_green = np.full((height, width), 1000, dtype=np.uint16)
    pre_nir = np.full((height, width), 3000, dtype=np.uint16)
    pre_green[0:20, 40:60] = 2000
    pre_nir[0:20, 40:60] = 500

    # Pre-flood SCL: 4 (vegetation) everywhere, 6 (water) in river
    pre_scl = np.full((height, width), 4, dtype=np.uint8)
    pre_scl[0:20, 40:60] = 6

    # Post-flood reflectance:
    # Permanent river remains: rows 0..20, cols 40..60 (Green ~ 2000, NIR ~ 500)
    # Newly inundated floodwater in rows 40..70, cols 20..80: Green ~ 2200, NIR ~ 600 (NDWI = +0.57)
    # Clouds in rows 80..100, cols 0..30 (Green ~ 8000, NIR ~ 8000)
    # Cloud shadow in rows 80..100, cols 30..50 (Green ~ 300, NIR ~ 200)
    post_green = np.full((height, width), 1000, dtype=np.uint16)
    post_nir = np.full((height, width), 3000, dtype=np.uint16)
    post_green[0:20, 40:60] = 2000
    post_nir[0:20, 40:60] = 500
    post_green[40:70, 20:80] = 2200
    post_nir[40:70, 20:80] = 600
    post_green[80:100, 0:30] = 8000
    post_nir[80:100, 0:30] = 8000
    post_green[80:100, 30:50] = 300
    post_nir[80:100, 30:50] = 200

    # Post-flood SCL:
    post_scl = np.full((height, width), 4, dtype=np.uint8)
    post_scl[0:20, 40:60] = 6        # persistent water
    post_scl[40:70, 20:80] = 6       # newly flooded water
    post_scl[80:100, 0:30] = 9       # cloud high probability
    post_scl[80:100, 30:50] = 3      # cloud shadow

    # Write GeoTIFFs
    for d, pfx, g, n, s in [
        (pre_dir, "pre_flood", pre_green, pre_nir, pre_scl),
        (post_dir, "post_flood", post_green, post_nir, post_scl),
    ]:
        with rasterio.open(d / f"{pfx}_B03.tif", "w", **profile_10m) as dst:
            dst.write(g, 1)
        with rasterio.open(d / f"{pfx}_B08.tif", "w", **profile_10m) as dst:
            dst.write(n, 1)

        prof_scl = profile_10m.copy()
        prof_scl.update(dtype="uint8")
        with rasterio.open(d / f"{pfx}_SCL.tif", "w", **prof_scl) as dst:
            dst.write(s, 1)

    return {
        "pre_dir": pre_dir,
        "post_dir": post_dir,
        "transform": transform,
        "crs": crs,
        "profile": profile_10m,
    }


def test_compute_ndwi_basic_math():
    """Test standard NDWI formula and bounds."""
    green = np.array([0.20, 0.10, 0.05, 0.0], dtype=np.float32)
    nir = np.array([0.05, 0.30, 0.05, 0.0], dtype=np.float32)

    ndwi = compute_ndwi(green, nir)
    # (0.20-0.05)/(0.20+0.05) = 0.15/0.25 = 0.60
    assert pytest.approx(ndwi[0], 0.01) == 0.60
    # (0.10-0.30)/(0.10+0.30) = -0.20/0.40 = -0.50
    assert pytest.approx(ndwi[1], 0.01) == -0.50
    # (0.05-0.05)/(0.05+0.05) = 0.0
    assert pytest.approx(ndwi[2], 0.01) == 0.0
    # 0/0 -> NaN
    assert np.isnan(ndwi[3])


def test_scl_quality_and_cloud_masking():
    """Verify that cloud shadows (3), clouds (8, 9), cirrus (10), saturated (1), and nodata (0) are masked."""
    scl = np.array([[0, 1, 2, 3],
                    [4, 5, 6, 7],
                    [8, 9, 10, 11]], dtype=np.uint8)

    # Conservative policy masks {0, 1, 2, 3, 7, 8, 9, 10, 11}; only 4, 5, 6 are valid
    mask_cons = extract_scl_mask(scl, shape=(3, 4), policy="conservative")
    assert not mask_cons[0, 0]  # 0 NoData
    assert not mask_cons[0, 1]  # 1 Saturated
    assert not mask_cons[0, 2]  # 2 Cast Shadow / Dark area (masked in conservative!)
    assert not mask_cons[0, 3]  # 3 Cloud Shadow
    assert mask_cons[1, 0]      # 4 Vegetation
    assert mask_cons[1, 1]      # 5 Bare soil
    assert mask_cons[1, 2]      # 6 Water
    assert not mask_cons[1, 3]  # 7 Unclassified (masked in conservative!)
    assert not mask_cons[2, 0]  # 8 Cloud medium
    assert not mask_cons[2, 1]  # 9 Cloud high
    assert not mask_cons[2, 2]  # 10 Cirrus
    assert not mask_cons[2, 3]  # 11 Snow/ice


def test_scl_classes_2_and_7_conservative_quality_policy():
    """Documented regression test for SCL Class 2 (cast shadow) and Class 7 (unclassified).

    Class 2: Topographic shadows have near-zero NIR, artificially spiking NDWI > 0.
             Under conservative policy, Class 2 MUST be masked as unobserved.
    Class 7: Ambiguous classification from Sen2Cor (cloud edges, haze, mixed pixels).
             Cannot be certified as clear dry land or water; must be masked as unobserved.
    """
    # Create scenario: pixel with shadow (SCL=2) where low NIR creates false NDWI = 0.50
    scl_shadow = np.array([2], dtype=np.uint8)
    refl_g = np.array([0.06], dtype=np.float32)
    refl_n = np.array([0.02], dtype=np.float32)
    ndwi = compute_ndwi(refl_g, refl_n)  # (0.06-0.02)/(0.06+0.02) = +0.50 (looks like water!)

    # Under permissive policy: SCL=2 is accepted -> false positive water
    val_perm = extract_scl_mask(scl_shadow, shape=(1,), policy="permissive")
    assert val_perm[0] is True or val_perm[0] == True

    # Under conservative policy: SCL=2 is masked -> correctly excluded from clear observation
    val_cons = extract_scl_mask(scl_shadow, shape=(1,), policy="conservative")
    assert val_cons[0] is False or val_cons[0] == False

    # Similarly for Class 7 (unclassified)
    scl_unclass = np.array([7], dtype=np.uint8)
    val_unclass_perm = extract_scl_mask(scl_unclass, shape=(1,), policy="permissive")
    val_unclass_cons = extract_scl_mask(scl_unclass, shape=(1,), policy="conservative")
    assert val_unclass_perm[0] is True or val_unclass_perm[0] == True
    assert val_unclass_cons[0] is False or val_unclass_cons[0] == False


def test_sentinel2_processing_baseline_and_reflectance_scaling():
    """Verify conversion of DN to reflectance for PB < 04.00 (offset=0) vs PB >= 04.00 (offset=-1000)."""
    raw_dn = np.array([0, 1000, 2000, 5000], dtype=np.uint16)

    # 1. Processing Baseline < 04.00 (e.g. PB 02.12): offset = 0.0
    refl_legacy = dn_to_reflectance(raw_dn, scale_factor=10000.0, boa_offset=0.0)
    assert np.isnan(refl_legacy[0])  # DN 0 is NoData
    assert pytest.approx(refl_legacy[1], 1e-4) == 0.1000
    assert pytest.approx(refl_legacy[2], 1e-4) == 0.2000
    assert pytest.approx(refl_legacy[3], 1e-4) == 0.5000

    # 2. Processing Baseline >= 04.00: offset = -1000.0
    refl_harmonized = dn_to_reflectance(raw_dn, scale_factor=10000.0, boa_offset=-1000.0)
    assert np.isnan(refl_harmonized[0])  # DN 0 is NoData
    assert pytest.approx(refl_harmonized[1], 1e-4) == 0.0000  # (1000 - 1000) / 10000
    assert pytest.approx(refl_harmonized[2], 1e-4) == 0.1000  # (2000 - 1000) / 10000
    assert pytest.approx(refl_harmonized[3], 1e-4) == 0.4000  # (5000 - 1000) / 10000


def test_classify_flood_dynamics_isolates_persistent_from_new_flood():
    """Verify that persistent water is cleanly isolated from newly inundated floodwater."""
    # 4 pixels:
    # 0: Pre land (-0.5), Post land (-0.5) -> Dry land (0)
    # 1: Pre water (+0.6), Post water (+0.6) -> Persistent water (2)
    # 2: Pre land (-0.5), Post water (+0.5) -> New flood (1)
    # 3: Pre cloud (valid=False), Post water (+0.5) -> Unobserved (255)
    ndwi_pre = np.array([-0.5, 0.6, -0.5, 0.0], dtype=np.float32)
    ndwi_post = np.array([-0.5, 0.6, 0.5, 0.5], dtype=np.float32)
    valid_pre = np.array([True, True, True, False])
    valid_post = np.array([True, True, True, True])

    mask, stats = classify_flood_dynamics(ndwi_pre, ndwi_post, valid_pre, valid_post, threshold=0.0)

    assert mask[0] == 0    # Dry land
    assert mask[1] == 2    # Persistent water
    assert mask[2] == 1    # New flood
    assert mask[3] == 255  # Unobserved / cloud-masked in baseline

    assert stats["new_flood_pixels"] == 1
    assert stats["persistent_water_pixels"] == 1
    assert stats["dry_land_pixels"] == 1
    assert stats["unobserved_pixels"] == 1


def test_missing_baseline_rejection(db_session: Session, synthetic_optical_fixtures):
    """Reject optical NDWI new-flood processing on raw band directory when baseline is omitted."""
    post_dir = synthetic_optical_fixtures["post_dir"]

    # Create test event and optical scene pointing to a directory
    event = FloodEvent(
        id=f"event_test_{uuid.uuid4().hex[:8]}",
        name="Test Monsoon Flood",
        region_id="nepal_terai",
        start_at=datetime(2017, 8, 10, tzinfo=timezone.utc),
    )
    target_scene = SatelliteScene(
        id=f"scene_post_{uuid.uuid4().hex[:8]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 15, tzinfo=timezone.utc),
        asset_ref=str(post_dir),
        bbox_geojson={"type": "Polygon", "coordinates": [[[87.0, 26.0], [88.0, 26.0], [88.0, 27.0], [87.0, 27.0], [87.0, 26.0]]]},
    )
    db_session.add_all([event, target_scene])
    db_session.commit()

    # Job without baseline_scene_id
    job_spec = SatelliteJobCreate(
        event_id=event.id,
        scene_id=target_scene.id,
        baseline_scene_id=None,
        method="NDWI",
        threshold=0.0,
    )

    with pytest.raises(FloodLensAPIException) as exc_info:
        validate_satellite_job_parameters(db_session, job_spec)
    assert exc_info.value.code == "MISSING_BASELINE_SCENE"


def test_invalid_crs_mismatch_rejection(tmp_path):
    """Ensure pipeline rejects baseline/target rasters with incompatible CRS."""
    out_dir = tmp_path / "out"
    prof_utm = {
        "driver": "GTiff", "height": 10, "width": 10, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10, 0, 500000, 0, -10, 2900000)
    }
    prof_wgs84 = prof_utm.copy()
    prof_wgs84["crs"] = "EPSG:4326"
    prof_wgs84["transform"] = Affine(0.0001, 0, 87.0, 0, -0.0001, 26.5)

    pre_g = tmp_path / "pre_B03.tif"
    pre_n = tmp_path / "pre_B08.tif"
    post_g = tmp_path / "post_B03.tif"
    post_n = tmp_path / "post_B08.tif"

    with rasterio.open(pre_g, "w", **prof_utm) as dst:
        dst.write(np.ones((10, 10), dtype=np.uint16) * 1000, 1)
    with rasterio.open(pre_n, "w", **prof_utm) as dst:
        dst.write(np.ones((10, 10), dtype=np.uint16) * 3000, 1)
    with rasterio.open(post_g, "w", **prof_wgs84) as dst:
        dst.write(np.ones((10, 10), dtype=np.uint16) * 2000, 1)
    with rasterio.open(post_n, "w", **prof_wgs84) as dst:
        dst.write(np.ones((10, 10), dtype=np.uint16) * 500, 1)

    with pytest.raises(ValueError) as exc:
        process_optical_flood_pair(
            pre_green_path=pre_g, pre_nir_path=pre_n,
            post_green_path=post_g, post_nir_path=post_n,
            out_dir=out_dir,
        )
    assert "CRS mismatch" in str(exc.value)


def test_exact_affine_grid_validation_and_reprojection(tmp_path):
    """Verify exact affine-grid validation within scenes and geospatial reprojection cross-scene."""
    # 1. Intra-scene shifted grid: Post B03 at (500000, 2900000), Post B08 shifted by 50m to (500050, 2900000)
    prof_a = {
        "driver": "GTiff", "height": 20, "width": 20, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 2900000.0),
    }
    prof_b = prof_a.copy()
    prof_b["transform"] = Affine(10.0, 0.0, 500050.0, 0.0, -10.0, 2900000.0)  # 50m shift

    # Intra-scene check with require_identical_grid=True must fail
    with pytest.raises(ValueError) as exc:
        validate_spatial_alignment(prof_a, prof_b, label_a="B03", label_b="B08", require_identical_grid=True)
    assert "Exact grid mismatch" in str(exc.value)

    # 2. 20m SCL raster reprojected onto 10m target grid using nearest-neighbor
    scl_20m_data = np.array([[4, 6], [5, 2]], dtype=np.uint8)  # 2x2 pixels at 20m = 40m x 40m
    scl_20m_transform = Affine(20.0, 0.0, 500000.0, 0.0, -20.0, 2900000.0)
    target_10m_transform = Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 2900000.0)
    target_10m_shape = (4, 4)

    reprojected_scl = reproject_to_target_grid(
        src_data=scl_20m_data,
        src_transform=scl_20m_transform,
        src_crs="EPSG:32645",
        target_shape=target_10m_shape,
        target_transform=target_10m_transform,
        target_crs="EPSG:32645",
        is_categorical=True,
    )
    assert reprojected_scl.shape == (4, 4)
    # Nearest neighbor preserves discrete classes: top-left quadrant is 4, top-right is 6
    assert reprojected_scl[0, 0] == 4
    assert reprojected_scl[0, 3] == 6
    assert reprojected_scl[3, 0] == 5
    assert reprojected_scl[3, 3] == 2


def test_end_to_end_synthetic_optical_pipeline(synthetic_optical_fixtures, tmp_path):
    """Execute complete optical pipeline with synthetic fixtures and verify outputs."""
    out_dir = tmp_path / "optical_out"
    pre_dir = synthetic_optical_fixtures["pre_dir"]
    post_dir = synthetic_optical_fixtures["post_dir"]

    result = process_optical_flood_pair(
        pre_green_path=pre_dir / "pre_flood_B03.tif",
        pre_nir_path=pre_dir / "pre_flood_B08.tif",
        post_green_path=post_dir / "post_flood_B03.tif",
        post_nir_path=post_dir / "post_flood_B08.tif",
        pre_scl_path=pre_dir / "pre_flood_SCL.tif",
        post_scl_path=post_dir / "post_flood_SCL.tif",
        out_dir=out_dir,
        threshold=0.00,
        job_id="test_opt_synthetic",
        scl_policy="conservative",
    )

    stats = result["statistics"]
    assert stats["new_flood_pixels"] > 0
    assert stats["persistent_water_pixels"] > 0
    assert stats["unobserved_pixels"] > 0
    assert stats["dry_land_pixels"] > 0
    assert stats["new_flood_km2"] > 0.0
    assert stats["scl_policy"] == "conservative"

    # Verify GeoTIFF products
    for art_key in ["flood_mask_tif", "pre_ndwi_tif", "post_ndwi_tif"]:
        p = Path(result["artifacts"][art_key])
        assert p.exists()
        with rasterio.open(p) as ds:
            assert ds.crs == synthetic_optical_fixtures["crs"]
            assert ds.shape == (100, 100)

    # Verify GeoJSON polygon artifact
    geojson_path = Path(result["artifacts"]["flood_extent_geojson"])
    assert geojson_path.exists()
    with open(geojson_path, "r", encoding="utf-8") as f:
        fc = json.load(f)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    feat = fc["features"][0]
    assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert feat["properties"]["new_flood_area_km2"] > 0.0


def test_fastapi_and_worker_optical_job_flow(db_session: Session, synthetic_optical_fixtures, tmp_path):
    """Test full FastAPI job queueing, worker claiming, execution, and PostGIS extent persistence.

    Compatible with both SQLite test databases and live PostgreSQL 16 + PostGIS 3.4.
    """
    pre_dir = synthetic_optical_fixtures["pre_dir"]
    post_dir = synthetic_optical_fixtures["post_dir"]

    # 1. Register historical event
    event = FloodEvent(
        id=f"event_koshi_{uuid.uuid4().hex[:6]}",
        name="Koshi Monsoon Flood 2017",
        region_id="nepal_terai",
        start_at=datetime(2017, 8, 10, tzinfo=timezone.utc),
        end_at=datetime(2017, 8, 25, tzinfo=timezone.utc),
    )
    # 2. Register pre and post scenes pointing to synthetic band directories
    pre_scene = SatelliteScene(
        id=f"scene_pre_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 5, tzinfo=timezone.utc),
        asset_ref=str(pre_dir),
        bbox_geojson={"type": "Polygon", "coordinates": [[[87.0, 26.0], [88.0, 26.0], [88.0, 27.0], [87.0, 27.0], [87.0, 26.0]]]},
    )
    post_scene = SatelliteScene(
        id=f"scene_post_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 20, tzinfo=timezone.utc),
        asset_ref=str(post_dir),
        bbox_geojson={"type": "Polygon", "coordinates": [[[87.0, 26.0], [88.0, 26.0], [88.0, 27.0], [87.0, 27.0], [87.0, 26.0]]]},
    )
    db_session.add_all([event, pre_scene, post_scene])
    db_session.commit()

    # 3. Create SatelliteJob specification
    job_spec = SatelliteJobCreate(
        event_id=event.id,
        scene_id=post_scene.id,
        baseline_scene_id=pre_scene.id,
        method="NDWI",
        threshold=0.0,
        parameters={"scl_policy": "conservative"},
    )
    target_s, base_s, _, _ = validate_satellite_job_parameters(db_session, job_spec)
    assert target_s.id == post_scene.id
    assert base_s.id == pre_scene.id

    job_id = f"sat_job_opt_{uuid.uuid4().hex[:6]}"
    job = SatelliteJob(
        id=job_id,
        event_id=event.id,
        scene_id=post_scene.id,
        baseline_scene_id=pre_scene.id,
        method="NDWI",
        threshold=0.0,
        parameters={"scl_policy": "conservative"},
        status="QUEUED",
        requested_by="qa_lead@floodlens.org",
    )
    db_session.add(job)
    db_session.commit()

    # 4. Worker claims job
    claimed = claim_job(db_session, job_id=job.id, worker_id="test-worker-optical", lease_seconds=120)
    assert claimed is not None
    assert claimed.status == "RUNNING"
    assert claimed.worker_id == "test-worker-optical"

    # 5. Worker executes job
    success = execute_job(claimed, db_session, worker_id="test-worker-optical")
    assert success is True

    # 6. Verify job status and PostGIS persistence
    db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.progress_percent == 100.0
    assert job.output_extent_id is not None
    assert job.provenance in ("SYNTHETIC_TEST_FIXTURE", "PROCESSED_OPTICAL")

    extent = db_session.query(FloodExtent).filter(FloodExtent.id == job.output_extent_id).first()
    assert extent is not None
    assert extent.event_id == event.id
    assert extent.method == "NDWI"
    assert extent.area_km2 > 0.0
    assert extent.geometry is not None
    assert extent.confidence is None  # No fabricated confidence
    assert len(extent.source_scene_ids) == 2


def test_historical_koshi_scene_manifest_audit():
    """Verify that committed scene_manifest.json documents genuine Sentinel-2 Level-2A imagery."""
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "data" / "historical_koshi_optical" / "scene_manifest.json"
    assert manifest_path.exists(), "scene_manifest.json must be committed in the repository"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Verify event and radiometric calibration metadata
    assert manifest["event"]["name"] == "August 2017 Nepal Terai Monsoon Flooding"
    assert manifest["radiometric_calibration"]["processing_baseline"] == "02.12"
    assert manifest["radiometric_calibration"]["quantification_value"] == 10000.0
    assert manifest["radiometric_calibration"]["boa_add_offset"] == 0.0

    pre_files = manifest["scenes"]["pre_flood"]["files"]
    post_files = manifest["scenes"]["post_flood"]["files"]

    for b in ["B03", "B08", "SCL"]:
        assert b in pre_files
        assert b in post_files
        assert len(pre_files[b]["sha256"]) == 64
        assert len(post_files[b]["sha256"]) == 64
        assert pre_files[b]["size_bytes"] > 100000
        assert post_files[b]["size_bytes"] > 100000


def test_empirical_historical_koshi_raster_pipeline():
    """Execute pipeline on actual local GeoTIFF assets if present; skip with clear message if not.

    In CI environments (where large .tif files are excluded by .gitignore), this test is
    explicitly labeled NOT EXECUTED. When run locally with downloaded assets, it executes
    the full empirical pipeline and verifies exact scientific numbers.
    """
    repo_root = Path(__file__).resolve().parents[2]
    pre_g = repo_root / "data" / "historical_koshi_optical" / "pre_flood" / "pre_flood_B03.tif"
    pre_n = repo_root / "data" / "historical_koshi_optical" / "pre_flood" / "pre_flood_B08.tif"
    pre_s = repo_root / "data" / "historical_koshi_optical" / "pre_flood" / "pre_flood_SCL.tif"
    post_g = repo_root / "data" / "historical_koshi_optical" / "post_flood" / "post_flood_B03.tif"
    post_n = repo_root / "data" / "historical_koshi_optical" / "post_flood" / "post_flood_B08.tif"
    post_s = repo_root / "data" / "historical_koshi_optical" / "post_flood" / "post_flood_SCL.tif"

    if not (pre_g.exists() and pre_n.exists() and post_g.exists() and post_n.exists()):
        pytest.skip(
            "NOT EXECUTED: Local historical GeoTIFF raster assets not available in CI environment "
            "(manifest audit verified separately in test_historical_koshi_scene_manifest_audit)."
        )

    out_dir = repo_root / "data" / "historical_koshi_optical" / "outputs"
    res = process_optical_flood_pair(
        pre_green_path=pre_g,
        pre_nir_path=pre_n,
        post_green_path=post_g,
        post_nir_path=post_n,
        pre_scl_path=pre_s if pre_s.exists() else None,
        post_scl_path=post_s if post_s.exists() else None,
        out_dir=out_dir,
        threshold=0.00,
        job_id="historical_koshi_ndwi",
        scl_policy="conservative",
        boa_offset=0.0,
    )

    stats = res["statistics"]
    # Verified exact numbers under conservative SCL policy
    assert stats["scl_policy"] == "conservative"
    assert stats["valid_shared_pixels"] == 1234008
    assert pytest.approx(stats["valid_shared_km2"], 0.01) == 123.4008
    assert stats["new_flood_pixels"] == 6429
    assert pytest.approx(stats["new_flood_km2"], 0.001) == 0.6429
    assert stats["persistent_water_pixels"] == 292
    assert pytest.approx(stats["persistent_water_km2"], 0.001) == 0.0292
    assert stats["dry_land_pixels"] == 1227287
    assert stats["unobserved_pixels"] == 2765992


def test_same_dimensions_different_geospatial_transforms_rejection():
    """Reject comparing two rasters that have identical pixel dimensions but represent different ground locations."""
    # Both 50x50, but A is in Sunsari (x=500000, y=2900000) and B is in Jhapa (x=580000, y=2900000) - 80 km offset!
    prof_a = {
        "driver": "GTiff", "height": 50, "width": 50, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 2900000.0),
    }
    prof_b = {
        "driver": "GTiff", "height": 50, "width": 50, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 580000.0, 0.0, -10.0, 2900000.0),  # 80 km offset (disjoint)
    }

    with pytest.raises(ValueError) as exc_info:
        validate_spatial_alignment(prof_a, prof_b, label_a="Scene A", label_b="Scene B")
    assert "do not spatially intersect" in str(exc_info.value)


def test_nodata_and_zero_reflectance_handling():
    """Ensure pixels with 0 or negative reflectance or NaN are treated as NoData (never dry land)."""
    green = np.array([0, -100, 1500, np.nan], dtype=np.float32)
    nir = np.array([0, 2000, -50, 1000], dtype=np.float32)

    ndwi = compute_ndwi(green, nir)
    # All invalid/zero/negative values must result in NaN
    assert np.isnan(ndwi[0])
    assert np.isnan(ndwi[1])
    assert np.isnan(ndwi[2])
    assert np.isnan(ndwi[3])


def test_missing_shared_coverage_marked_as_unobserved():
    """Where cloud or missing observations prevent comparison, pixels must be marked 255 (unobserved)."""
    # 3 pixels:
    # 0: Pre cloudy (valid_pre=False), Post clear water (valid_post=True) -> must be 255
    # 1: Pre clear land (valid_pre=True), Post shadow (valid_post=False) -> must be 255
    # 2: Both clear: Pre dry, Post water -> must be 1 (new flood)
    ndwi_pre = np.array([np.nan, -0.4, -0.5])
    ndwi_post = np.array([0.5, np.nan, 0.5])
    valid_pre = np.array([False, True, True])
    valid_post = np.array([True, False, True])

    mask, stats = classify_flood_dynamics(ndwi_pre, ndwi_post, valid_pre, valid_post, threshold=0.0)
    assert mask[0] == 255
    assert mask[1] == 255
    assert mask[2] == 1
    assert stats["unobserved_pixels"] == 2
    assert stats["new_flood_pixels"] == 1


def test_truthful_provenance_tagging(db_session: Session, synthetic_optical_fixtures, tmp_path):
    """Verify that provenance distinguishes PROCESSED_OPTICAL from IMPORTED_PRECOMPUTED and SYNTHETIC."""
    # 1. Band directory with baseline -> PROCESSED_OPTICAL or SYNTHETIC_TEST_FIXTURE
    out_dir = tmp_path / "prov_test"
    real_like_dir = tmp_path / "data" / "optical_real_sim"
    real_like_pre = real_like_dir / "pre"
    real_like_post = real_like_dir / "post"
    real_like_pre.mkdir(parents=True)
    real_like_post.mkdir(parents=True)
    for f in synthetic_optical_fixtures["pre_dir"].glob("*.tif"):
        shutil.copy(f, real_like_pre / f.name)
    for f in synthetic_optical_fixtures["post_dir"].glob("*.tif"):
        shutil.copy(f, real_like_post / f.name)

    geom, area, prov, poly_ref, raster_ref = _process_optical_bands(
        scene_dir_or_file=real_like_post,
        baseline_path=real_like_pre,
        threshold=0.0,
        job_id="prov_test_job",
    )
    assert prov == "PROCESSED_OPTICAL"
    assert area > 0.0

    # 2. Synthetic fixture directory -> SYNTHETIC_TEST_FIXTURE
    geom_syn, area_syn, prov_syn, _, _ = _process_optical_bands(
        scene_dir_or_file=synthetic_optical_fixtures["post_dir"],
        baseline_path=synthetic_optical_fixtures["pre_dir"],
        threshold=0.0,
        job_id="syn_test_job",
    )
    assert prov_syn == "SYNTHETIC_TEST_FIXTURE"


# ==============================================================================
# Mandatory Regression Tests (4 Independent Source Review Edge Cases)
# ==============================================================================

def test_half_pixel_origin_shift_at_real_utm_coordinates():
    """Verify that a 5m half-pixel shift in real UTM coordinates is NOT treated as equal.

    np.isclose with default rtol=1e-5 incorrectly returned True for:
      np.isclose(584980, 584985, atol=1e-5) -> True!
      np.isclose(2925000, 2925005, atol=1e-5) -> True!
    affine_transforms_equal with strict atol and zero rtol must return False.
    reproject_to_target_grid must reproject the array rather than returning it unchanged.
    """
    trans_a = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)
    trans_half = Affine(10.0, 0.0, 584985.0, 0.0, -10.0, 2925005.0)

    # Verify standard np.isclose defect exists if relative tolerance is enabled
    assert bool(np.isclose(584980.0, 584985.0, atol=1e-5)) is True
    assert bool(np.isclose(2925000.0, 2925005.0, atol=1e-5)) is True

    # Strict geospatial check correctly rejects half-pixel displacement
    assert affine_transforms_equal(trans_a, trans_half, atol=1e-3) is False

    # Verify reproject_to_target_grid reprojects rather than taking fast path
    arr = np.array([[1000.0, 2000.0], [1000.0, 2000.0]], dtype=np.float32)
    reprojected = reproject_to_target_grid(
        src_data=arr,
        src_transform=trans_half,
        src_crs="EPSG:32645",
        target_shape=(2, 2),
        target_transform=trans_a,
        target_crs="EPSG:32645",
        is_categorical=False,
    )
    # The half-pixel shift MUST produce interpolated values, not an unchanged copy of arr
    assert not np.array_equal(arr, reprojected)


def test_one_pixel_origin_shift_at_real_utm_coordinates():
    """Verify that a 10m one-pixel shift in UTM coordinates is rejected by fast path."""
    trans_a = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)
    trans_one = Affine(10.0, 0.0, 584990.0, 0.0, -10.0, 2925000.0)

    assert affine_transforms_equal(trans_a, trans_one, atol=1e-3) is False


def test_identical_grid_fast_path():
    """Verify that identical affine transforms, CRS and shapes take the fast path."""
    trans = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)
    assert affine_transforms_equal(trans, trans, atol=1e-3) is True

    arr = np.array([[100.0, 200.0], [300.0, 400.0]], dtype=np.float32)
    res = reproject_to_target_grid(
        src_data=arr,
        src_transform=trans,
        src_crs="EPSG:32645",
        target_shape=(2, 2),
        target_transform=trans,
        target_crs="EPSG:32645",
        is_categorical=False,
    )
    np.testing.assert_array_equal(arr, res)


def test_reprojection_uint16_reflectance_with_destination_nan():
    """Verify that raw uint16 arrays with dst_nodata=np.nan do not crash and produce float32 with NaNs."""
    trans_src = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)
    trans_dst = Affine(10.0, 0.0, 584985.0, 0.0, -10.0, 2925000.0)

    src_uint16 = np.array([[1500, 2500], [0, 3000]], dtype=np.uint16)

    out = reproject_to_target_grid(
        src_data=src_uint16,
        src_transform=trans_src,
        src_crs="EPSG:32645",
        target_shape=(2, 2),
        target_transform=trans_dst,
        target_crs="EPSG:32645",
        is_categorical=False,
        src_nodata=0,
        dst_nodata=np.nan,
    )
    assert out.dtype == np.float32
    assert np.issubdtype(out.dtype, np.floating)


def test_bilinear_interpolation_near_source_nodata_boundary():
    """Verify that bilinear resampling near NoData boundaries does not bleed invalid/zero pixels into valid reflectance."""
    trans_src = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)
    trans_dst = Affine(10.0, 0.0, 584985.0, 0.0, -10.0, 2925000.0)

    src_refl = np.full((4, 4), np.nan, dtype=np.float32)
    src_refl[:, 0:2] = 0.25

    dst = reproject_to_target_grid(
        src_data=src_refl,
        src_transform=trans_src,
        src_crs="EPSG:32645",
        target_shape=(4, 4),
        target_transform=trans_dst,
        target_crs="EPSG:32645",
        is_categorical=False,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    assert dst.dtype == np.float32
    valid_mask = ~np.isnan(dst[:, 0])
    if np.any(valid_mask):
        assert np.all(dst[valid_mask, 0] > 0.20)


def test_categorical_scl_nearest_neighbor_correctness():
    """Verify categorical SCL reprojection preserves integer dtype and distinct classes."""
    trans_src = Affine(20.0, 0.0, 584980.0, 0.0, -20.0, 2925000.0)
    trans_dst = Affine(10.0, 0.0, 584980.0, 0.0, -10.0, 2925000.0)

    scl_src = np.array([[2, 4], [6, 9]], dtype=np.uint8)

    scl_dst = reproject_to_target_grid(
        src_data=scl_src,
        src_transform=trans_src,
        src_crs="EPSG:32645",
        target_shape=(4, 4),
        target_transform=trans_dst,
        target_crs="EPSG:32645",
        is_categorical=True,
        src_nodata=0,
        dst_nodata=0,
    )
    assert scl_dst.dtype == np.uint8
    unique_vals = set(np.unique(scl_dst))
    assert unique_vals.issubset({0, 2, 4, 6, 9})


def test_differing_scl_policies_produce_distinct_flood_extents():
    """Verify differing SCL policies produce distinct extent IDs."""
    id_cons = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"scl_policy": "conservative"},
    )
    id_perm = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"scl_policy": "permissive"},
    )
    assert id_cons != id_perm
    assert id_cons.startswith("ext_evt_test_scene_post_NDWI_")
    assert id_perm.startswith("ext_evt_test_scene_post_NDWI_")


def test_differing_radiometric_offsets_produce_distinct_extents():
    """Verify differing radiometric baseline offsets produce distinct extent IDs."""
    id_pb02 = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"boa_offset": 0.0},
    )
    id_pb04 = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"boa_offset": -1000.0},
    )
    assert id_pb02 != id_pb04


def test_identical_configurations_remain_idempotent():
    """Verify identical parameters and inputs produce the exact same deterministic extent ID."""
    id1 = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"scl_policy": "conservative", "boa_offset": 0.0, "scale_factor": 10000.0},
    )
    id2 = compute_extent_identity(
        event_id="evt_test",
        scene_id="scene_post",
        baseline_scene_id="scene_pre",
        method="NDWI",
        threshold=0.0,
        artifact_checksum="abc123hash",
        parameters={"scl_policy": "conservative", "boa_offset": 0.0, "scale_factor": 10000.0},
    )
    assert id1 == id2


def test_differently_configured_jobs_can_coexist(client: TestClient, authority_token: str, db_session: Session, synthetic_optical_fixtures):
    """Verify that jobs with different processing parameters are not blocked by duplicate active job detection."""
    event = FloodEvent(
        id=f"evt_coexist_{uuid.uuid4().hex[:6]}",
        name="Coexistence Test Event",
        region_id="Koshi",
        start_at=datetime(2017, 8, 1, tzinfo=timezone.utc),
        end_at=datetime(2017, 8, 25, tzinfo=timezone.utc),
    )
    pre_scene = SatelliteScene(
        id=f"scene_pre_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 5, tzinfo=timezone.utc),
        asset_ref=str(synthetic_optical_fixtures["pre_dir"]),
    )
    post_scene = SatelliteScene(
        id=f"scene_post_{uuid.uuid4().hex[:6]}",
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 20, tzinfo=timezone.utc),
        asset_ref=str(synthetic_optical_fixtures["post_dir"]),
    )
    db_session.add_all([event, pre_scene, post_scene])
    db_session.commit()

    # Seed an active (RUNNING) satellite job with conservative SCL policy
    active_job = SatelliteJob(
        id=f"sat_job_active_{uuid.uuid4().hex[:6]}",
        event_id=event.id,
        scene_id=post_scene.id,
        baseline_scene_id=pre_scene.id,
        method="NDWI",
        threshold=0.0,
        status="RUNNING",
        progress_percent=45.0,
        requested_by="qa@floodlens.org",
        parameters={
            "threshold": 0.0,
            "scene_id": post_scene.id,
            "baseline_scene_id": pre_scene.id,
            "method": "NDWI",
            "event_id": event.id,
            "scl_policy": "conservative",
            "boa_offset": 0.0,
            "scale_factor": 10000.0,
            "allow_single_scene": False,
        },
    )
    db_session.add(active_job)
    db_session.commit()

    # 1. Submit exact same configuration while active_job is RUNNING
    # Duplicate detection MUST match active_job and return it idempotently!
    res_dup = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": event.id,
            "scene_id": post_scene.id,
            "baseline_scene_id": pre_scene.id,
            "method": "NDWI",
            "threshold": 0.0,
            "parameters": {"scl_policy": "conservative"},
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_dup.status_code == 202
    assert res_dup.json()["job_id"] == active_job.id
    assert "already in progress" in res_dup.json()["message"]

    # 2. Submit differently configured job with permissive SCL policy
    # Duplicate detection MUST NOT mistake it for identical job; creates NEW job!
    res_diff_scl = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": event.id,
            "scene_id": post_scene.id,
            "baseline_scene_id": pre_scene.id,
            "method": "NDWI",
            "threshold": 0.0,
            "parameters": {"scl_policy": "permissive"},
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_diff_scl.status_code == 202
    job_diff_id = res_diff_scl.json()["job_id"]
    assert job_diff_id != active_job.id

    # 3. Submit differently configured job with different radiometric offset
    res_diff_offset = client.post(
        "/api/v1/satellite/jobs",
        json={
            "event_id": event.id,
            "scene_id": post_scene.id,
            "baseline_scene_id": pre_scene.id,
            "method": "NDWI",
            "threshold": 0.0,
            "parameters": {"scl_policy": "conservative", "boa_offset": -1000.0},
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res_diff_offset.status_code == 202
    job_offset_id = res_diff_offset.json()["job_id"]
    assert job_offset_id != active_job.id
    assert job_offset_id != job_diff_id


def test_modified_raster_contents_with_unchanged_file_sizes_change_checksums(tmp_path):
    """Verify that streaming content hashing detects pixel changes even when file sizes and filenames are identical."""
    dir_path = tmp_path / "raster_hash_test"
    dir_path.mkdir()
    raster_file = dir_path / "band.tif"

    profile = {
        "driver": "GTiff", "height": 10, "width": 10, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 580000.0, 0.0, -10.0, 2920000.0),
    }

    data_v1 = np.full((10, 10), 1000, dtype=np.uint16)
    with rasterio.open(raster_file, "w", **profile) as dst:
        dst.write(data_v1, 1)

    size_v1 = raster_file.stat().st_size
    checksum_v1 = compute_artifact_checksum(dir_path)

    # Version 2: change one pixel from 1000 to 2000 (same uncompressed byte size)
    data_v2 = data_v1.copy()
    data_v2[5, 5] = 2000
    with rasterio.open(raster_file, "w", **profile) as dst:
        dst.write(data_v2, 1)

    size_v2 = raster_file.stat().st_size
    checksum_v2 = compute_artifact_checksum(dir_path)

    assert size_v1 == size_v2
    assert checksum_v1 != checksum_v2
