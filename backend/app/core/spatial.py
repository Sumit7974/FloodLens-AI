"""Spatial processing utilities for FloodLens AI.

Provides cross-backend geometry conversion, PostGIS & Shapely spatial operations,
GeoJSON serialization conforming to RFC 7946, and settlement/asset exposure assessment.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.asset import Asset
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
    if expected_type == "MULTIPOLYGON" and shp.geom_type == "Polygon":
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
            return json.loads(shapely.to_geojson(shp))
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
            return json.loads(shapely.to_geojson(shp))
        except Exception:
            return None

    # Shapely geometry instance
    if hasattr(geom_val, "geom_type"):
        return json.loads(shapely.to_geojson(geom_val))

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
        if evt:
            region_id = evt.region_id

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
    """Execute spatial intersection between a flood extent and critical assets (roads, buildings, agriculture)."""
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
        if extent_shp is not None and not extent_shp.is_empty:
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
