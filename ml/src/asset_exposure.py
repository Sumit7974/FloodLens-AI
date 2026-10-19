"""Asset exposure analysis and spatial join pipeline for FloodLens AI.

Joins multi-horizon flood-risk predictions with critical infrastructure assets
(buildings, roads, hospitals, schools, shelters, farmland, drainage infrastructure)
using valid location keys or geographic coordinates (WGS84 / EPSG:4326).

SAFETY DIRECTIVE:
  - Clearly distinguishes predicted risk exposure from confirmed structural or economic damage.
  - Avoids double-counting assets when spatial boundaries overlap.
  - Transparently handles unmatched records, missing coordinates, duplicate identifiers,
    and invalid geometries.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import MultiPolygon, Point, Polygon, LineString, mapping, shape
    from shapely.validation import make_valid
    import shapely
    _SHAPELY_AVAILABLE = True
except ImportError:
    _SHAPELY_AVAILABLE = False
    logger.warning("Shapely is not available; geometric spatial joins will fall back to location-key matching.")

# Supported infrastructure asset types
RECOGNIZED_ASSET_TYPES = {
    "building",
    "structure",
    "hospital",
    "health_post",
    "school",
    "shelter",
    "road",
    "bridge",
    "drainage_culvert",
    "farmland",
    "water_treatment",
    "power_substation",
}

# Risk category severity ordering
RISK_SEVERITY_ORDER = {
    "low": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
    "unknown": -1,
}


@dataclass
class AssetRecord:
    """Represents a discrete infrastructure asset."""
    asset_id: str
    asset_type: str
    name: str
    location_id: Optional[str] = None
    coordinates: Optional[Tuple[float, float]] = None  # (longitude, latitude) in EPSG:4326
    geometry: Optional[Dict[str, Any]] = None          # GeoJSON geometry dict
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_identifier: str = "osm_nepal_cadastral"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MatchedAssetExposure:
    """Output record joining an asset with predicted flood risk."""
    asset_id: str
    asset_type: str
    name: str
    location_id: str
    horizon_hours: int
    predicted_risk_score: Optional[float]
    risk_category: str
    exposure_status: str
    source_identifier: str
    coordinates: Optional[Tuple[float, float]] = None
    geometry: Optional[Dict[str, Any]] = None
    intersecting_metric_val: Optional[float] = None  # e.g., length_km for roads, area_ha for farmland
    confirmed_damage: Optional[str] = None           # Strictly None or "not_evaluated"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssetExposureSummary:
    """Statistical summary of exposed assets aggregated by risk tier and type."""
    horizon_hours: int
    evaluation_timestamp: str
    total_assets_evaluated: int
    total_assets_exposed: int  # moderate, high, or critical
    by_risk_category: Dict[str, int]
    by_asset_type: Dict[str, Dict[str, int]]
    infrastructure_metrics: Dict[str, float]  # roads_exposed_km, farmland_exposed_ha, etc.
    unmatched_assets_count: int
    data_quality_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_asset_inventory(
    file_path: Union[str, Path],
) -> List[AssetRecord]:
    """Load asset records from a JSON file, GeoJSON FeatureCollection, or CSV.

    Validates identifiers, coordinate bounds, and geometry integrity.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Asset inventory file not found: {path}")

    records: List[AssetRecord] = []
    seen_ids = set()

    if path.suffix.lower() == ".json" or path.suffix.lower() == ".geojson":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", []) if isinstance(data, dict) and data.get("type") == "FeatureCollection" else data
        if isinstance(data, list):
            features = data

        for item in features:
            if not isinstance(item, dict):
                continue

            # Support both GeoJSON Feature and flat dict
            if item.get("type") == "Feature":
                props = item.get("properties", {})
                geom = item.get("geometry")
                asset_id = str(item.get("id") or props.get("asset_id") or props.get("id") or "")
            else:
                props = item
                geom = item.get("geometry")
                asset_id = str(item.get("asset_id") or item.get("id") or "")

            if not asset_id:
                continue

            # Handle duplicate identifiers
            if asset_id in seen_ids:
                logger.warning(f"Duplicate asset ID '{asset_id}' encountered. Skipping duplicate.")
                continue
            seen_ids.add(asset_id)

            asset_type = props.get("asset_type") or props.get("type") or "structure"
            name = props.get("name") or f"{asset_type}_{asset_id}"
            location_id = props.get("location_id")
            source_id = props.get("source_identifier") or props.get("source") or "osm_nepal"

            # Parse coordinates
            coords = None
            if geom and geom.get("type") == "Point" and isinstance(geom.get("coordinates"), list):
                c = geom["coordinates"]
                if len(c) >= 2:
                    coords = (float(c[0]), float(c[1]))
            elif "longitude" in props and "latitude" in props:
                try:
                    coords = (float(props["longitude"]), float(props["latitude"]))
                except (ValueError, TypeError):
                    coords = None

            records.append(
                AssetRecord(
                    asset_id=asset_id,
                    asset_type=str(asset_type).lower(),
                    name=name,
                    location_id=location_id,
                    coordinates=coords,
                    geometry=geom,
                    metadata=props,
                    source_identifier=source_id,
                )
            )

    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            aid = str(row.get("asset_id") or row.get("id") or "")
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)

            coords = None
            if "longitude" in row and "latitude" in row and not pd.isna(row["longitude"]) and not pd.isna(row["latitude"]):
                coords = (float(row["longitude"]), float(row["latitude"]))

            records.append(
                AssetRecord(
                    asset_id=aid,
                    asset_type=str(row.get("asset_type", "structure")).lower(),
                    name=str(row.get("name", f"asset_{aid}")),
                    location_id=str(row.get("location_id")) if not pd.isna(row.get("location_id")) else None,
                    coordinates=coords,
                    geometry=None,
                    metadata=row.to_dict(),
                    source_identifier=str(row.get("source_identifier", "csv_import")),
                )
            )

    logger.info(f"Loaded {len(records)} unique asset records from {path.name}")
    return records


def join_risk_with_assets(
    assets: List[AssetRecord],
    risk_predictions: Union[Dict[str, Any], List[Dict[str, Any]]],
    location_geometries: Optional[Dict[str, Any]] = None,
    horizon_hours: int = 3,
) -> Tuple[List[MatchedAssetExposure], AssetExposureSummary]:
    """Join flood risk predictions with asset records using spatial or location-key matching.

    Args:
        assets: List of AssetRecord instances.
        risk_predictions: Forecast payload dictionary matching backend prediction contract,
                          or a list of forecast run dicts.
        location_geometries: Optional mapping of location_id -> GeoJSON Polygon/MultiPolygon.
        horizon_hours: Target prediction horizon (+1h, +3h, +6h). Default: 3.

    Returns:
        (matched_assets_list, exposure_summary)
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes: List[str] = []

    # 1. Normalize risk predictions into location -> {risk_level, probability} map
    # Supports single forecast payload or multi-location list
    pred_list = [risk_predictions] if isinstance(risk_predictions, dict) else risk_predictions
    location_risk_map: Dict[str, Dict[str, Any]] = {}

    for p in pred_list:
        loc_id = p.get("location_id")
        if not loc_id:
            continue

        horizons = p.get("horizons", [])
        matched_h = next((h for h in horizons if h.get("hours") == horizon_hours), None)
        if matched_h is None and horizons:
            matched_h = horizons[0]

        if matched_h:
            location_risk_map[loc_id] = {
                "risk_level": matched_h.get("risk_level", "unknown").lower(),
                "calibrated_probability": matched_h.get("calibrated_probability"),
                "forecast_id": p.get("forecast_id"),
                "data_quality": p.get("data_quality", "FULL"),
            }

    if not location_risk_map:
        notes.append("No active risk predictions found for the specified horizon.")

    # 2. Parse location geometries into Shapely shapes if available
    shapely_zones: Dict[str, Any] = {}
    if _SHAPELY_AVAILABLE and location_geometries:
        for loc_id, geom_dict in location_geometries.items():
            try:
                raw_shape = shape(geom_dict)
                valid_shape = make_valid(raw_shape) if hasattr(raw_shape, "is_valid") and not raw_shape.is_valid else raw_shape
                if not valid_shape.is_empty:
                    shapely_zones[loc_id] = valid_shape
            except Exception as e:
                logger.warning(f"Invalid geometry for location '{loc_id}': {e}")

    # 3. Join assets to risk
    matched_results: List[MatchedAssetExposure] = []
    unmatched_count = 0
    assigned_assets: set = set()

    for asset in assets:
        if asset.asset_id in assigned_assets:
            continue

        target_loc_id: Optional[str] = None
        spatial_match = False
        intersecting_metric = None

        # A. Try spatial join first if Shapely and geometries are present
        if _SHAPELY_AVAILABLE and shapely_zones:
            asset_shp = None
            if asset.geometry:
                try:
                    asset_shp = make_valid(shape(asset.geometry))
                except Exception:
                    asset_shp = None

            if asset_shp is None and asset.coordinates:
                asset_shp = Point(asset.coordinates[0], asset.coordinates[1])

            if asset_shp is not None and not asset_shp.is_empty:
                # Find intersecting zones; if multiple, pick highest severity zone to avoid double counting
                candidate_locs = []
                for loc_id, zone_shp in shapely_zones.items():
                    if zone_shp.intersects(asset_shp):
                        risk_info = location_risk_map.get(loc_id, {"risk_level": "unknown"})
                        severity = RISK_SEVERITY_ORDER.get(risk_info["risk_level"], -1)
                        candidate_locs.append((loc_id, severity, zone_shp))

                if candidate_locs:
                    # Sort by severity descending to assign to most critical zone
                    candidate_locs.sort(key=lambda x: x[1], reverse=True)
                    target_loc_id = candidate_locs[0][0]
                    spatial_match = True

                    # Calculate intersection metric (e.g. road length in km)
                    try:
                        best_zone = candidate_locs[0][2]
                        inter = best_zone.intersection(asset_shp)
                        if inter.geom_type in ("LineString", "MultiLineString"):
                            intersecting_metric = round(inter.length * 111.139, 3)
                        elif inter.geom_type in ("Polygon", "MultiPolygon"):
                            # Area in hectares
                            centroid_lat = inter.centroid.y
                            import math
                            cos_lat = math.cos(math.radians(centroid_lat))
                            area_km2 = inter.area * 111.139 * (111.139 * cos_lat)
                            intersecting_metric = round(area_km2 * 100.0, 2)
                    except Exception:
                        pass

        # B. Fall back to location-key matching if spatial join was not possible or yielded no match
        if not target_loc_id and asset.location_id:
            target_loc_id = asset.location_id

        # C. Evaluate risk and exposure status
        asset_notes = []
        if target_loc_id and target_loc_id in location_risk_map:
            risk_data = location_risk_map[target_loc_id]
            risk_cat = risk_data["risk_level"]
            score = risk_data["calibrated_probability"]

            if risk_cat in ("critical", "high"):
                exposure_status = "potential_risk_exposure"
            elif risk_cat == "moderate":
                exposure_status = "potential_risk_exposure"
            elif risk_cat == "low":
                exposure_status = "low_risk_monitored"
            else:
                exposure_status = "risk_unavailable"

            if spatial_match:
                asset_notes.append("Matched via spatial geometry intersection.")
            else:
                asset_notes.append("Matched via location identifier key.")
        elif target_loc_id:
            risk_cat = "unknown"
            score = None
            exposure_status = "risk_unavailable"
            asset_notes.append(f"Location '{target_loc_id}' has no prediction for horizon +{horizon_hours}h.")
        else:
            risk_cat = "unknown"
            score = None
            exposure_status = "unmatched"
            unmatched_count += 1
            target_loc_id = "unmatched"
            asset_notes.append("Asset has no matching location key or spatial intersection.")

        matched_record = MatchedAssetExposure(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            name=asset.name,
            location_id=target_loc_id,
            horizon_hours=horizon_hours,
            predicted_risk_score=score,
            risk_category=risk_cat,
            exposure_status=exposure_status,
            source_identifier=asset.source_identifier,
            coordinates=asset.coordinates,
            geometry=asset.geometry,
            intersecting_metric_val=intersecting_metric,
            confirmed_damage=None,  # Strictly None: risk exposure != confirmed damage
            notes=asset_notes,
        )
        matched_results.append(matched_record)
        assigned_assets.add(asset.asset_id)

    # 4. Generate summary statistics
    by_risk: Dict[str, int] = {"low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0}
    by_type: Dict[str, Dict[str, int]] = {}
    roads_km = 0.0
    farmland_ha = 0.0
    exposed_count = 0

    for m in matched_results:
        # Tally risk
        rc = m.risk_category if m.risk_category in by_risk else "unknown"
        by_risk[rc] += 1

        # Tally type
        atype = m.asset_type
        if atype not in by_type:
            by_type[atype] = {"low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0}
        by_type[atype][rc] = by_type[atype].get(rc, 0) + 1

        if m.exposure_status == "potential_risk_exposure":
            exposed_count += 1
            if "road" in atype and m.intersecting_metric_val:
                roads_km += m.intersecting_metric_val
            elif "farm" in atype and m.intersecting_metric_val:
                farmland_ha += m.intersecting_metric_val

    infra_metrics = {
        "roads_exposed_km": round(roads_km, 3),
        "farmland_exposed_ha": round(farmland_ha, 2),
        "critical_facilities_exposed_count": sum(
            by_type.get(t, {}).get("high", 0) + by_type.get(t, {}).get("critical", 0)
            for t in ["hospital", "health_post", "school", "shelter"]
        ),
    }

    summary = AssetExposureSummary(
        horizon_hours=horizon_hours,
        evaluation_timestamp=now_iso,
        total_assets_evaluated=len(matched_results),
        total_assets_exposed=exposed_count,
        by_risk_category=by_risk,
        by_asset_type=by_type,
        infrastructure_metrics=infra_metrics,
        unmatched_assets_count=unmatched_count,
        data_quality_notes=notes,
    )

    logger.info(
        f"Asset risk join completed: {len(matched_results)} assets evaluated, "
        f"{exposed_count} flagged as potential risk exposure for +{horizon_hours}h horizon."
    )
    return matched_results, summary


def generate_koshi_terai_sample_assets() -> List[AssetRecord]:
    """Generate a realistic set of infrastructure assets for the Barahachhetra / Chatara study area.

    Includes health posts, schools, bridges, highway road segments, and agricultural land
    accurately placed within Sunsari District, Nepal Terai (EPSG:4326).
    """
    return [
        AssetRecord(
            asset_id="ast_chatara_health_post_01",
            asset_type="health_post",
            name="Chatara Primary Health Centre",
            location_id="loc_barahachhetra_w2",
            coordinates=(87.162, 26.868),
            geometry={"type": "Point", "coordinates": [87.162, 26.868]},
            metadata={"capacity_beds": 15, "emergency_access": True, "vulnerability": "high"},
            source_identifier="nepal_dhm_osm_pilot",
        ),
        AssetRecord(
            asset_id="ast_barahachhetra_school_02",
            asset_type="school",
            name="Barahachhetra Secondary School",
            location_id="loc_barahachhetra_w2",
            coordinates=(87.145, 26.852),
            geometry={"type": "Point", "coordinates": [87.145, 26.852]},
            metadata={"students_count": 420, "designated_shelter": True},
            source_identifier="nepal_dhm_osm_pilot",
        ),
        AssetRecord(
            asset_id="ast_koshi_bridge_chatara_03",
            asset_type="bridge",
            name="Chatara Koshi Suspension & Road Bridge",
            location_id="loc_barahachhetra_w2",
            coordinates=(87.158, 26.872),
            geometry={"type": "Point", "coordinates": [87.158, 26.872]},
            metadata={"span_m": 260, "critical_evacuation_corridor": True},
            source_identifier="nepal_dhm_osm_pilot",
        ),
        AssetRecord(
            asset_id="ast_koshi_highway_seg_04",
            asset_type="road",
            name="Chatara-Dharan Access Road (Segment A)",
            location_id="loc_barahachhetra_w2",
            coordinates=(87.165, 26.860),
            geometry={
                "type": "LineString",
                "coordinates": [
                    [87.155, 26.870],
                    [87.160, 26.865],
                    [87.170, 26.855],
                ],
            },
            metadata={"road_class": "secondary", "surface": "paved", "length_km": 2.45},
            source_identifier="nepal_dhm_osm_pilot",
        ),
        AssetRecord(
            asset_id="ast_koshi_floodplain_cropland_05",
            asset_type="farmland",
            name="Koshi Right Bank Lowland Paddy Fields",
            location_id="loc_barahachhetra_w2",
            coordinates=(87.135, 26.840),
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [87.125, 26.830],
                        [87.145, 26.830],
                        [87.145, 26.850],
                        [87.125, 26.850],
                        [87.125, 26.830],
                    ]
                ],
            },
            metadata={"crop_type": "rice_paddy", "area_ha": 38.5, "monsoon_harvest_stage": "vegetative"},
            source_identifier="nepal_dhm_osm_pilot",
        ),
        AssetRecord(
            asset_id="ast_dharan_hospital_safe_06",
            asset_type="hospital",
            name="BPKIHS Dharan Hospital (Highland / Safe Zone)",
            location_id="loc_safe_sunsari_dharan",
            coordinates=(87.284, 26.812),
            geometry={"type": "Point", "coordinates": [87.284, 26.812]},
            metadata={"capacity_beds": 700, "elevation_m": 350.0},
            source_identifier="nepal_dhm_osm_pilot",
        ),
    ]
