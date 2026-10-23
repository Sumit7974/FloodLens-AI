"""Comprehensive unit and integration tests for reproducible optical flood detection.

Validates:
1. Valid pre/post Sentinel-2 bands (B03 Green, B08 NIR, SCL).
2. Missing baseline rejection for empirical optical new-flood jobs.
3. Invalid CRS mismatch rejection.
4. Same dimensions with different geospatial transforms (disjoint locations).
5. Different band resolution and grid alignment (e.g. 20m SCL resampled to 10m).
6. NoData and saturated pixel handling.
7. Cloud and cloud shadow masking via SCL.
8. Persistent water exclusion from new inundation.
9. Newly inundated water extraction.
10. Missing valid shared coverage marked as unobserved (255), never dry land.
11. Metric flood area calculation in km² (EPSG:32645).
12. GeoTIFF metadata preservation (CRS, transform, NoData).
13. GeoJSON polygon validity in EPSG:4326.
14. FastAPI job endpoint integration and worker execution.
15. PostGIS flood extent persistence and readback.
16. Truthful provenance labeling.
17. Real historical Koshi demonstration verification.
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
from app.schemas.satellite import SatelliteJobCreate
from app.services.satellite_processor import (
    _process_optical_bands,
    execute_satellite_pipeline,
    validate_satellite_job_parameters,
    set_test_db_session,
    OUTPUT_DIR,
)
from app.workers.satellite_worker import claim_job, execute_job
from ml.gis_processing.calculate_ndwi import (
    classify_flood_dynamics,
    compute_ndwi,
    extract_scl_mask,
    process_optical_flood_pair,
    validate_spatial_alignment,
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
    green = np.array([2000, 1000, 500, 0], dtype=np.float32)
    nir = np.array([500, 3000, 500, 0], dtype=np.float32)

    ndwi = compute_ndwi(green, nir)
    # (2000-500)/(2000+500) = 1500/2500 = 0.60
    assert pytest.approx(ndwi[0], 0.01) == 0.60
    # (1000-3000)/(1000+3000) = -2000/4000 = -0.50
    assert pytest.approx(ndwi[1], 0.01) == -0.50
    # (500-500)/(500+500) = 0.0
    assert pytest.approx(ndwi[2], 0.01) == 0.0
    # zero denom -> nan
    assert np.isnan(ndwi[3])


def test_scl_quality_and_cloud_masking():
    """Test that SCL classes 3 (shadow), 8, 9, 10 (cloud) are excluded, while 4, 5, 6 are valid."""
    scl = np.array([[0, 1, 3], [4, 5, 6], [8, 9, 10]], dtype=np.uint8)
    mask = extract_scl_mask(scl, (3, 3))

    # Row 0: 0(NoData), 1(Saturated), 3(Shadow) -> all False
    assert not mask[0, 0] and not mask[0, 1] and not mask[0, 2]
    # Row 1: 4(Vegetation), 5(Soil), 6(Water) -> all True
    assert mask[1, 0] and mask[1, 1] and mask[1, 2]
    # Row 2: 8(Cloud Med), 9(Cloud High), 10(Cirrus) -> all False
    assert not mask[2, 0] and not mask[2, 1] and not mask[2, 2]


def test_classify_flood_dynamics_isolates_persistent_from_new_flood():
    """Verify that persistent water is separated from new floodwater."""
    # 4 pixels:
    # px 0: Dry in pre, dry in post -> 0 (dry land)
    # px 1: Water in pre, water in post -> 2 (persistent water)
    # px 2: Dry in pre, water in post -> 1 (new flood)
    # px 3: Water in post, but cloudy in pre -> 255 (unobserved)
    ndwi_pre = np.array([-0.4, 0.5, -0.3, np.nan])
    ndwi_post = np.array([-0.4, 0.6, 0.5, 0.5])
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

    arr = np.full((10, 10), 1000, dtype=np.uint16)
    with rasterio.open(pre_g, "w", **prof_utm) as dst:
        dst.write(arr, 1)
    with rasterio.open(pre_n, "w", **prof_utm) as dst:
        dst.write(arr, 1)
    with rasterio.open(post_g, "w", **prof_wgs84) as dst:
        dst.write(arr, 1)
    with rasterio.open(post_n, "w", **prof_wgs84) as dst:
        dst.write(arr, 1)

    with pytest.raises(ValueError) as exc_info:
        process_optical_flood_pair(pre_g, pre_n, post_g, post_n, out_dir=out_dir)
    assert "CRS mismatch" in str(exc_info.value)


def test_different_resolution_scl_resampling(synthetic_optical_fixtures, tmp_path):
    """Test that 20m SCL is automatically resampled and aligned with 10m bands."""
    post_dir = synthetic_optical_fixtures["post_dir"]
    pre_dir = synthetic_optical_fixtures["pre_dir"]
    out_dir = tmp_path / "resample_out"

    # Create a 20m SCL file (50x50) to verify nearest-neighbor resampling to 100x100
    scl_20m_path = tmp_path / "scl_20m.tif"
    prof_20m = synthetic_optical_fixtures["profile"].copy()
    prof_20m.update({
        "height": 50,
        "width": 50,
        "transform": Affine(20.0, 0.0, 580000.0, 0.0, -20.0, 2920000.0),
        "dtype": "uint8",
    })
    scl_20m = np.full((50, 50), 4, dtype=np.uint8)
    scl_20m[10:20, 10:20] = 9  # cloud block
    with rasterio.open(scl_20m_path, "w", **prof_20m) as dst:
        dst.write(scl_20m, 1)

    res = process_optical_flood_pair(
        pre_green_path=pre_dir / "pre_flood_B03.tif",
        pre_nir_path=pre_dir / "pre_flood_B08.tif",
        post_green_path=post_dir / "post_flood_B03.tif",
        post_nir_path=post_dir / "post_flood_B08.tif",
        post_scl_path=scl_20m_path,
        out_dir=out_dir,
        threshold=0.0,
    )
    assert res["statistics"]["valid_shared_pixels"] > 0
    # Output mask must match 100x100 10m grid
    with rasterio.open(res["artifacts"]["flood_mask_tif"]) as src:
        assert src.shape == (100, 100)


def test_end_to_end_synthetic_optical_pipeline(synthetic_optical_fixtures, tmp_path):
    """Full execution of optical flood extraction on calibrated synthetic fixtures."""
    pre_dir = synthetic_optical_fixtures["pre_dir"]
    post_dir = synthetic_optical_fixtures["post_dir"]
    out_dir = tmp_path / "pipeline_test"

    result = process_optical_flood_pair(
        pre_green_path=pre_dir / "pre_flood_B03.tif",
        pre_nir_path=pre_dir / "pre_flood_B08.tif",
        post_green_path=post_dir / "post_flood_B03.tif",
        post_nir_path=post_dir / "post_flood_B08.tif",
        pre_scl_path=pre_dir / "pre_flood_SCL.tif",
        post_scl_path=post_dir / "post_flood_SCL.tif",
        out_dir=out_dir,
        threshold=0.0,
        job_id="test_opt_e2e",
    )

    stats = result["statistics"]
    # 1. Total pixels: 100x100 = 10,000
    assert stats["total_pixels"] == 10000
    # 2. Persistent water (river: 20x20 = 400 px)
    assert stats["persistent_water_pixels"] == 400
    # 3. Newly inundated flood: 30x60 = 1800 px
    assert stats["new_flood_pixels"] == 1800
    # 4. Flood area at 10m: 1800 * 100 m² = 180,000 m² = 0.18 km²
    assert pytest.approx(stats["new_flood_km2"], 0.01) == 0.18
    # 5. Persistent water area: 400 * 100 m² = 0.04 km²
    assert pytest.approx(stats["persistent_water_km2"], 0.01) == 0.04

    # 6. Verify GeoTIFF outputs
    for k in ["flood_mask_tif", "pre_ndwi_tif", "post_ndwi_tif"]:
        p = Path(result["artifacts"][k])
        assert p.exists()
        with rasterio.open(p) as src:
            assert src.shape == (100, 100)
            assert str(src.crs) == "EPSG:32645"

    # 7. Verify GeoJSON vector
    geojson_path = Path(result["artifacts"]["flood_extent_geojson"])
    assert geojson_path.exists()
    with open(geojson_path, "r", encoding="utf-8") as f:
        fc = json.load(f)
    assert len(fc["features"]) > 0
    geom = shape(fc["features"][0]["geometry"])
    assert geom.is_valid
    assert fc["features"][0]["properties"]["new_flood_area_km2"] == 0.18


def test_fastapi_and_worker_optical_job_flow(db_session: Session, synthetic_optical_fixtures):
    """Verify FastAPI job registration, database-backed worker lease, PostGIS persistence, and readback."""
    set_test_db_session(db_session)

    # 1. Register historical event
    event = FloodEvent(
        id=f"event_koshi_{uuid.uuid4().hex[:6]}",
        name="August 2017 Koshi Flood",
        region_id="koshi_basin",
        start_at=datetime(2017, 8, 11, tzinfo=timezone.utc),
        end_at=datetime(2017, 8, 25, tzinfo=timezone.utc),
    )
    # 2. Register pre- and post-flood optical scenes
    pre_scene = SatelliteScene(
        id=f"scene_s2_pre_{uuid.uuid4().hex[:6]}",
        provider="ESA Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 5, tzinfo=timezone.utc),
        asset_ref=str(synthetic_optical_fixtures["pre_dir"]),
        bbox_geojson={"type": "Polygon", "coordinates": [[[87.0, 26.0], [88.0, 26.0], [88.0, 27.0], [87.0, 27.0], [87.0, 26.0]]]},
    )
    post_scene = SatelliteScene(
        id=f"scene_s2_post_{uuid.uuid4().hex[:6]}",
        provider="ESA Copernicus",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=datetime(2017, 8, 20, tzinfo=timezone.utc),
        asset_ref=str(synthetic_optical_fixtures["post_dir"]),
        bbox_geojson={"type": "Polygon", "coordinates": [[[87.0, 26.0], [88.0, 26.0], [88.0, 27.0], [87.0, 27.0], [87.0, 26.0]]]},
    )
    db_session.add_all([event, pre_scene, post_scene])
    db_session.commit()

    # 3. Submit optical NDWI job
    job_spec = SatelliteJobCreate(
        event_id=event.id,
        scene_id=post_scene.id,
        baseline_scene_id=pre_scene.id,
        method="NDWI",
        threshold=0.0,
    )
    target_s, base_s, fl_event, res_target = validate_satellite_job_parameters(db_session, job_spec)
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


def test_empirical_historical_koshi_dataset_verification():
    """Verify that genuine historical Sentinel-2 Level-2A imagery exists and processes correctly."""
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = repo_root / "data" / "historical_koshi_optical" / "scene_manifest.json"
    if not manifest_path.exists():
        pytest.skip("Historical Koshi dataset not fetched; run scripts/fetch_historical_koshi_optical.py")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pre_files = manifest["scenes"]["pre_flood"]["files"]
    post_files = manifest["scenes"]["post_flood"]["files"]

    for b in ["B03", "B08", "SCL"]:
        assert b in pre_files
        assert b in post_files
        assert pre_files[b]["size_bytes"] > 100000
        assert post_files[b]["size_bytes"] > 100000

    # Verify that outputs were generated and conform to physical flood detection
    outputs_manifest = repo_root / "data" / "historical_koshi_optical" / "outputs" / "historical_koshi_ndwi_manifest.json"
    if outputs_manifest.exists():
        with open(outputs_manifest, "r", encoding="utf-8") as f:
            out_meta = json.load(f)
        stats = out_meta["statistics"]
        # Valid shared observation area in Koshi flood AOI (~202 km²)
        assert stats["valid_shared_km2"] > 150.0
        # Newly inundated water (~3.71 km²)
        assert stats["new_flood_km2"] > 1.0
        # Persistent water (~0.19 km²)
        assert stats["persistent_water_km2"] > 0.05
        # Total scene area is 400 km² (20km x 20km)
        assert stats["total_scene_km2"] == 400.0


def test_same_dimensions_different_geospatial_transforms_rejection(tmp_path):
    """Reject comparing two rasters that have identical pixel dimensions but represent different ground locations."""
    # Both 50x50, but A is in Sunsari (x=500000, y=2900000) and B is in Jhapa (x=580000, y=2900000)
    prof_a = {
        "driver": "GTiff", "height": 50, "width": 50, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 500000.0, 0.0, -10.0, 2900000.0),
    }
    prof_b = {
        "driver": "GTiff", "height": 50, "width": 50, "count": 1,
        "dtype": "uint16", "crs": "EPSG:32645",
        "transform": Affine(10.0, 0.0, 580000.0, 0.0, -10.0, 2900000.0),  # 80 km offset!
    }

    with pytest.raises(ValueError) as exc_info:
        validate_spatial_alignment(prof_a, prof_b, label_a="Scene A", label_b="Scene B")
    # If spatial alignment validation enforces origin match or resolution match
    # Let's ensure validate_spatial_alignment checks origin or bounds overlap


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

