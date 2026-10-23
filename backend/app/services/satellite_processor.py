"""Durable background satellite processing pipeline service for FloodLens AI.

Orchestrates:
1. Scientific domain validation of satellite scenes, temporal & geographic compatibility, and asset references.
2. Removal of all implicit synthetic fixture fallbacks in production.
3. Dedicated optical (Sentinel-2 NDWI) and radar (Sentinel-1 SAR change detection) workflows.
4. Truthful provenance tracking (PROCESSED_OPTICAL, PROCESSED_SAR, IMPORTED_PRECOMPUTED, SYNTHETIC_TEST_FIXTURE).
5. Elimination of fabricated confidence values (confidence=None when uncalibrated).
6. Multi-event and multi-scene extent preservation with input-specific idempotency in PostGIS.
7. Atomic job claiming, worker restart recovery, and controlled retry budgeting.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pyproj
import shapely
import shapely.ops
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.validation import make_valid
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, FloodLensAPIException, NotFoundError
from app.core.spatial import geometry_to_geojson, to_wkt_element
from app.database import SessionLocal
from app.models.enums import EventType
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent, SatelliteJob, SatelliteScene
from app.schemas.event import WebSocketEvent
from app.schemas.satellite import SatelliteJobCreate
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger("floodlens.satellite_processor")

# Approved storage roots to guard against arbitrary path traversal and file access attacks
_REPO_ROOT = Path(__file__).resolve().parents[3]
_APPROVED_ROOTS = [
    _REPO_ROOT / "ml" / "gis_processing" / "downloads",
    _REPO_ROOT / "backend" / "tests" / "fixtures",
    _REPO_ROOT / "backend" / "app" / "storage",
    _REPO_ROOT / "data",
    Path(tempfile.gettempdir()),
]

# Ensure output directory exists for fresh processing outputs
OUTPUT_DIR = _REPO_ROOT / "backend" / "app" / "storage" / "satellite_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Global test session hook for transaction-isolated test environments
_TEST_DB_SESSION: Optional[Session] = None


def set_test_db_session(sess: Optional[Session]) -> None:
    """Register an active test database session so background tasks execute within the test transaction."""
    global _TEST_DB_SESSION
    _TEST_DB_SESSION = sess


def get_worker_db_session() -> Session:
    """Obtain the appropriate database session for worker execution (test session or production SessionLocal)."""
    if _TEST_DB_SESSION is not None:
        return _TEST_DB_SESSION
    return SessionLocal()


def is_safe_path(candidate_path: Union[str, Path]) -> Tuple[bool, Optional[Path]]:
    """Verify that a path does not escape approved directories via directory traversal
    and points to a valid geospatial asset type rather than arbitrary repository code/files."""
    try:
        p = Path(candidate_path)
        raw_str = str(candidate_path)
        if ".." in raw_str:
            return False, None

        if not p.is_absolute():
            resolved = (_REPO_ROOT / p).resolve()
        else:
            resolved = p.resolve()

        in_approved_root = False
        for approved in _APPROVED_ROOTS:
            try:
                resolved.relative_to(approved.resolve())
                in_approved_root = True
                break
            except ValueError:
                continue

        if not in_approved_root:
            try:
                resolved.relative_to(Path(tempfile.gettempdir()).resolve())
                in_approved_root = True
            except ValueError:
                pass

        if not in_approved_root:
            return False, None

        # Guard against selecting non-geospatial repository files (e.g., source code, configs)
        valid_extensions = {".geojson", ".json", ".tif", ".tiff", ".png"}
        if resolved.is_file() and resolved.suffix.lower() not in valid_extensions:
            return False, None

        return True, resolved
    except Exception:
        return False, None


def sanitize_error(exc: Exception) -> str:
    """Strip local filesystem paths and raw tracebacks from public error messages."""
    msg = str(exc)
    for root in _APPROVED_ROOTS:
        msg = msg.replace(str(root), "[STORAGE_ROOT]")
        msg = msg.replace(str(root).replace("\\", "/"), "[STORAGE_ROOT]")
    return msg[:950]


def compute_metric_area_km2(geom_wgs84: Union[Polygon, MultiPolygon]) -> float:
    """Calculate exact projected ground surface area in km² using UTM Zone 45N (EPSG:32645)."""
    if geom_wgs84 is None or geom_wgs84.is_empty:
        return 0.0
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    geom_utm = shapely.ops.transform(transformer.transform, geom_wgs84)
    return round(float(geom_utm.area) / 1e6, 4)


def normalize_to_multipolygon(geom: Any) -> MultiPolygon:
    """Ensure geometry is a valid MultiPolygon in WGS84."""
    if geom is None:
        return MultiPolygon([])
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom]) if not geom.is_empty and geom.area > 0 else MultiPolygon([])
    elif geom.geom_type == "MultiPolygon":
        polys = [p for p in geom.geoms if not p.is_empty and p.area > 0]
        return MultiPolygon(polys)
    elif hasattr(geom, "geoms"):
        flat_polys = []
        for sub_geom in geom.geoms:
            if sub_geom.is_empty:
                continue
            if not sub_geom.is_valid:
                sub_geom = make_valid(sub_geom)
            if sub_geom.geom_type == "Polygon" and sub_geom.area > 0:
                flat_polys.append(sub_geom)
            elif sub_geom.geom_type == "MultiPolygon":
                flat_polys.extend([p for p in sub_geom.geoms if not p.is_empty and p.area > 0])
        return MultiPolygon(flat_polys)
    return MultiPolygon([])


def validate_satellite_job_parameters(
    db: Session,
    job_spec: SatelliteJobCreate,
) -> Tuple[SatelliteScene, Optional[SatelliteScene], FloodEvent, Path]:
    """Validate all job creation requirements and input data integrity.

    Returns:
        (target_scene, baseline_scene, flood_event, resolved_asset_path)
    Raises:
        FloodLensAPIException / NotFoundError on validation failure.
    """
    # 1. Processing method validation
    method = (job_spec.method or "").strip().upper()
    if method == "MNDWI":
        raise FloodLensAPIException(
            status_code=400,
            code="UNSUPPORTED_PROCESSING_METHOD",
            message=(
                "MNDWI processing method is not supported by the current optical pipeline "
                "(SWIR band required). Supported methods: NDWI, SAR_CHANGE."
            ),
            details={"requested_method": job_spec.method, "supported_methods": ["NDWI", "SAR_CHANGE"]},
        )
    if method not in ("NDWI", "SAR_CHANGE"):
        raise FloodLensAPIException(
            status_code=400,
            code="INVALID_PROCESSING_METHOD",
            message=f"Unsupported processing method '{job_spec.method}'. Supported methods: NDWI, SAR_CHANGE.",
            details={"requested_method": job_spec.method, "supported_methods": ["NDWI", "SAR_CHANGE"]},
        )

    # 2. Historical Event Association Validation (Issue 4)
    if not job_spec.event_id or not job_spec.event_id.strip():
        raise FloodLensAPIException(
            status_code=400,
            code="MISSING_EVENT_ID",
            message="An explicit, valid event_id is required to create a satellite processing job.",
        )
    flood_event = db.query(FloodEvent).filter(FloodEvent.id == job_spec.event_id.strip()).first()
    if not flood_event:
        raise NotFoundError(
            message=f"Flood event '{job_spec.event_id}' not found",
            code="EVENT_NOT_FOUND",
        )

    # 3. Target scene existence
    if not job_spec.scene_id or not job_spec.scene_id.strip():
        raise FloodLensAPIException(
            status_code=400,
            code="MISSING_SCENE_ID",
            message="A primary scene_id is required to create a satellite processing job.",
        )
    target_scene = db.query(SatelliteScene).filter(SatelliteScene.id == job_spec.scene_id.strip()).first()
    if not target_scene:
        raise NotFoundError(
            message=f"Satellite scene '{job_spec.scene_id}' not found",
            code="SCENE_NOT_FOUND",
        )

    # 4. Temporal consistency between event and target scene
    if target_scene.captured_at and flood_event.start_at:
        event_start = flood_event.start_at
        event_end = flood_event.end_at or flood_event.start_at
        # Allow pre-flood baseline scenes up to 30 days prior and post-flood observation up to 14 days after
        min_allowed = event_start - timedelta(days=30)
        max_allowed = event_end + timedelta(days=14)
        if target_scene.captured_at < min_allowed or target_scene.captured_at > max_allowed:
            raise FloodLensAPIException(
                status_code=400,
                code="TEMPORAL_EVENT_MISMATCH",
                message=(
                    f"Target scene capture timestamp ({target_scene.captured_at.isoformat()}) "
                    f"is outside the temporal scope of flood event '{flood_event.id}' "
                    f"[{min_allowed.isoformat()} to {max_allowed.isoformat()}]."
                ),
            )

    # 5. Geographic consistency between event region and target scene
    if target_scene.bbox_geojson and flood_event.region_id:
        try:
            t_geom = shape(target_scene.bbox_geojson.get("geometry", target_scene.bbox_geojson))
            # Known region footprint for nepal_terai
            if flood_event.region_id.lower() in ("nepal_terai", "koshi_basin"):
                region_poly = Polygon([[79.5, 26.0], [88.5, 26.0], [88.5, 30.5], [79.5, 30.5], [79.5, 26.0]])
                if not t_geom.intersects(region_poly):
                    raise FloodLensAPIException(
                        status_code=400,
                        code="GEOGRAPHIC_EVENT_MISMATCH",
                        message=(
                            f"Target scene footprint is outside the event geographic region "
                            f"'{flood_event.region_id}'."
                        ),
                    )
        except FloodLensAPIException:
            raise
        except Exception as e:
            logger.warning("Could not compute event-scene geographic intersection: %s", e)

    # 6. Baseline scene validation & Method-Specific Rules
    baseline_scene: Optional[SatelliteScene] = None
    if method == "SAR_CHANGE":
        # SAR change detection strictly requires a pre-flood baseline scene
        if not job_spec.baseline_scene_id or not job_spec.baseline_scene_id.strip():
            raise FloodLensAPIException(
                status_code=400,
                code="MISSING_BASELINE_SCENE",
                message="SAR_CHANGE detection requires both target (post-flood) and baseline (pre-flood) radar acquisitions.",
            )

    if job_spec.baseline_scene_id:
        baseline_scene = db.query(SatelliteScene).filter(SatelliteScene.id == job_spec.baseline_scene_id.strip()).first()
        if not baseline_scene:
            raise NotFoundError(
                message=f"Baseline satellite scene '{job_spec.baseline_scene_id}' not found",
                code="SCENE_NOT_FOUND",
            )

        # Temporal compatibility: baseline must precede or equal target scene
        if baseline_scene.captured_at and target_scene.captured_at:
            if baseline_scene.captured_at > target_scene.captured_at:
                raise FloodLensAPIException(
                    status_code=400,
                    code="TEMPORAL_INCOMPATIBILITY",
                    message=(
                        f"Baseline scene capture timestamp ({baseline_scene.captured_at.isoformat()}) "
                        f"must precede or match target scene capture timestamp ({target_scene.captured_at.isoformat()})."
                    ),
                )

        # Geographic compatibility: bounding footprints must intersect
        if baseline_scene.bbox_geojson and target_scene.bbox_geojson:
            try:
                b_geom = shape(baseline_scene.bbox_geojson.get("geometry", baseline_scene.bbox_geojson))
                t_geom = shape(target_scene.bbox_geojson.get("geometry", target_scene.bbox_geojson))
                if not b_geom.intersects(t_geom):
                    raise FloodLensAPIException(
                        status_code=400,
                        code="GEOGRAPHIC_INCOMPATIBILITY",
                        message="Target scene and baseline scene geographic footprints do not overlap.",
                    )
            except FloodLensAPIException:
                raise
            except Exception as e:
                logger.warning("Could not compute bounding footprint intersection: %s", e)

    # 7. Modality compatibility (Issue 2)
    target_modality = (target_scene.modality or "").strip().lower()
    if method == "NDWI" and target_modality == "sar":
        raise FloodLensAPIException(
            status_code=400,
            code="MODALITY_INCOMPATIBILITY",
            message="NDWI index calculation requires optical imagery, but target scene has SAR modality.",
        )
    if method == "SAR_CHANGE":
        if target_modality != "sar":
            raise FloodLensAPIException(
                status_code=400,
                code="MODALITY_INCOMPATIBILITY",
                message="SAR_CHANGE detection requires radar imagery (SAR) for the target scene.",
            )
        if baseline_scene:
            base_modality = (baseline_scene.modality or "").strip().lower()
            if base_modality != "sar":
                raise FloodLensAPIException(
                    status_code=400,
                    code="MODALITY_INCOMPATIBILITY",
                    message="SAR_CHANGE detection requires radar imagery (SAR) for the baseline scene.",
                )

    # 8. Asset reference security and strict existence check (Issue 1: NO SILENT FALLBACK)
    is_safe, resolved_target = is_safe_path(target_scene.asset_ref)
    if not is_safe or resolved_target is None:
        raise FloodLensAPIException(
            status_code=400,
            code="SECURITY_VIOLATION",
            message="Access to the specified scene asset storage path is forbidden.",
        )

    # Strictly reject uncalibrated visual browse thumbnails
    if method == "SAR_CHANGE" and "thumbnail" in str(resolved_target).lower():
        raise FloodLensAPIException(
            status_code=400,
            code="INVALID_INPUT_ARTIFACT",
            message=(
                "Sentinel-1 preview thumbnails are uncalibrated visual browse images and cannot "
                "be used for quantitative SAR change detection. Full-resolution calibrated GRD/SLC "
                "radar observations required."
            ),
        )

    # Strict existence check: NEVER fall back to synthetic files silently
    if not resolved_target.exists():
        raise FloodLensAPIException(
            status_code=400,
            code="MISSING_INPUT_ARTIFACTS",
            message=f"Target scene asset reference '{target_scene.asset_ref}' cannot be accessed or does not exist.",
            details={"asset_ref": target_scene.asset_ref},
        )

    # If baseline is supplied, validate its asset strictly
    resolved_base: Optional[Path] = None
    if baseline_scene:
        b_safe, resolved_base = is_safe_path(baseline_scene.asset_ref)
        if not b_safe or resolved_base is None:
            raise FloodLensAPIException(
                status_code=400,
                code="SECURITY_VIOLATION",
                message="Access to the specified baseline scene asset storage path is forbidden.",
            )

        if method == "SAR_CHANGE" and "thumbnail" in str(resolved_base).lower():
            raise FloodLensAPIException(
                status_code=400,
                code="INVALID_INPUT_ARTIFACT",
                message="Baseline Sentinel-1 preview thumbnails cannot be used for quantitative SAR change detection.",
            )

        if not resolved_base.exists():
            raise FloodLensAPIException(
                status_code=400,
                code="MISSING_INPUT_ARTIFACTS",
                message=f"Baseline scene asset reference '{baseline_scene.asset_ref}' cannot be accessed or does not exist.",
                details={"asset_ref": baseline_scene.asset_ref},
            )

    # 9. Optical NDWI band directory validation
    if method == "NDWI" and resolved_target.is_dir():
        target_g = list(resolved_target.glob("*B03*.tif")) + list(resolved_target.glob("*green*.tif"))
        target_n = list(resolved_target.glob("*B08*.tif")) + list(resolved_target.glob("*nir*.tif"))
        if not target_g or not target_n:
            raise FloodLensAPIException(
                status_code=400,
                code="MISSING_INPUT_BANDS",
                message=f"Target scene directory '{target_scene.asset_ref}' is missing required Sentinel-2 bands (B03 Green, B08 NIR).",
            )

        allow_single = False
        if hasattr(job_spec, "parameters") and isinstance(job_spec.parameters, dict):
            allow_single = bool(job_spec.parameters.get("allow_single_scene"))

        if not baseline_scene and not allow_single:
            raise FloodLensAPIException(
                status_code=400,
                code="MISSING_BASELINE_SCENE",
                message=(
                    "Optical new-flood detection (NDWI) from satellite bands requires both target (post-flood) "
                    "and baseline (pre-flood) optical acquisitions to distinguish new inundation from persistent water."
                ),
            )

        if baseline_scene and resolved_base and resolved_base.is_dir():
            base_g = list(resolved_base.glob("*B03*.tif")) + list(resolved_base.glob("*green*.tif"))
            base_n = list(resolved_base.glob("*B08*.tif")) + list(resolved_base.glob("*nir*.tif"))
            if not base_g or not base_n:
                raise FloodLensAPIException(
                    status_code=400,
                    code="MISSING_INPUT_BANDS",
                    message=f"Baseline scene directory '{baseline_scene.asset_ref}' is missing required Sentinel-2 bands (B03 Green, B08 NIR).",
                )

    return target_scene, baseline_scene, flood_event, resolved_target


def _is_synthetic_fixture(asset_path: Path) -> bool:
    """Return True if the asset originates from explicit bundled test fixture directories."""
    path_str = str(asset_path).replace("\\", "/").lower()
    return "tests/fixtures" in path_str or "fixture" in path_str or "test_fixtures" in path_str


def _process_vector_asset(
    asset_path: Path,
    method: str,
) -> Tuple[MultiPolygon, float, str, Optional[str]]:
    """Process precomputed or vectorized GeoJSON asset into a standardized MultiPolygon.

    Validates GeoJSON CRS, reprojects from UTM if projected, and verifies geographic coordinates.
    """
    with open(asset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check for legacy CRS definitions in GeoJSON
    crs_name = ""
    if isinstance(data, dict) and "crs" in data and isinstance(data["crs"], dict):
        crs_props = data["crs"].get("properties", {})
        crs_name = str(crs_props.get("name", "")).upper()

    features = []
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    elif "coordinates" in data:
        features = [{"type": "Feature", "geometry": data, "properties": {}}]

    # Check if coordinates need reprojection from UTM to EPSG:4326
    needs_reprojection = "32645" in crs_name or "UTM" in crs_name
    transformer = None
    if needs_reprojection:
        transformer = pyproj.Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)

    polys = []
    for feat in features:
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            shp = shape(geom_dict)
            if shp.is_empty:
                continue

            # Reproject if projected CRS was detected
            if transformer is not None:
                shp = shapely.ops.transform(transformer.transform, shp)

            # Validate coordinate bounds (WGS 84 lon in [-180, 180], lat in [-90, 90])
            minx, miny, maxx, maxy = shp.bounds
            if minx < -180.0 or maxx > 180.0 or miny < -90.0 or maxy > 90.0:
                raise ValueError(
                    f"GeoJSON coordinate values [{minx}, {miny}, {maxx}, {maxy}] are out of WGS84 bounds."
                )

            if not shp.is_valid:
                shp = make_valid(shp)

            if shp.geom_type == "Polygon" and shp.area > 0:
                polys.append(shp)
            elif shp.geom_type == "MultiPolygon":
                polys.extend([p for p in shp.geoms if not p.is_empty and p.area > 0])
        except Exception as e:
            logger.warning("Skipping invalid GeoJSON feature geometry: %s", e)

    if not polys:
        raise ValueError(f"No valid flood polygon features extracted from {asset_path.name}")

    merged = normalize_to_multipolygon(MultiPolygon(polys))
    area_km2 = compute_metric_area_km2(merged)

    # Provenance tagging: SYNTHETIC_TEST_FIXTURE or IMPORTED_PRECOMPUTED
    if _is_synthetic_fixture(asset_path):
        provenance = "SYNTHETIC_TEST_FIXTURE"
    else:
        provenance = "IMPORTED_PRECOMPUTED"

    return merged, area_km2, provenance, str(asset_path)


def _process_raster_mask(
    raster_path: Path,
    method: str,
) -> Tuple[MultiPolygon, float, str, Optional[str], Optional[str]]:
    """Polygonize a GeoTIFF water mask into EPSG:4326 MultiPolygon geometry."""
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.warp import transform_geom
    except ImportError:
        raise RuntimeError("rasterio is required for raster satellite processing.")

    with rasterio.open(raster_path) as src:
        mask = src.read(1)
        src_crs = src.crs or "EPSG:4326"
        transform = src.transform

    flood_pixels = (mask == 1).astype(np.uint8)
    if np.count_nonzero(flood_pixels) == 0:
        return MultiPolygon([]), 0.0, "IMPORTED_PRECOMPUTED", None, str(raster_path)

    wgs84_polys = []
    for geom_dict, val in shapes(flood_pixels, mask=(flood_pixels == 1), transform=transform):
        if val != 1:
            continue
        try:
            if str(src_crs).upper() not in ("EPSG:4326", "WGS84"):
                geom_wgs84 = transform_geom(src_crs, "EPSG:4326", geom_dict)
            else:
                geom_wgs84 = geom_dict

            poly_obj = shape(geom_wgs84)
            if not poly_obj.is_valid:
                poly_obj = make_valid(poly_obj)
            if poly_obj.geom_type == "Polygon" and poly_obj.area > 0:
                wgs84_polys.append(poly_obj)
            elif poly_obj.geom_type == "MultiPolygon":
                wgs84_polys.extend([p for p in poly_obj.geoms if not p.is_empty and p.area > 0])
        except Exception as e:
            logger.warning("Skipping invalid polygon during polygonization: %s", e)

    merged = normalize_to_multipolygon(MultiPolygon(wgs84_polys))
    area_km2 = compute_metric_area_km2(merged)

    if _is_synthetic_fixture(raster_path):
        provenance = "SYNTHETIC_TEST_FIXTURE"
    elif "download" in str(raster_path).lower():
        provenance = "IMPORTED_PRECOMPUTED"
    else:
        provenance = "PROCESSED_OPTICAL" if method == "NDWI" else "PROCESSED_SAR"

    return merged, area_km2, provenance, None, str(raster_path)


def _process_optical_bands(
    scene_dir_or_file: Path,
    baseline_path: Optional[Path],
    threshold: float,
    job_id: str,
    job_parameters: Optional[Dict[str, Any]] = None,
) -> Tuple[MultiPolygon, float, str, Optional[str], Optional[str]]:
    """Compute calibrated NDWI from Green (B03) and NIR (B08) bands with SCL quality masking.

    Validates CRS, geospatial transforms, NoData handling, cloud/shadow masking,
    and isolates newly inundated floodwater from persistent water.
    """
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.warp import transform_geom
    except ImportError:
        raise RuntimeError("rasterio is required for optical band NDWI processing.")

    if not scene_dir_or_file.is_dir():
        return _process_raster_mask(scene_dir_or_file, "NDWI")

    from ml.gis_processing.calculate_ndwi import process_optical_flood_pair

    params = job_parameters or {}
    scl_policy = params.get("scl_policy", "conservative")
    boa_offset = float(params.get("boa_offset", 0.0))
    scale_factor = float(params.get("scale_factor", 10000.0))

    # Locate target bands
    target_g = list(scene_dir_or_file.glob("*B03*.tif")) + list(scene_dir_or_file.glob("*green*.tif"))
    target_n = list(scene_dir_or_file.glob("*B08*.tif")) + list(scene_dir_or_file.glob("*nir*.tif"))
    target_s = list(scene_dir_or_file.glob("*SCL*.tif")) + list(scene_dir_or_file.glob("*scl*.tif"))

    if not target_g or not target_n:
        raise FileNotFoundError(
            f"Required Sentinel-2 bands (B03 Green, B08 NIR) not found in directory: {scene_dir_or_file}"
        )

    # Dual-temporal new-flood detection when baseline is provided
    if baseline_path and baseline_path.is_dir():
        base_g = list(baseline_path.glob("*B03*.tif")) + list(baseline_path.glob("*green*.tif"))
        base_n = list(baseline_path.glob("*B08*.tif")) + list(baseline_path.glob("*nir*.tif"))
        base_s = list(baseline_path.glob("*SCL*.tif")) + list(baseline_path.glob("*scl*.tif"))

        if not base_g or not base_n:
            raise FileNotFoundError(
                f"Required Sentinel-2 baseline bands (B03 Green, B08 NIR) not found in directory: {baseline_path}"
            )

        result_dict = process_optical_flood_pair(
            pre_green_path=base_g[0],
            pre_nir_path=base_n[0],
            post_green_path=target_g[0],
            post_nir_path=target_n[0],
            pre_scl_path=base_s[0] if base_s else None,
            post_scl_path=target_s[0] if target_s else None,
            out_dir=OUTPUT_DIR,
            threshold=threshold,
            job_id=job_id,
            scl_policy=scl_policy,
            boa_offset=boa_offset,
            scale_factor=scale_factor,
        )

        merged = result_dict["multipolygon"]
        area_km2 = result_dict["area_km2"]
        poly_ref = result_dict["artifacts"]["flood_extent_geojson"]
        raster_ref = result_dict["artifacts"]["flood_mask_tif"]
        provenance = "SYNTHETIC_TEST_FIXTURE" if _is_synthetic_fixture(scene_dir_or_file) else "PROCESSED_OPTICAL"
        return merged, area_km2, provenance, poly_ref, raster_ref

    # Otherwise, single-scene water extent analysis
    with rasterio.open(target_g[0]) as g_src:
        green = g_src.read(1).astype(np.float32)
        profile = g_src.profile.copy()
        transform = g_src.transform
        crs = g_src.crs
        nodata_g = g_src.nodata
        target_shape = g_src.shape

    with rasterio.open(target_n[0]) as n_src:
        nir = n_src.read(1).astype(np.float32)
        crs_n = n_src.crs
        shape_n = n_src.shape
        nodata_n = n_src.nodata

    if crs != crs_n:
        raise ValueError(f"CRS mismatch between Green ({crs}) and NIR ({crs_n}) bands.")
    if target_shape != shape_n:
        raise ValueError(f"Dimension mismatch between Green {target_shape} and NIR {shape_n} bands.")

    if nodata_g is not None:
        green[green == nodata_g] = np.nan
    if nodata_n is not None:
        nir[nir == nodata_n] = np.nan
    green[green < 0] = np.nan
    nir[nir < 0] = np.nan

    denom = green + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = np.where(denom <= 0, np.nan, (green - nir) / denom)
    ndwi = np.clip(ndwi, -1.0, 1.0)

    # SCL quality masking for single scene
    valid_mask = ~np.isnan(ndwi) & (green > 0)
    if target_s:
        with rasterio.open(target_s[0]) as s_src:
            scl = s_src.read(1)
            if scl.shape != target_shape:
                scl = np.repeat(np.repeat(scl, target_shape[0] // scl.shape[0], axis=0), target_shape[1] // scl.shape[1], axis=1)
            unsuitable = {0, 1, 3, 8, 9, 10, 11}
            valid_mask = valid_mask & ~np.isin(scl, list(unsuitable))

    is_water = (ndwi > threshold) & valid_mask
    mask = np.where(~valid_mask, 255, np.where(is_water, 1, 0)).astype(np.uint8)

    # Save artifacts
    out_mask_path = OUTPUT_DIR / f"{job_id}_flood_mask.tif"
    profile.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.open(out_mask_path, "w", **profile) as dst:
        dst.write(mask, 1)

    out_ndwi_path = OUTPUT_DIR / f"{job_id}_post_ndwi.tif"
    prof_f = profile.copy()
    prof_f.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(out_ndwi_path, "w", **prof_f) as dst:
        dst.write(ndwi.astype(np.float32), 1)

    # Vectorize
    wgs84_polys = []
    flood_idx = (mask == 1).astype(np.uint8)
    for geom_dict, val in shapes(flood_idx, mask=(flood_idx == 1), transform=transform):
        if val != 1:
            continue
        try:
            if str(crs).upper() not in ("EPSG:4326", "WGS84"):
                geom_wgs84 = transform_geom(crs, "EPSG:4326", geom_dict)
            else:
                geom_wgs84 = geom_dict

            p = shape(geom_wgs84)
            if not p.is_valid:
                p = make_valid(p)
            if p.geom_type == "Polygon" and p.area > 0:
                wgs84_polys.append(p)
            elif p.geom_type == "MultiPolygon":
                wgs84_polys.extend([sub for sub in p.geoms if not sub.is_empty and sub.area > 0])
        except Exception as e:
            logger.warning("Skipping invalid vectorized polygon: %s", e)

    merged = normalize_to_multipolygon(MultiPolygon(wgs84_polys))
    area_km2 = compute_metric_area_km2(merged)

    out_geojson_path = OUTPUT_DIR / f"{job_id}_flood_extent.geojson"
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {
                    "job_id": job_id,
                    "method": "NDWI",
                    "area_km2": area_km2,
                    "is_baseline_subtracted": False,
                    "analysis_type": "SINGLE_SCENE_WATER_EXTENT",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        ],
    }
    with open(out_geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f)

    provenance = "SYNTHETIC_TEST_FIXTURE" if _is_synthetic_fixture(scene_dir_or_file) else "PROCESSED_OPTICAL_SINGLE_SCENE"
    return merged, area_km2, provenance, str(out_geojson_path), str(out_mask_path)


def _process_sar_radar_pair(
    target_raster_path: Path,
    baseline_raster_path: Path,
    threshold_db: float,
    job_id: str,
) -> Tuple[MultiPolygon, float, str, Optional[str], Optional[str]]:
    """Compute calibrated Sentinel-1 SAR change detection from pre/post radar rasters (Issue 2).

    Calculates backscatter difference: Delta sigma0 = 10 * log10(Post / Pre) = Post_dB - Pre_dB
    Inundated water exhibits specular radar loss (Delta sigma0 < threshold_db).
    """
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.warp import transform_geom
    except ImportError:
        raise RuntimeError("rasterio is required for SAR radar change detection.")

    with rasterio.open(target_raster_path) as post_src:
        post_arr = post_src.read(1).astype(np.float32)
        profile = post_src.profile.copy()
        transform = post_src.transform
        crs = post_src.crs
        shape_post = post_src.shape
        nodata_post = post_src.nodata

    with rasterio.open(baseline_raster_path) as pre_src:
        pre_arr = pre_src.read(1).astype(np.float32)
        shape_pre = pre_src.shape
        crs_pre = pre_src.crs
        nodata_pre = pre_src.nodata

    if crs != crs_pre:
        raise ValueError(f"SAR CRS mismatch: target={crs}, baseline={crs_pre}")
    if shape_post != shape_pre:
        raise ValueError(f"SAR dimension mismatch: target={shape_post}, baseline={shape_pre}")

    # NoData handling
    if nodata_post is not None:
        post_arr[post_arr == nodata_post] = np.nan
    if nodata_pre is not None:
        pre_arr[pre_arr == nodata_pre] = np.nan

    # Convert linear amplitude/intensity to dB backscatter
    with np.errstate(divide="ignore", invalid="ignore"):
        post_db = 10.0 * np.log10(np.clip(post_arr, 1e-4, None))
        pre_db = 10.0 * np.log10(np.clip(pre_arr, 1e-4, None))
        diff_db = post_db - pre_db

    # Default drop threshold for specular water inundation: -3.0 dB
    effective_thresh = threshold_db if threshold_db != 0.0 else -3.0
    is_flood = (diff_db < effective_thresh) & ~np.isnan(diff_db)

    mask = np.where(np.isnan(diff_db), 255, np.where(is_flood, 1, 0)).astype(np.uint8)

    # Save output GeoTIFF mask artifact
    out_mask_path = OUTPUT_DIR / f"{job_id}_sar_flood_mask.tif"
    profile.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.open(out_mask_path, "w", **profile) as dst:
        dst.write(mask, 1)

    # Vectorize
    wgs84_polys = []
    flood_idx = (mask == 1).astype(np.uint8)
    for geom_dict, val in shapes(flood_idx, mask=(flood_idx == 1), transform=transform):
        if val != 1:
            continue
        try:
            if str(crs).upper() not in ("EPSG:4326", "WGS84"):
                geom_wgs84 = transform_geom(crs, "EPSG:4326", geom_dict)
            else:
                geom_wgs84 = geom_dict

            p = shape(geom_wgs84)
            if not p.is_valid:
                p = make_valid(p)
            if p.geom_type == "Polygon" and p.area > 0:
                wgs84_polys.append(p)
            elif p.geom_type == "MultiPolygon":
                wgs84_polys.extend([sub for sub in p.geoms if not sub.is_empty and sub.area > 0])
        except Exception as e:
            logger.warning("Skipping invalid vectorized polygon: %s", e)

    merged = normalize_to_multipolygon(MultiPolygon(wgs84_polys))
    area_km2 = compute_metric_area_km2(merged)

    # Save GeoJSON vector artifact
    out_geojson_path = OUTPUT_DIR / f"{job_id}_sar_flood_extent.geojson"
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {
                    "job_id": job_id,
                    "method": "SAR_CHANGE",
                    "area_km2": area_km2,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        ],
    }
    with open(out_geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f)

    provenance = "SYNTHETIC_TEST_FIXTURE" if _is_synthetic_fixture(target_raster_path) else "PROCESSED_SAR"
    return merged, area_km2, provenance, str(out_geojson_path), str(out_mask_path)


def compute_artifact_checksum(path: Path) -> str:
    """Compute deterministic SHA-256 digest of input artifact or directory contents."""
    if not path.exists():
        return "missing"
    hasher = hashlib.sha256()
    if path.is_file():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    elif path.is_dir():
        for p in sorted(path.rglob("*.tif")):
            hasher.update(p.name.encode("utf-8"))
            hasher.update(str(p.stat().st_size).encode("utf-8"))
    return hasher.hexdigest()[:16]


def compute_extent_identity(
    event_id: str,
    scene_id: str,
    baseline_scene_id: Optional[str],
    method: str,
    threshold: Optional[float],
    artifact_checksum: str,
    pipeline_version: str = "v1",
) -> str:
    """Generate a collision-resistant deterministic flood extent identity.

    Incorporate:
    - Event ID
    - Target scene ID
    - Baseline scene ID
    - Method and algorithm version
    - Threshold and quality settings
    - Input artifact checksum

    Guarantees:
    - Retries with identical parameters remain strictly idempotent.
    - Different thresholds do not overwrite distinct valid outputs.
    - Different acquisition scenes or baselines remain separate.
    - Avoids truncated string collisions and fits within VARCHAR(100).
    """
    clean_event = event_id.replace(" ", "_")[:16]
    clean_scene = scene_id.replace(" ", "_")[:16]
    norm_thresh = round(float(threshold if threshold is not None else 0.0), 4)

    identity_dict = {
        "event_id": event_id,
        "scene_id": scene_id,
        "baseline_scene_id": baseline_scene_id or "",
        "method": method.upper(),
        "threshold": norm_thresh,
        "artifact_hash": artifact_checksum,
        "version": pipeline_version,
    }
    canonical_repr = json.dumps(identity_dict, sort_keys=True)
    hash_hex = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()[:16]

    extent_id = f"ext_{clean_event}_{clean_scene}_{method.upper()}_{hash_hex}"
    return extent_id[:95]


def execute_satellite_pipeline(
    job: SatelliteJob,
    db: Session,
    heartbeat_cb: Optional[Callable[[], None]] = None,
) -> Tuple[str, str]:
    """Execute the compatible GIS pipeline for a claimed satellite job and persist results in PostGIS.

    Returns:
        (flood_extent_id, provenance)
    """
    scene = db.query(SatelliteScene).filter(SatelliteScene.id == job.scene_id).first()
    if not scene:
        raise NotFoundError(f"Target satellite scene '{job.scene_id}' missing during execution", "SCENE_NOT_FOUND")

    baseline_scene = None
    if job.baseline_scene_id:
        baseline_scene = db.query(SatelliteScene).filter(SatelliteScene.id == job.baseline_scene_id).first()

    is_safe, resolved_target = is_safe_path(scene.asset_ref)
    if not is_safe or not resolved_target or not resolved_target.exists():
        raise FileNotFoundError(f"Scene asset reference '{scene.asset_ref}' is missing or forbidden.")

    resolved_base = None
    if baseline_scene:
        b_safe, resolved_base = is_safe_path(baseline_scene.asset_ref)
        if not b_safe or not resolved_base or not resolved_base.exists():
            raise FileNotFoundError(f"Baseline asset reference '{baseline_scene.asset_ref}' is missing or forbidden.")

    if heartbeat_cb:
        heartbeat_cb()

    job.progress_percent = 30.0
    db.commit()

    suffix = resolved_target.suffix.lower()

    # Route based on method and input data types
    if job.method == "SAR_CHANGE":
        if suffix in (".geojson", ".json"):
            geom, area_km2, provenance, poly_ref = _process_vector_asset(resolved_target, job.method)
            raster_ref = None
        elif suffix in (".tif", ".tiff") and not resolved_target.is_dir():
            if not resolved_base:
                raise ValueError("SAR change detection requires dual-date pre-flood and post-flood radar imagery.")
            geom, area_km2, provenance, poly_ref, raster_ref = _process_sar_radar_pair(
                resolved_target, resolved_base, job.threshold or -3.0, job.id
            )
        else:
            raise ValueError(f"Unrecognized SAR radar input format: {resolved_target.name}")

    elif job.method == "NDWI":
        if suffix in (".geojson", ".json"):
            geom, area_km2, provenance, poly_ref = _process_vector_asset(resolved_target, job.method)
            raster_ref = None
        elif suffix in (".tif", ".tiff") and not resolved_target.is_dir():
            geom, area_km2, provenance, poly_ref, raster_ref = _process_raster_mask(resolved_target, job.method)
        elif resolved_target.is_dir():
            geom, area_km2, provenance, poly_ref, raster_ref = _process_optical_bands(
                resolved_target, resolved_base, job.threshold or 0.0, job.id, job_parameters=job.parameters
            )
        else:
            raise ValueError(f"Unrecognized optical satellite asset format: {resolved_target.name}")
    else:
        raise ValueError(f"Unsupported processing method: {job.method}")

    if heartbeat_cb:
        heartbeat_cb()

    job.progress_percent = 70.0
    db.commit()

    # Verify event ID exists
    event_id = job.event_id
    if not event_id:
        raise ValueError(f"Job '{job.id}' has no associated event_id. Ambiguous event association is rejected.")

    # Multi-event and multi-scene extent preservation with collision-resistant identity
    target_checksum = compute_artifact_checksum(resolved_target)
    base_checksum = compute_artifact_checksum(resolved_base) if resolved_base else "none"
    combined_checksum = f"{target_checksum}_{base_checksum}"

    extent_id = compute_extent_identity(
        event_id=event_id,
        scene_id=job.scene_id,
        baseline_scene_id=job.baseline_scene_id,
        method=job.method,
        threshold=job.threshold,
        artifact_checksum=combined_checksum,
    )

    source_scenes = [job.scene_id]
    if job.baseline_scene_id:
        source_scenes.append(job.baseline_scene_id)

    geom_element = to_wkt_element(mapping(geom), expected_type="MULTIPOLYGON", srid=4326)

    if heartbeat_cb:
        heartbeat_cb()

    # Idempotent upsert matching exact deterministic result identity
    existing_extent = db.query(FloodExtent).filter(FloodExtent.id == extent_id).first()

    if existing_extent:
        logger.info("Idempotently updating existing flood extent '%s' for event '%s'", extent_id, event_id)
        existing_extent.observed_at = scene.captured_at or datetime.now(timezone.utc)
        existing_extent.area_km2 = area_km2
        existing_extent.polygon_ref = poly_ref
        existing_extent.raster_ref = raster_ref
        existing_extent.source_scene_ids = source_scenes
        existing_extent.confidence = None  # Issue 5: No fabricated confidence
        existing_extent.provenance = provenance
        existing_extent.geometry = geom_element
        extent_record = existing_extent
    else:
        logger.info("Creating new flood extent '%s' for event '%s'", extent_id, event_id)
        new_extent = FloodExtent(
            id=extent_id,
            event_id=event_id,
            observed_at=scene.captured_at or datetime.now(timezone.utc),
            method=job.method,
            polygon_ref=poly_ref,
            raster_ref=raster_ref,
            area_km2=area_km2,
            source_scene_ids=source_scenes,
            confidence=None,  # Issue 5: No fabricated confidence
            provenance=provenance,
            geometry=geom_element,
        )
        db.add(new_extent)
        extent_record = new_extent

    db.flush()

    # Emit real-time WebSocket event
    try:
        ws_event = WebSocketEvent(
            event_id=f"ws_{extent_id}",
            type=EventType.FLOOD_EXTENT_UPDATED.value,
            timestamp=datetime.now(timezone.utc),
            location_id=event_id,
            resource_id=extent_id,
        )
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(connection_manager.broadcast(ws_event))
    except Exception as e:
        logger.warning("Could not broadcast extent WebSocket notification: %s", e)

    return extent_record.id, provenance


def dispatch_satellite_job(job_id: str, worker_id: Optional[str] = None) -> None:
    """Entry point for FastAPI BackgroundTasks to claim and execute a queued job."""
    from app.workers.satellite_worker import claim_job, execute_job, generate_worker_id

    db = get_worker_db_session()
    close_after = (db is not _TEST_DB_SESSION)
    active_worker = worker_id or generate_worker_id(prefix="api-dispatch")
    try:
        claimed = claim_job(db, job_id=job_id, worker_id=active_worker)
        if not claimed:
            logger.info("Job '%s' already claimed by another worker or not queued.", job_id)
            return
        execute_job(claimed, db, worker_id=active_worker)
    finally:
        if close_after:
            db.close()


def process_satellite_job(
    job_id: str,
    db_session: Optional[Session] = None,
    worker_id: Optional[str] = None,
) -> None:
    """Backward-compatible function to execute a satellite processing job."""
    if db_session is not None:
        from app.workers.satellite_worker import claim_job, execute_job, generate_worker_id
        active_worker = worker_id or generate_worker_id(prefix="compat")
        claimed = claim_job(db_session, job_id=job_id, worker_id=active_worker)
        if claimed:
            execute_job(claimed, db_session, worker_id=active_worker)
    else:
        dispatch_satellite_job(job_id, worker_id=worker_id)


def recover_pending_jobs(db: Session, now: Optional[datetime] = None) -> int:
    """Backward-compatible alias for worker restart recovery."""
    from app.workers.satellite_worker import recover_interrupted_jobs
    return recover_interrupted_jobs(db, now=now)
