"""Durable background satellite processing pipeline service for FloodLens AI.

Orchestrates:
1. Validation of satellite scenes, temporal & geographic compatibility, and asset references.
2. Durable job dispatching and state machine tracking (QUEUED -> RUNNING -> COMPLETED / FAILED).
3. Remote sensing algorithms (Sentinel-2 NDWI water extraction, change detection, and precomputed GIS import).
4. Idempotent PostGIS persistence in flood_extents with metric UTM Zone 45N area computation.
5. Worker restart recovery and controlled retries.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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

logger = logging.getLogger(__name__)

# Approved storage roots to guard against arbitrary path traversal attacks
_REPO_ROOT = Path(__file__).resolve().parents[3]
_APPROVED_ROOTS = [
    _REPO_ROOT,
    _REPO_ROOT / "ml" / "gis_processing",
    _REPO_ROOT / "ml" / "gis_processing" / "downloads",
    _REPO_ROOT / "data",
    Path(tempfile.gettempdir()),
]

# Ensure output directory exists for fresh processing outputs
OUTPUT_DIR = _REPO_ROOT / "backend" / "app" / "storage" / "satellite_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_safe_path(candidate_path: Union[str, Path]) -> Tuple[bool, Optional[Path]]:
    """Verify that a path does not escape approved directories via directory traversal."""
    try:
        p = Path(candidate_path)
        # Check for path traversal markers in raw string
        raw_str = str(candidate_path)
        if ".." in raw_str:
            return False, None

        if not p.is_absolute():
            resolved = (_REPO_ROOT / p).resolve()
        else:
            resolved = p.resolve()

        for approved in _APPROVED_ROOTS:
            try:
                resolved.relative_to(approved.resolve())
                return True, resolved
            except ValueError:
                continue

        # Also accept temp directory paths created during test runs
        try:
            resolved.relative_to(Path(tempfile.gettempdir()).resolve())
            return True, resolved
        except ValueError:
            pass

        return False, None
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
        polys = [
            sub_geom for sub_geom in geom.geoms
            if sub_geom.geom_type in ("Polygon", "MultiPolygon") and not sub_geom.is_empty and sub_geom.area > 0
        ]
        flat_polys = []
        for p in polys:
            if p.geom_type == "Polygon":
                flat_polys.append(p)
            elif p.geom_type == "MultiPolygon":
                flat_polys.extend(p.geoms)
        return MultiPolygon(flat_polys)
    return MultiPolygon([])


def validate_satellite_job_parameters(
    db: Session,
    job_spec: SatelliteJobCreate,
) -> Tuple[SatelliteScene, Optional[SatelliteScene], Optional[FloodEvent], Path]:
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

    # 2. Target scene existence
    if not job_spec.scene_id:
        raise FloodLensAPIException(
            status_code=400,
            code="MISSING_SCENE_ID",
            message="A primary scene_id is required to create a satellite processing job.",
        )
    target_scene = db.query(SatelliteScene).filter(SatelliteScene.id == job_spec.scene_id).first()
    if not target_scene:
        raise NotFoundError(
            message=f"Satellite scene '{job_spec.scene_id}' not found",
            code="SCENE_NOT_FOUND",
        )

    # 3. Baseline scene validation (if specified)
    baseline_scene: Optional[SatelliteScene] = None
    if job_spec.baseline_scene_id:
        baseline_scene = db.query(SatelliteScene).filter(SatelliteScene.id == job_spec.baseline_scene_id).first()
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

    # 4. Modality compatibility
    modality = (target_scene.modality or "").strip().lower()
    if method == "NDWI" and modality == "sar":
        raise FloodLensAPIException(
            status_code=400,
            code="MODALITY_INCOMPATIBILITY",
            message="NDWI index calculation requires optical imagery, but target scene has SAR modality.",
        )
    if method == "SAR_CHANGE" and modality == "optical":
        raise FloodLensAPIException(
            status_code=400,
            code="MODALITY_INCOMPATIBILITY",
            message="SAR_CHANGE detection requires radar imagery (SAR), but target scene has optical modality.",
        )

    # 5. Flood event validation (if specified)
    flood_event: Optional[FloodEvent] = None
    if job_spec.event_id:
        flood_event = db.query(FloodEvent).filter(FloodEvent.id == job_spec.event_id).first()
        if not flood_event:
            raise NotFoundError(
                message=f"Flood event '{job_spec.event_id}' not found",
                code="EVENT_NOT_FOUND",
            )

    # 6. Asset reference security and existence
    is_safe, resolved_target = is_safe_path(target_scene.asset_ref)
    if not is_safe or resolved_target is None:
        raise FloodLensAPIException(
            status_code=400,
            code="SECURITY_VIOLATION",
            message="Access to the specified scene asset storage path is forbidden.",
        )

    # Distinguish uncalibrated browse preview thumbnails from real SAR radar observations
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

    if not resolved_target.exists():
        raise FloodLensAPIException(
            status_code=400,
            code="MISSING_INPUT_ARTIFACTS",
            message=f"Target scene asset reference '{target_scene.asset_ref}' cannot be accessed or does not exist.",
            details={"asset_ref": target_scene.asset_ref},
        )

    # If baseline is supplied, validate its asset as well
    if baseline_scene:
        b_safe, resolved_base = is_safe_path(baseline_scene.asset_ref)
        if not b_safe or resolved_base is None:
            raise FloodLensAPIException(
                status_code=400,
                code="SECURITY_VIOLATION",
                message="Access to the specified baseline scene asset storage path is forbidden.",
            )
        if not resolved_base.exists():
            raise FloodLensAPIException(
                status_code=400,
                code="MISSING_INPUT_ARTIFACTS",
                message=f"Baseline scene asset reference '{baseline_scene.asset_ref}' cannot be accessed or does not exist.",
                details={"asset_ref": baseline_scene.asset_ref},
            )

    return target_scene, baseline_scene, flood_event, resolved_target


def _process_vector_asset(
    asset_path: Path,
    method: str,
) -> Tuple[MultiPolygon, float, str, Optional[str]]:
    """Process precomputed or vectorized GeoJSON asset into a standardized MultiPolygon."""
    with open(asset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = []
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    elif "coordinates" in data:
        features = [{"type": "Feature", "geometry": data, "properties": {}}]

    polys = []
    for feat in features:
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        try:
            shp = shape(geom_dict)
            if shp.is_empty:
                continue
            if not shp.is_valid:
                shp = make_valid(shp)
            if shp.geom_type == "Polygon" and shp.area > 0:
                polys.append(shp)
            elif shp.geom_type == "MultiPolygon":
                polys.extend([p for p in shp.geoms if not p.is_empty and p.area > 0])
            elif hasattr(shp, "geoms"):
                for g in shp.geoms:
                    if g.geom_type == "Polygon" and not g.is_empty and g.area > 0:
                        polys.append(g)
                    elif g.geom_type == "MultiPolygon":
                        polys.extend([p for p in g.geoms if not p.is_empty and p.area > 0])
        except Exception:
            continue

    if not polys:
        raise ValueError(f"No valid vector polygons found in asset {asset_path.name}")

    merged = normalize_to_multipolygon(MultiPolygon(polys))
    area_km2 = compute_metric_area_km2(merged)

    # Truthful provenance labeling: archived outputs are explicitly labeled
    provenance = "IMPORTED_PRECOMPUTED"
    return merged, area_km2, provenance, str(asset_path)


def _process_raster_mask(
    raster_path: Path,
    method: str,
) -> Tuple[MultiPolygon, float, str, Optional[str], Optional[str]]:
    """Extract vector polygons from binary flood mask GeoTIFF."""
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.warp import transform_geom
    except ImportError:
        raise RuntimeError("rasterio is required for raster flood mask extraction.")

    with rasterio.open(raster_path) as src:
        mask_data = src.read(1)
        transform = src.transform
        crs = src.crs

    binary = (mask_data == 1).astype(np.uint8)
    if np.count_nonzero(binary) == 0:
        return MultiPolygon([]), 0.0, "IMPORTED_PRECOMPUTED", None, str(raster_path)

    poly_generator = shapes(binary, mask=(binary == 1), transform=transform, connectivity=4)
    wgs84_polys = []
    for geom_dict, val in poly_generator:
        if val != 1:
            continue
        try:
            if crs is not None and crs.to_epsg() != 4326:
                geom_dict = transform_geom(crs, "EPSG:4326", geom_dict)
            shp = shape(geom_dict)
            if not shp.is_valid:
                shp = make_valid(shp)
            if shp.geom_type == "Polygon" and shp.area > 0:
                wgs84_polys.append(shp)
            elif shp.geom_type == "MultiPolygon":
                wgs84_polys.extend([p for p in shp.geoms if not p.is_empty and p.area > 0])
        except Exception:
            continue

    merged = normalize_to_multipolygon(MultiPolygon(wgs84_polys))
    area_km2 = compute_metric_area_km2(merged)
    provenance = "IMPORTED_PRECOMPUTED" if "download" in str(raster_path).lower() else "PROCESSED_OPTICAL"
    return merged, area_km2, provenance, None, str(raster_path)


def _process_optical_bands(
    scene_dir_or_file: Path,
    baseline_path: Optional[Path],
    threshold: float,
    job_id: str,
) -> Tuple[MultiPolygon, float, str, Optional[str], Optional[str]]:
    """Compute fresh NDWI from Green (B03) and NIR (B08) GeoTIFF bands."""
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.warp import transform_geom
    except ImportError:
        raise RuntimeError("rasterio is required for optical band NDWI processing.")

    # Locate green and nir files
    if scene_dir_or_file.is_dir():
        green_files = list(scene_dir_or_file.glob("*B03*.tif")) + list(scene_dir_or_file.glob("*green*.tif"))
        nir_files = list(scene_dir_or_file.glob("*B08*.tif")) + list(scene_dir_or_file.glob("*nir*.tif"))
        if not green_files or not nir_files:
            raise FileNotFoundError(
                f"Required Sentinel-2 bands (B03 Green, B08 NIR) not found in directory: {scene_dir_or_file}"
            )
        green_path = green_files[0]
        nir_path = nir_files[0]
    else:
        # If single GeoTIFF file is passed, check if it's already a flood mask
        return _process_raster_mask(scene_dir_or_file, "NDWI")

    with rasterio.open(green_path) as g_src:
        green = g_src.read(1).astype(np.float32)
        profile = g_src.profile.copy()
        transform = g_src.transform
        crs = g_src.crs
        nodata = g_src.nodata

    with rasterio.open(nir_path) as n_src:
        nir = n_src.read(1).astype(np.float32)

    if nodata is not None:
        green[green == nodata] = np.nan
        nir[nir == nodata] = np.nan

    denom = green + nir
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi_post = np.where(denom == 0, np.nan, (green - nir) / denom)
    ndwi_post = np.clip(ndwi_post, -1.0, 1.0)

    # Baseline comparison if baseline is supplied
    if baseline_path and baseline_path.is_dir():
        b_green_files = list(baseline_path.glob("*B03*.tif")) + list(baseline_path.glob("*green*.tif"))
        b_nir_files = list(baseline_path.glob("*B08*.tif")) + list(baseline_path.glob("*nir*.tif"))
        if b_green_files and b_nir_files:
            with rasterio.open(b_green_files[0]) as bg_src:
                bg = bg_src.read(1).astype(np.float32)
            with rasterio.open(b_nir_files[0]) as bn_src:
                bn = bn_src.read(1).astype(np.float32)
            b_denom = bg + bn
            with np.errstate(divide="ignore", invalid="ignore"):
                ndwi_pre = np.where(b_denom == 0, np.nan, (bg - bn) / b_denom)
            is_flood = (ndwi_post > threshold) & (ndwi_post > ndwi_pre)
        else:
            is_flood = ndwi_post > threshold
    else:
        is_flood = ndwi_post > threshold

    mask = np.where(np.isnan(ndwi_post), 255, np.where(is_flood, 1, 0)).astype(np.uint8)

    # Save output GeoTIFF mask artifact
    out_mask_path = OUTPUT_DIR / f"{job_id}_flood_mask.tif"
    profile.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.open(out_mask_path, "w", **profile) as dst:
        dst.write(mask, 1)

    # Vectorize flooded pixels
    binary = (mask == 1).astype(np.uint8)
    poly_generator = shapes(binary, mask=(binary == 1), transform=transform, connectivity=4)
    wgs84_polys = []
    for geom_dict, val in poly_generator:
        if val != 1:
            continue
        try:
            if crs is not None and crs.to_epsg() != 4326:
                geom_dict = transform_geom(crs, "EPSG:4326", geom_dict)
            shp = shape(geom_dict)
            if not shp.is_valid:
                shp = make_valid(shp)
            if shp.geom_type == "Polygon" and shp.area > 0:
                wgs84_polys.append(shp)
            elif shp.geom_type == "MultiPolygon":
                wgs84_polys.extend([p for p in shp.geoms if not p.is_empty and p.area > 0])
        except Exception:
            continue

    merged = normalize_to_multipolygon(MultiPolygon(wgs84_polys))
    area_km2 = compute_metric_area_km2(merged)

    # Save output GeoJSON artifact
    out_geojson_path = OUTPUT_DIR / f"{job_id}_flood_polygons.geojson"
    out_geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": mapping(merged),
                        "properties": {"job_id": job_id, "area_km2": area_km2, "method": "NDWI"},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    provenance = "PROCESSED_OPTICAL"
    return merged, area_km2, provenance, str(out_geojson_path), str(out_mask_path)


def process_satellite_job(job_id: str, db_session: Optional[Session] = None) -> None:
    """Execute background processing for a queued satellite job."""
    close_db_after = False
    if db_session is None:
        db_session = SessionLocal()
        close_db_after = True

    try:
        job = db_session.query(SatelliteJob).filter(SatelliteJob.id == job_id).first()
        if not job:
            logger.error("Satellite job '%s' not found for processing", job_id)
            return

        # Prevent duplicate execution
        if job.status == "COMPLETED":
            logger.info("Satellite job '%s' is already completed; skipping duplicate run.", job_id)
            return

        # Transition to RUNNING
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        job.progress_percent = 10.0
        db_session.commit()

        # Retrieve scene metadata
        scene = db_session.query(SatelliteScene).filter(SatelliteScene.id == job.scene_id).first()
        if not scene:
            raise NotFoundError(f"Target satellite scene '{job.scene_id}' missing during execution", "SCENE_NOT_FOUND")

        baseline_scene = None
        if job.baseline_scene_id:
            baseline_scene = db_session.query(SatelliteScene).filter(SatelliteScene.id == job.baseline_scene_id).first()

        is_safe, resolved_target = is_safe_path(scene.asset_ref)
        if not is_safe or not resolved_target or not resolved_target.exists():
            raise FileNotFoundError(f"Scene asset reference '{scene.asset_ref}' is missing or forbidden.")

        resolved_base = None
        if baseline_scene:
            b_safe, resolved_base = is_safe_path(baseline_scene.asset_ref)
            if not b_safe or not resolved_base or not resolved_base.exists():
                raise FileNotFoundError(f"Baseline asset reference '{baseline_scene.asset_ref}' is missing or forbidden.")

        job.progress_percent = 30.0
        db_session.commit()

        # Execute appropriate GIS processing workflow
        suffix = resolved_target.suffix.lower()
        if suffix in (".geojson", ".json"):
            geom, area_km2, provenance, poly_ref = _process_vector_asset(resolved_target, job.method)
            raster_ref = None
        elif suffix in (".tif", ".tiff") and not resolved_target.is_dir():
            geom, area_km2, provenance, poly_ref, raster_ref = _process_raster_mask(resolved_target, job.method)
        elif resolved_target.is_dir():
            geom, area_km2, provenance, poly_ref, raster_ref = _process_optical_bands(
                resolved_target, resolved_base, job.threshold or 0.0, job.id
            )
        else:
            raise ValueError(f"Unrecognized satellite asset format: {resolved_target.name}")

        job.progress_percent = 70.0
        db_session.commit()

        # Associate output with target flood event
        event_id = job.event_id
        if not event_id:
            # Fallback to an existing flood event in the database, or create default historical demo event
            existing_event = db_session.query(FloodEvent).order_by(FloodEvent.created_at.desc()).first()
            if existing_event:
                event_id = existing_event.id
            else:
                demo_event = FloodEvent(
                    id="evt_historical_nepal_2017",
                    region_id="nepal_terai",
                    name="Koshi River Monsoon Inundation (August 2017)",
                    start_at=scene.captured_at or datetime.now(timezone.utc),
                )
                db_session.add(demo_event)
                db_session.flush()
                event_id = demo_event.id
            job.event_id = event_id

        # Persist derived flood extent idempotently in PostGIS
        source_scenes = [job.scene_id]
        if job.baseline_scene_id:
            source_scenes.append(job.baseline_scene_id)

        existing_extent = (
            db_session.query(FloodExtent)
            .filter(
                FloodExtent.event_id == event_id,
                FloodExtent.method == job.method,
            )
            .first()
        )

        wkt_elem = to_wkt_element(geom, expected_type="MULTIPOLYGON", srid=4326)

        if existing_extent:
            existing_extent.observed_at = scene.captured_at or datetime.now(timezone.utc)
            existing_extent.polygon_ref = poly_ref or existing_extent.polygon_ref
            existing_extent.raster_ref = raster_ref or existing_extent.raster_ref
            existing_extent.area_km2 = area_km2
            existing_extent.source_scene_ids = source_scenes
            existing_extent.confidence = 0.90 if provenance != "IMPORTED_PRECOMPUTED" else 0.85
            existing_extent.geometry = wkt_elem
            flood_extent_record = existing_extent
        else:
            flood_extent_record = FloodExtent(
                id=f"ext_{uuid.uuid4().hex[:12]}",
                event_id=event_id,
                observed_at=scene.captured_at or datetime.now(timezone.utc),
                method=job.method,
                polygon_ref=poly_ref,
                raster_ref=raster_ref,
                area_km2=area_km2,
                source_scene_ids=source_scenes,
                confidence=0.90 if provenance != "IMPORTED_PRECOMPUTED" else 0.85,
                geometry=wkt_elem,
            )
            db_session.add(flood_extent_record)

        db_session.flush()

        # Update job record to COMPLETED
        job.status = "COMPLETED"
        job.progress_percent = 100.0
        job.completed_at = datetime.now(timezone.utc)
        job.output_extent_id = flood_extent_record.id
        job.provenance = provenance
        job.error_message = None
        db_session.commit()

        # Broadcast WebSocket notification
        try:
            ws_event = WebSocketEvent(
                event_id=f"evt_job_{job.id}",
                type=EventType.PROCESSING_COMPLETED.value,
                timestamp=datetime.now(timezone.utc),
                location_id="nepal_terai",
                resource_id=job.id,
            )
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(connection_manager.broadcast(ws_event))
            except Exception:
                pass
        except Exception:
            pass

        logger.info(
            "Satellite processing job '%s' successfully completed. Extent ID: %s, Area: %.2f km²",
            job.id,
            flood_extent_record.id,
            area_km2,
        )

    except Exception as exc:
        db_session.rollback()
        logger.exception("Satellite processing job '%s' failed: %s", job_id, exc)
        try:
            job = db_session.query(SatelliteJob).filter(SatelliteJob.id == job_id).first()
            if job:
                job.retry_count += 1
                job.error_message = sanitize_error(exc)
                if job.retry_count < job.max_retries and not isinstance(
                    exc, (NotFoundError, ValueError, FileNotFoundError)
                ):
                    job.status = "QUEUED"
                    job.progress_percent = 0.0
                else:
                    job.status = "FAILED"
                    job.progress_percent = 0.0
                    job.completed_at = datetime.now(timezone.utc)
                db_session.commit()
        except Exception as inner_exc:
            logger.error("Failed to persist job failure state: %s", inner_exc)
    finally:
        if close_db_after:
            db_session.close()


def recover_pending_jobs(db: Session) -> int:
    """Recover and re-queue jobs interrupted by simulated or real worker restarts."""
    interrupted_jobs = db.query(SatelliteJob).filter(SatelliteJob.status == "RUNNING").all()
    count = 0
    for j in interrupted_jobs:
        count += 1
        j.retry_count += 1
        if j.retry_count < j.max_retries:
            j.status = "QUEUED"
            j.error_message = f"Recovered after worker restart (attempt {j.retry_count}/{j.max_retries})."
            j.progress_percent = 0.0
        else:
            j.status = "FAILED"
            j.completed_at = datetime.now(timezone.utc)
            j.error_message = "Job failed: maximum retry limit exceeded after worker restart."
            j.progress_percent = 0.0
    if count > 0:
        db.commit()
        logger.info("Recovered %d interrupted satellite processing jobs after restart.", count)
    return count
