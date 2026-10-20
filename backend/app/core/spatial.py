"""Spatial processing utilities for FloodLens AI.

Provides cross-backend geometry conversion, PostGIS & Shapely spatial operations,
GeoJSON serialization conforming to RFC 7946, and settlement/asset exposure assessment.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any, Dict, List, Optional, Tuple, Union
# Type stubs provided by types-shapely
import pyproj
import shapely
import shapely.ops
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.asset import Asset, Facility, RoadHazard
from app.models.flood_event import FloodEvent
from app.models.location import Location
from app.models.satellite import FloodExtent


def to_wkt_element(
    geom_input: Union[Dict[str, Any], str, WKTElement, WKBElement, Any],
    expected_type: Optional[str] = "MULTIPOLYGON",
    srid: int = 4326,
) -> WKTElement:
    """Convert a GeoJSON dictionary, GeoJSON string, WKT string, or Shapely geometry into a WKTElement.

    Normalizes Polygon to MultiPolygon if expected_type is MULTIPOLYGON.
    """
    if isinstance(geom_input, WKTElement):
        return geom_input

    if isinstance(geom_input, WKBElement):
        shp = to_shape(geom_input)
    elif isinstance(geom_input, dict):
        # Handle GeoJSON Feature or Geometry
        if geom_input.get("type") == "Feature" and "geometry" in geom_input:
            shp = shape(geom_input["geometry"])
        else:
            shp = shape(geom_input)
    elif isinstance(geom_input, str):
        s = geom_input.strip()
        if s.startswith("{"):
            parsed = json.loads(s)
            if parsed.get("type") == "Feature" and "geometry" in parsed:
                shp = shape(parsed["geometry"])
            else:
                shp = shape(parsed)
        else:
            # Strip SRID prefix if present e.g. SRID=4326;POLYGON(...)
            if ";" in s:
                s = s.split(";", 1)[1]
            shp = shapely.from_wkt(s)
    elif hasattr(geom_input, "geom_type"):
        shp = geom_input
    else:
        raise ValueError(f"Unsupported geometry input format: {type(geom_input)}")

    # Ensure validity
    if not shp.is_valid:
        shp = shapely.make_valid(shp)

    # Normalize Polygon to MultiPolygon if expected
    if expected_type == "MULTIPOLYGON" and isinstance(shp, Polygon):
        shp = MultiPolygon([shp])

    return WKTElement(shp.wkt, srid=srid)


def geometry_to_geojson(geom_val: Any) -> Optional[Dict[str, Any]]:
    """Convert any supported database geometry representation into a clean GeoJSON geometry dict."""
    if geom_val is None:
        return None

    if isinstance(geom_val, dict):
        if geom_val.get("type") == "Feature" and "geometry" in geom_val:
            return geom_val["geometry"]
        return geom_val

    # GeoAlchemy2 WKBElement or WKTElement
    if isinstance(geom_val, (WKBElement, WKTElement)):
        try:
            shp = to_shape(geom_val)
            if shp is not None:
                geojson_str = shapely.to_geojson(shp)
                if geojson_str is not None:
                    return json.loads(geojson_str)
        except Exception:
            pass

    # String representation (WKT, EWKT, or GeoJSON JSON string)
    if isinstance(geom_val, str):
        s = geom_val.strip()
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
                if parsed.get("type") == "Feature" and "geometry" in parsed:
                    return parsed["geometry"]
                return parsed
            except Exception:
                return None
        if ";" in s:
            s = s.split(";", 1)[1]
        try:
            shp = shapely.from_wkt(s)
            if shp is not None:
                geojson_str = shapely.to_geojson(shp)
                if geojson_str is not None:
                    return json.loads(geojson_str)
            return None
        except Exception:
            return None

    # Shapely geometry instance
    if hasattr(geom_val, "geom_type"):
        geojson_str = shapely.to_geojson(geom_val)
        if geojson_str is not None:
            return json.loads(geojson_str)
        return None

    return None


def geometry_to_shapely(geom_val: Any) -> Optional[Any]:
    """Convert any database geometry representation into a Shapely geometry object."""
    if geom_val is None:
        return None

    if hasattr(geom_val, "geom_type"):
        return geom_val

    if isinstance(geom_val, (WKBElement, WKTElement)):
        return to_shape(geom_val)

    if isinstance(geom_val, dict):
        if geom_val.get("type") == "Feature" and "geometry" in geom_val:
            return shape(geom_val["geometry"])
        return shape(geom_val)

    if isinstance(geom_val, str):
        s = geom_val.strip()
        if s.startswith("{"):
            parsed = json.loads(s)
            if parsed.get("type") == "Feature" and "geometry" in parsed:
                return shape(parsed["geometry"])
            return shape(parsed)
        if ";" in s:
            s = s.split(";", 1)[1]
        return shapely.from_wkt(s)

    return None


def calculate_area_km2_from_geometry(geom_val: Any) -> float:
    """Calculate approximate area in square kilometers for WGS84 coordinates.

    Uses an equirectangular projection approximation near the centroid for performance
    when calculating offline, or returns 0.0 for point geometries.
    """
    shp = geometry_to_shapely(geom_val)
    if shp is None or shp.is_empty:
        return 0.0

    if shp.geom_type in ("Point", "MultiPoint", "LineString", "MultiLineString"):
        return 0.0

    import math
    centroid = shp.centroid
    lat_rad = math.radians(centroid.y)
    # 1 degree of latitude ~ 111.139 km
    # 1 degree of longitude ~ 111.139 * cos(lat) km
    km_per_deg_lat = 111.139
    km_per_deg_lon = 111.139 * math.cos(lat_rad)
    scale_factor = km_per_deg_lat * km_per_deg_lon
    return round(float(shp.area * scale_factor), 3)


def location_matches_study_area(
    loc: Location,
    region_id: Optional[str],
    study_area_shp: Optional[Any] = None,
) -> bool:
    """Check if a location record belongs to the specified study area / region.

    Evaluates documented region relationships:
    - Direct location ID matches region_id
    - Direct parent_id matches region_id
    - metadata_json explicitly tags region_id, region, district, or study_area_id
    - OR location geometry falls within / intersects verified study-area boundary polygon.
    """
    if not region_id:
        return True

    # The region study area boundary container itself is not a settlement within the study area
    if loc.id == region_id:
        return False

    if loc.parent_id == region_id:
        return True

    meta = loc.metadata_json if isinstance(loc.metadata_json, dict) else {}
    if (
        meta.get("region_id") == region_id
        or meta.get("region") == region_id
        or meta.get("study_area_id") == region_id
        or meta.get("district") == region_id
    ):
        return True

    # Check verified study-area boundary containment if available
    if study_area_shp is not None and not study_area_shp.is_empty and loc.geometry is not None:
        loc_shp = geometry_to_shapely(loc.geometry)
        if loc_shp and not loc_shp.is_empty:
            try:
                if study_area_shp.intersects(loc_shp):
                    return True
            except Exception:
                pass

    return False


def get_affected_settlements_spatial(
    db: Session,
    flood_extent: FloodExtent,
    region_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Execute spatial intersection between a flood extent and mapped settlements (locations).

    Scopes settlement evaluation to the event's study area using documented region
    relationships or verified study-area boundaries. Unrelated administrative regions
    are not counted, preventing false zero-exposure claims when local datasets are missing.

    Returns a tuple of (affected_settlements_list, total_settlements_evaluated).
    Supports both live PostGIS (PostgreSQL) using ST_Intersects and SQLite fallback using Shapely.
    Avoids unsupported population claims by distinguishing settlement population from verified exposure.
    """
    if not flood_extent.geometry:
        return [], 0

    if region_id is None and flood_extent.event_id:
        evt = db.query(FloodEvent).filter(FloodEvent.id == flood_extent.event_id).first()
        if evt and evt.region_id:
            region_id = str(evt.region_id)

    # Resolve study area boundary if available
    study_area_loc = None
    study_area_shp = None
    has_boundary = False
    if region_id:
        study_area_loc = (
            db.query(Location)
            .filter(Location.id == region_id, Location.geometry.isnot(None))
            .first()
        )
        if not study_area_loc:
            candidates = db.query(Location).filter(Location.geometry.isnot(None)).all()
            for cand in candidates:
                cand_meta = cand.metadata_json if isinstance(cand.metadata_json, dict) else {}
                if (
                    cand_meta.get("region_id") == region_id
                    or cand_meta.get("study_area_id") == region_id
                ) and (
                    cand_meta.get("is_study_area") is True
                    or cand.admin_level <= 3
                ):
                    study_area_loc = cand
                    break

        if study_area_loc and study_area_loc.geometry is not None:
            study_area_shp = geometry_to_shapely(study_area_loc.geometry)
            if study_area_shp is not None and not study_area_shp.is_empty:
                has_boundary = True

    is_postgres = False
    bind = db.get_bind()
    if bind is not None and getattr(bind.dialect, "name", None) == "postgresql":
        is_postgres = True

    if is_postgres:
        boundary_loc_id = study_area_loc.id if (study_area_loc and has_boundary) else ""
        # Native PostGIS spatial query scoped to the event's study area / region
        count_query = text("""
            SELECT COUNT(*)
            FROM locations l
            WHERE l.geometry IS NOT NULL
              AND (:region_id IS NULL OR l.id != :region_id)
              AND (
                  :region_id IS NULL
                  OR l.parent_id = :region_id
                  OR l.metadata_json->>'region_id' = :region_id
                  OR l.metadata_json->>'region' = :region_id
                  OR l.metadata_json->>'district' = :region_id
                  OR l.metadata_json->>'study_area_id' = :region_id
                  OR (:has_boundary = TRUE AND EXISTS (
                      SELECT 1 FROM locations sa
                      WHERE sa.id = :boundary_loc_id
                        AND sa.geometry IS NOT NULL
                        AND ST_Intersects(l.geometry, sa.geometry)
                  ))
              );
        """)
        total_evaluated = db.execute(count_query, {
            "region_id": region_id,
            "has_boundary": has_boundary,
            "boundary_loc_id": boundary_loc_id,
        }).scalar() or 0

        if total_evaluated == 0:
            return [], 0

        query = text("""
            SELECT
                l.id,
                l.name,
                l.admin_level,
                l.crs_source,
                l.metadata_json,
                ST_AsGeoJSON(l.geometry) AS geojson,
                ST_GeometryType(l.geometry) AS geom_type,
                CASE
                    WHEN ST_GeometryType(l.geometry) IN ('ST_Polygon', 'ST_MultiPolygon')
                    THEN ROUND((ST_Area(ST_Intersection(l.geometry, fe.geometry)::geography) / 1000000.0)::numeric, 4)
                    ELSE NULL
                END AS intersection_area_km2
            FROM locations l
            JOIN flood_extents fe ON fe.id = :extent_id
            WHERE ST_Intersects(l.geometry, fe.geometry)
              AND (:region_id IS NULL OR l.id != :region_id)
              AND (
                  :region_id IS NULL
                  OR l.parent_id = :region_id
                  OR l.metadata_json->>'region_id' = :region_id
                  OR l.metadata_json->>'region' = :region_id
                  OR l.metadata_json->>'district' = :region_id
                  OR l.metadata_json->>'study_area_id' = :region_id
                  OR (:has_boundary = TRUE AND EXISTS (
                      SELECT 1 FROM locations sa
                      WHERE sa.id = :boundary_loc_id
                        AND sa.geometry IS NOT NULL
                        AND ST_Intersects(l.geometry, sa.geometry)
                  ))
              )
            ORDER BY l.admin_level DESC, l.name ASC;
        """)
        rows = db.execute(query, {
            "extent_id": flood_extent.id,
            "region_id": region_id,
            "has_boundary": has_boundary,
            "boundary_loc_id": boundary_loc_id,
        }).fetchall()
        affected: List[Dict[str, Any]] = []
        for row in rows:
            loc_id, name, admin_level, crs_source, meta, geojson_str, geom_type, area_km2 = row
            loc_geojson = json.loads(geojson_str) if geojson_str else None
            status_desc = "inundated"
            if area_km2 is not None and area_km2 > 0:
                status_desc = "partially_inundated" if area_km2 < 5.0 else "inundated"

            meta_dict = meta if isinstance(meta, dict) else {}
            total_pop = meta_dict.get("population") or meta_dict.get("total_population")
            if total_pop is not None:
                try:
                    total_pop = int(total_pop)
                except (ValueError, TypeError):
                    total_pop = None

            verified_exposed = meta_dict.get("verified_population_exposed") or meta_dict.get("population_exposed")
            if verified_exposed is not None:
                try:
                    verified_exposed = int(verified_exposed)
                except (ValueError, TypeError):
                    verified_exposed = None

            affected.append({
                "settlement_id": loc_id,
                "name": name,
                "admin_level": admin_level,
                "exposure_status": status_desc,
                "intersection_area_km2": float(area_km2) if area_km2 is not None else None,
                "population_exposed": verified_exposed,
                "settlement_population": total_pop,
                "crs_source": crs_source,
                "geometry": loc_geojson,
                "metadata": meta_dict,
            })
        return affected, total_evaluated
    else:
        # SQLite fallback using Shapely with region study area filtering
        all_locations = db.query(Location).filter(Location.geometry.isnot(None)).all()
        candidate_locations = [
            loc for loc in all_locations
            if location_matches_study_area(loc, region_id, study_area_shp)
        ]
        total_evaluated = len(candidate_locations)
        if total_evaluated == 0:
            return [], 0

        extent_shp = geometry_to_shapely(flood_extent.geometry)
        if extent_shp is None or extent_shp.is_empty:
            return [], total_evaluated

        affected: List[Dict[str, Any]] = []
        for loc in candidate_locations:
            loc_shp = geometry_to_shapely(loc.geometry)
            if loc_shp is None or loc_shp.is_empty:
                continue

            if extent_shp.intersects(loc_shp):
                loc_geojson = geometry_to_geojson(loc.geometry)
                area_km2 = None
                status_desc = "inundated"
                if loc_shp.geom_type in ("Polygon", "MultiPolygon"):
                    try:
                        inter = extent_shp.intersection(loc_shp)
                        area_km2 = calculate_area_km2_from_geometry(inter)
                        status_desc = "partially_inundated" if area_km2 < 5.0 else "inundated"
                    except Exception:
                        pass

                meta_dict = loc.metadata_json if isinstance(loc.metadata_json, dict) else {}
                total_pop = meta_dict.get("population") or meta_dict.get("total_population")
                if total_pop is not None:
                    try:
                        total_pop = int(total_pop)
                    except (ValueError, TypeError):
                        total_pop = None

                verified_exposed = meta_dict.get("verified_population_exposed") or meta_dict.get("population_exposed")
                if verified_exposed is not None:
                    try:
                        verified_exposed = int(verified_exposed)
                    except (ValueError, TypeError):
                        verified_exposed = None

                affected.append({
                    "settlement_id": loc.id,
                    "name": loc.name,
                    "admin_level": loc.admin_level,
                    "exposure_status": status_desc,
                    "intersection_area_km2": area_km2,
                    "population_exposed": verified_exposed,
                    "settlement_population": total_pop,
                    "crs_source": loc.crs_source,
                    "geometry": loc_geojson,
                    "metadata": meta_dict,
                })

        return affected, total_evaluated


def get_exposed_assets_spatial(
    db: Session,
    flood_extent: FloodExtent,
) -> Dict[str, Any]:
    """Execute spatial intersection between a flood extent and critical assets (roads, buildings, agriculture).

    Distinguishes:
    - Missing or invalid flood extent geometry ('no_extent_geometry')
    - Absence of mapped assets in the database ('no_assets_available')
    - Measured zero exposure after evaluating existing assets ('completed')
    """
    if not flood_extent.geometry:
        return {
            "roads_exposed_km": 0.0,
            "structures_exposed_count": 0,
            "cropland_exposed_ha": 0.0,
            "exposed_assets": [],
            "status": "no_extent_geometry",
        }

    is_postgres = False
    bind = db.get_bind()
    if bind is not None and getattr(bind.dialect, "name", None) == "postgresql":
        is_postgres = True

    roads_km = 0.0
    structures_count = 0
    cropland_ha = 0.0
    exposed_items: List[Dict[str, Any]] = []

    if is_postgres:
        query = text("""
            SELECT
                a.id,
                a.asset_type,
                a.metadata_json,
                ST_AsGeoJSON(a.geometry) AS geojson,
                ST_GeometryType(a.geometry) AS geom_type,
                CASE
                    WHEN ST_GeometryType(a.geometry) IN ('ST_LineString', 'ST_MultiLineString')
                    THEN ROUND((ST_Length(ST_Intersection(a.geometry, fe.geometry)::geography) / 1000.0)::numeric, 3)
                    WHEN ST_GeometryType(a.geometry) IN ('ST_Polygon', 'ST_MultiPolygon')
                    THEN ROUND((ST_Area(ST_Intersection(a.geometry, fe.geometry)::geography) / 10000.0)::numeric, 3)
                    ELSE 0.0
                END AS metric_val
            FROM assets a
            JOIN flood_extents fe ON fe.id = :extent_id
            WHERE ST_Intersects(a.geometry, fe.geometry);
        """)
        rows = db.execute(query, {"extent_id": flood_extent.id}).fetchall()
        for row in rows:
            asset_id, asset_type, meta, geojson_str, geom_type, metric_val = row
            val = float(metric_val) if metric_val is not None else 0.0
            if "road" in asset_type.lower():
                roads_km += val
            elif "structure" in asset_type.lower() or "building" in asset_type.lower():
                structures_count += 1
            elif "crop" in asset_type.lower() or "farm" in asset_type.lower() or "agri" in asset_type.lower():
                cropland_ha += val

            exposed_items.append({
                "asset_id": asset_id,
                "asset_type": asset_type,
                "metadata": meta if isinstance(meta, dict) else {},
            })
    else:
        extent_shp = geometry_to_shapely(flood_extent.geometry)
        if extent_shp is None or extent_shp.is_empty:
            return {
                "roads_exposed_km": 0.0,
                "structures_exposed_count": 0,
                "cropland_exposed_ha": 0.0,
                "exposed_assets": [],
                "status": "no_extent_geometry",
            }

        assets = db.query(Asset).filter(Asset.geometry.isnot(None)).all()
        for asset in assets:
            asset_shp = geometry_to_shapely(asset.geometry)
            if asset_shp is None or asset_shp.is_empty:
                continue
            if extent_shp.intersects(asset_shp):
                asset_type = asset.asset_type.lower()
                if "road" in asset_type:
                    try:
                        inter = extent_shp.intersection(asset_shp)
                        # approximate km for linestring
                        roads_km += round(inter.length * 111.139, 3)
                    except Exception:
                        roads_km += 0.5
                elif "structure" in asset_type or "building" in asset_type:
                    structures_count += 1
                elif "crop" in asset_type or "farm" in asset_type or "agri" in asset_type:
                    try:
                        inter = extent_shp.intersection(asset_shp)
                        # 1 km2 = 100 hectares
                        cropland_ha += round(calculate_area_km2_from_geometry(inter) * 100.0, 2)
                    except Exception:
                        cropland_ha += 1.0

                exposed_items.append({
                    "asset_id": asset.id,
                    "asset_type": asset.asset_type,
                    "metadata": asset.metadata_json if isinstance(asset.metadata_json, dict) else {},
                })

    return {
        "roads_exposed_km": round(roads_km, 3),
        "structures_exposed_count": structures_count,
        "cropland_exposed_ha": round(cropland_ha, 3),
        "exposed_assets": exposed_items,
        "status": "completed",
    }


def facility_to_response_dict(facility: Facility) -> Dict[str, Any]:
    """Convert a Facility database model into an enriched map-ready response dict.

    Preserves legacy fields (id, name, verification_status, capacity, contact_info)
    and adds map-ready RFC 7946 GeoJSON Point geometry in EPSG:4326, longitude/latitude,
    status check freshness, provenance source, and explicit data limitations.
    """
    loc_geojson = geometry_to_geojson(facility.location)
    lon: Optional[float] = None
    lat: Optional[float] = None
    if loc_geojson and loc_geojson.get("type") == "Point":
        coords = loc_geojson.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lon = float(coords[0])
            lat = float(coords[1])

    details = facility.details if isinstance(facility.details, dict) else {}
    source = details.get("source") or details.get("provenance") or details.get("data_source")

    limitations: List[str] = []
    if loc_geojson is None:
        limitations.append(
            "Facility coordinates are missing or unmapped in geospatial database; physical location cannot be displayed on map."
        )
    if facility.verification_status == "unverified":
        limitations.append(
            "Facility operational readiness and flood safety have not been verified by local authorities; presence in database does not guarantee safety."
        )
    elif facility.verification_status == "demo_labeled":
        limitations.append(
            "Simulated demonstration facility for testing purposes only."
        )

    if facility.capacity is None:
        limitations.append("Capacity unknown or unrecorded in local administrative database.")

    if facility.contact_info is None:
        limitations.append("Public contact information is not on file.")

    return {
        "id": facility.id,
        "type": facility.type,
        "name": facility.name,
        "verification_status": facility.verification_status,
        "capacity": facility.capacity,
        "contact_info": facility.contact_info,
        "status_checked_at": facility.status_checked_at,
        "location": loc_geojson,
        "longitude": lon,
        "latitude": lat,
        "source": source,
        "details": details,
        "limitations": limitations,
    }


def assess_route_spatial(
    db: Session,
    route_geojson: Dict[str, Any],
    event_id: Optional[str] = None,
    cutoff_time: Optional[datetime] = None,
    buffer_meters: float = 25.0,
    evaluation_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute evidence-based geographic hazard screening along a candidate route LineString.

    Performs spatial intersection and proximity screening against:
    A. Relevant active road-hazard geometries scoped to the historical event window and evaluation time
    B. Relevant observed flood extents for the specified historical event (FloodExtent, event_id=event_id)

    Supports both live PostGIS (PostgreSQL) using ST_Intersects / ST_DWithin and
    Shapely spatial fallback with rigorous pyproj Azimuthal Equidistant (AEQD) metric projections.

    Distinguishes direct geometric intersections (0.0m) from proximity corridor warnings.
    Never classifies an unverified route as safe; reports explicit limitations and provenance.
    """
    eval_time = datetime.now(timezone.utc)

    # 1. Convert route to Shapely geometry
    route_shp = geometry_to_shapely(route_geojson)
    if route_shp is None or route_shp.is_empty:
        raise ValueError("Invalid route geometry: unable to parse GeoJSON LineString")

    if route_shp.geom_type not in ("LineString", "MultiLineString"):
        raise ValueError(f"Route geometry must be LineString or MultiLineString, got {route_shp.geom_type}")

    # 2. Scope evaluation time window to historical event if event_id is provided
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = cutoff_time

    if event_id:
        event_obj = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
        if not event_obj:
            raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")
        window_start = event_obj.start_at - timedelta(hours=24)
        if cutoff_time is not None:
            window_end = cutoff_time
        elif event_obj.end_at is not None:
            window_end = event_obj.end_at

    is_postgres = False
    bind = db.get_bind()
    if bind is not None and getattr(bind.dialect, "name", None) == "postgresql":
        is_postgres = True

    hazards_detected: List[Dict[str, Any]] = []
    total_road_hazards_screened = 0
    total_extents_screened = 0

    if is_postgres:
        route_wkt = route_shp.wkt

        # Count active road hazards within temporal window
        count_rh_query = text("""
            SELECT COUNT(*)
            FROM road_hazards rh
            WHERE rh.geometry IS NOT NULL
              AND rh.status = 'active'
              AND (:window_start IS NULL OR rh.observed_at >= :window_start)
              AND (:window_end IS NULL OR rh.observed_at <= :window_end);
        """)
        total_road_hazards_screened = db.execute(count_rh_query, {
            "window_start": window_start,
            "window_end": window_end,
        }).scalar() or 0

        # Query intersecting / proximity active road hazards
        rh_intersect_query = text("""
            SELECT
                rh.id,
                rh.hazard_type,
                rh.status,
                rh.source,
                rh.observed_at,
                rh.confidence,
                ST_Intersects(rh.geometry, ST_GeomFromText(:route_wkt, 4326)) AS is_direct,
                ROUND(ST_Distance(rh.geometry::geography, ST_GeomFromText(:route_wkt, 4326)::geography)::numeric, 1) AS distance_meters,
                ST_AsGeoJSON(ST_Intersection(rh.geometry, ST_GeomFromText(:route_wkt, 4326))) AS intersection_geojson
            FROM road_hazards rh
            WHERE rh.geometry IS NOT NULL
              AND rh.status = 'active'
              AND (:window_start IS NULL OR rh.observed_at >= :window_start)
              AND (:window_end IS NULL OR rh.observed_at <= :window_end)
              AND (
                  ST_Intersects(rh.geometry, ST_GeomFromText(:route_wkt, 4326))
                  OR (:buffer_meters > 0.0 AND ST_DWithin(rh.geometry::geography, ST_GeomFromText(:route_wkt, 4326)::geography, :buffer_meters))
              )
            ORDER BY rh.observed_at DESC;
        """)
        rh_rows = db.execute(rh_intersect_query, {
            "route_wkt": route_wkt,
            "window_start": window_start,
            "window_end": window_end,
            "buffer_meters": float(buffer_meters),
        }).fetchall()

        for row in rh_rows:
            h_id, h_type, h_status, h_source, h_obs_at, h_conf, is_direct, dist_m, inter_geojson_str = row
            is_direct_bool = bool(is_direct)
            distance_val = float(dist_m) if dist_m is not None else 0.0
            inter_details = json.loads(inter_geojson_str) if inter_geojson_str else None
            match_type = "direct_intersection" if is_direct_bool else "proximity_warning"
            prox_dist = 0.0 if is_direct_bool else distance_val

            hazards_detected.append({
                "hazard_id": h_id,
                "hazard_type": h_type,
                "source_layer": "road_hazard",
                "status": h_status,
                "observed_at": h_obs_at,
                "source": h_source,
                "confidence": float(h_conf) if h_conf is not None else None,
                "match_type": match_type,
                "proximity_distance_meters": prox_dist,
                "intersection_details": inter_details,
                "notes": (
                    f"Active road hazard of type '{h_type}' directly intersects candidate route corridor."
                    if is_direct_bool
                    else f"Active road hazard of type '{h_type}' is located within {prox_dist}m buffer corridor (buffer={buffer_meters}m)."
                ),
            })

        # Query intersecting flood extents if event_id provided
        if event_id:
            count_fe_query = text("""
                SELECT COUNT(*)
                FROM flood_extents fe
                WHERE fe.event_id = :event_id
                  AND fe.geometry IS NOT NULL
                  AND (:window_start IS NULL OR fe.observed_at >= :window_start)
                  AND (:window_end IS NULL OR fe.observed_at <= :window_end);
            """)
            total_extents_screened = db.execute(count_fe_query, {
                "event_id": event_id,
                "window_start": window_start,
                "window_end": window_end,
            }).scalar() or 0

            fe_intersect_query = text("""
                SELECT
                    fe.id,
                    fe.method,
                    fe.observed_at,
                    fe.confidence,
                    fe.area_km2,
                    ST_Intersects(fe.geometry, ST_GeomFromText(:route_wkt, 4326)) AS is_direct,
                    ROUND(ST_Distance(fe.geometry::geography, ST_GeomFromText(:route_wkt, 4326)::geography)::numeric, 1) AS distance_meters,
                    ST_AsGeoJSON(ST_Intersection(fe.geometry, ST_GeomFromText(:route_wkt, 4326))) AS intersection_geojson
                FROM flood_extents fe
                WHERE fe.event_id = :event_id
                  AND fe.geometry IS NOT NULL
                  AND (:window_start IS NULL OR fe.observed_at >= :window_start)
                  AND (:window_end IS NULL OR fe.observed_at <= :window_end)
                  AND (
                      ST_Intersects(fe.geometry, ST_GeomFromText(:route_wkt, 4326))
                      OR (:buffer_meters > 0.0 AND ST_DWithin(fe.geometry::geography, ST_GeomFromText(:route_wkt, 4326)::geography, :buffer_meters))
                  )
                ORDER BY fe.observed_at DESC;
            """)
            fe_rows = db.execute(fe_intersect_query, {
                "route_wkt": route_wkt,
                "event_id": event_id,
                "window_start": window_start,
                "window_end": window_end,
                "buffer_meters": float(buffer_meters),
            }).fetchall()

            for row in fe_rows:
                f_id, f_method, f_obs_at, f_conf, f_area, is_direct, dist_m, inter_geojson_str = row
                is_direct_bool = bool(is_direct)
                distance_val = float(dist_m) if dist_m is not None else 0.0
                inter_details = json.loads(inter_geojson_str) if inter_geojson_str else None
                match_type = "direct_intersection" if is_direct_bool else "proximity_warning"
                prox_dist = 0.0 if is_direct_bool else distance_val

                hazards_detected.append({
                    "hazard_id": f_id,
                    "hazard_type": "observed_flood_extent",
                    "source_layer": "flood_extent",
                    "status": "active_inundation",
                    "observed_at": f_obs_at,
                    "source": f"Satellite {f_method}",
                    "confidence": float(f_conf) if f_conf is not None else None,
                    "match_type": match_type,
                    "proximity_distance_meters": prox_dist,
                    "intersection_details": inter_details,
                    "notes": (
                        f"Observed satellite flood extent ({f_method}, area {f_area} km2) physically inundates route segment."
                        if is_direct_bool
                        else f"Observed satellite flood extent ({f_method}, area {f_area} km2) is within {prox_dist}m buffer corridor (buffer={buffer_meters}m)."
                    ),
                })
    else:
        # SQLite / Shapely fallback with metric projection via pyproj
        centroid = route_shp.centroid
        crs_aeqd = pyproj.CRS(proj="aeqd", lat_0=centroid.y, lon_0=centroid.x, datum="WGS84")
        transformer_to_m = pyproj.Transformer.from_crs("EPSG:4326", crs_aeqd, always_xy=True).transform
        route_m = shapely.ops.transform(transformer_to_m, route_shp)

        # Screen active road hazards scoped to event window
        rh_q = db.query(RoadHazard).filter(RoadHazard.status == "active", RoadHazard.geometry.isnot(None))
        if window_start is not None:
            rh_q = rh_q.filter(RoadHazard.observed_at >= window_start)
        if window_end is not None:
            rh_q = rh_q.filter(RoadHazard.observed_at <= window_end)
        active_hazards = rh_q.order_by(RoadHazard.observed_at.desc()).all()
        total_road_hazards_screened = len(active_hazards)

        for rh in active_hazards:
            h_shp = geometry_to_shapely(rh.geometry)
            if h_shp is None or h_shp.is_empty:
                continue

            h_m = shapely.ops.transform(transformer_to_m, h_shp)
            dist_m = float(route_m.distance(h_m))
            is_direct = (dist_m == 0.0) or route_shp.intersects(h_shp)

            if is_direct or (buffer_meters > 0.0 and dist_m <= buffer_meters):
                match_type = "direct_intersection" if is_direct else "proximity_warning"
                prox_dist = 0.0 if is_direct else round(dist_m, 1)
                inter_details = None
                if is_direct:
                    try:
                        inter_geom = route_shp.intersection(h_shp)
                        if not inter_geom.is_empty:
                            inter_geojson_str = shapely.to_geojson(inter_geom)
                            if inter_geojson_str:
                                inter_details = json.loads(inter_geojson_str)
                    except Exception:
                        pass

                hazards_detected.append({
                    "hazard_id": rh.id,
                    "hazard_type": rh.hazard_type,
                    "source_layer": "road_hazard",
                    "status": rh.status,
                    "observed_at": rh.observed_at,
                    "source": rh.source,
                    "confidence": rh.confidence,
                    "match_type": match_type,
                    "proximity_distance_meters": prox_dist,
                    "intersection_details": inter_details,
                    "notes": (
                        f"Active road hazard of type '{rh.hazard_type}' directly intersects candidate route corridor."
                        if is_direct
                        else f"Active road hazard of type '{rh.hazard_type}' is located within {prox_dist}m buffer corridor (buffer={buffer_meters}m)."
                    ),
                })

        # Screen flood extents if event_id is supplied
        if event_id:
            fe_q = db.query(FloodExtent).filter(FloodExtent.event_id == event_id, FloodExtent.geometry.isnot(None))
            if window_start is not None:
                fe_q = fe_q.filter(FloodExtent.observed_at >= window_start)
            if window_end is not None:
                fe_q = fe_q.filter(FloodExtent.observed_at <= window_end)
            extents = fe_q.order_by(FloodExtent.observed_at.desc()).all()
            total_extents_screened = len(extents)

            for fe in extents:
                fe_shp = geometry_to_shapely(fe.geometry)
                if fe_shp is None or fe_shp.is_empty:
                    continue

                fe_m = shapely.ops.transform(transformer_to_m, fe_shp)
                dist_m = float(route_m.distance(fe_m))
                is_direct = (dist_m == 0.0) or route_shp.intersects(fe_shp)

                if is_direct or (buffer_meters > 0.0 and dist_m <= buffer_meters):
                    match_type = "direct_intersection" if is_direct else "proximity_warning"
                    prox_dist = 0.0 if is_direct else round(dist_m, 1)
                    inter_details = None
                    if is_direct:
                        try:
                            inter_geom = route_shp.intersection(fe_shp)
                            if not inter_geom.is_empty:
                                inter_geojson_str = shapely.to_geojson(inter_geom)
                                if inter_geojson_str:
                                    inter_details = json.loads(inter_geojson_str)
                        except Exception:
                            pass

                    hazards_detected.append({
                        "hazard_id": fe.id,
                        "hazard_type": "observed_flood_extent",
                        "source_layer": "flood_extent",
                        "status": "active_inundation",
                        "observed_at": fe.observed_at,
                        "source": f"Satellite {fe.method}",
                        "confidence": fe.confidence,
                        "match_type": match_type,
                        "proximity_distance_meters": prox_dist,
                        "intersection_details": inter_details,
                        "notes": (
                            f"Observed satellite flood extent ({fe.method}, area {fe.area_km2} km2) physically inundates route segment."
                            if is_direct
                            else f"Observed satellite flood extent ({fe.method}, area {fe.area_km2} km2) is within {prox_dist}m buffer corridor (buffer={buffer_meters}m)."
                        ),
                    })

    total_screened = total_road_hazards_screened + total_extents_screened

    # Determine assessment and route status
    limitations: List[str] = [
        "Demonstration decision-support prototype only: route hazard assessment does NOT command emergency deployments or guarantee alternative paths.",
        "Always follow official directives from emergency authorities.",
        "NEVER classify an unverified route as safe; absence of recorded hazards does NOT guarantee road passability or structural stability.",
    ]

    if total_screened == 0:
        route_status = "not_evaluated"
        assessment_status = "NOT_EVALUATED"
        limitations.append(
            "No active road hazard or flood extent records available within event temporal window for screening. Route safety cannot be assessed."
        )
    elif len(hazards_detected) > 0:
        route_status = "hazards_detected"
        assessment_status = "HAZARDS_INTERSECTED"
        limitations.append(
            f"Identified {len(hazards_detected)} hazard intersection(s) / proximity warning(s) along candidate corridor; route may be submerged, blocked, or impassable."
        )
    else:
        route_status = "conditional"
        assessment_status = "NO_KNOWN_INTERSECTIONS"
        limitations.extend([
            "No known intersections identified with available active data in the database.",
            "NEVER infer that a candidate route is safe merely because no hazard intersection was found.",
            "Unmapped localized flooding, damaged bridges, debris, or recent changes may exist.",
        ])

    if event_id and total_extents_screened == 0:
        limitations.append(
            f"No satellite flood extent records found for historical event '{event_id}'. Flood polygon screening could not be performed."
        )
    elif not event_id:
        limitations.append(
            "No historical event_id was specified; route was evaluated strictly against standalone road hazards without event flood extent polygons."
        )

    if not is_postgres:
        limitations.append(
            "Evaluation performed via Shapely and pyproj metric projection fallback (PostGIS not detected on current connection)."
        )

    return {
        "route_status": route_status,
        "assessment_status": assessment_status,
        "hazards_detected": hazards_detected,
        "event_id": event_id,
        "evaluation_time": eval_time,
        "cutoff_time_applied": cutoff_time,
        "total_hazards_screened": total_screened,
        "hazards_intersected_count": len(hazards_detected),
        "limitations": limitations,
        "provenance": {
            "spatial_engine": "PostGIS (native)" if is_postgres else "Shapely / pyproj (fallback)",
            "road_hazards_screened": total_road_hazards_screened,
            "flood_extents_screened": total_extents_screened,
            "buffer_meters": buffer_meters,
            "event_id": event_id,
            "temporal_window_start": window_start.isoformat() if window_start else None,
            "temporal_window_end": window_end.isoformat() if window_end else None,
            "evaluation_context": evaluation_context or {},
        },
    }
