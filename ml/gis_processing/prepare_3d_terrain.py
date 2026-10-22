"""
prepare_3d_terrain.py
=====================
FloodLens AI — Cesium 3D Terrain & 3D Tiles Layer Preparation Pipeline
----------------------------------------------------------------------
Loads 2D geospatial layers generated in previous steps:
    1. flood_polygons.geojson      -> flood_polygons_3d.geojson
    2. flooded_buildings.geojson    -> flooded_buildings_3d.geojson
    3. flooded_roads.geojson        -> flooded_roads_3d.geojson
    4. flooded_facilities.geojson   -> flooded_facilities_3d.geojson

For each layer, computes and injects:
    - height: Vertical extrusion / feature height in meters (e.g., 2m floods, 5m roads, 10m buildings)
    - elevation_offset: Vertical offset to ensure correct draping above Cesium 3D tiles & terrain
    - extrudedHeight: Absolute or relative top altitude for 3D polygon extrusion
    - clampToGround / classificationType: Direct CesiumJS terrain-draping and 3D tile classification flags
    - 3D Coordinates: Upgrades 2D (lon, lat) geometries to 3D (lon, lat, z) coordinates using Shapely

Outputs are RFC 7946 GeoJSON files directly compatible with CesiumJS GeoJsonDataSource,
Mapbox GL 3D, and 3D web/mobile map engines.

Author : FloodLens AI Team
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Ensure standard UTF-8 console output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import shapely
from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon
import geopandas as gpd


# ---------------------------------------------------------------------------
# DEFAULT CONFIGURATION & 3D TERRAIN SPECIFICATIONS
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 3D Layer Styling & Height Configurations for Cesium 3D Tiles
LAYER_3D_CONFIGS = {
    "flood_polygons": {
        "input_filename": "flood_polygons.geojson",
        "output_filename": "flood_polygons_3d.geojson",
        "default_height": 2.0,            # 2 meters flood water depth
        "default_offset": 0.5,            # 0.5m offset above terrain mesh to avoid z-fighting
        "clamp_to_ground": True,
        "classification_type": "CESIUM_3D_TILE",
        "style": {
            "fill": "#1E90FF",
            "fill-opacity": 0.65,
            "stroke": "#0000CD",
            "stroke-width": 1.5,
        }
    },
    "flooded_buildings": {
        "input_filename": "flooded_buildings.geojson",
        "output_filename": "flooded_buildings_3d.geojson",
        "default_height": 10.0,           # 10 meters (~3-story building)
        "default_offset": 0.0,            # Anchored to terrain ground surface
        "clamp_to_ground": False,         # Extruded volume
        "classification_type": "NONE",
        "style": {
            "fill": "#E63946",
            "fill-opacity": 0.85,
            "stroke": "#7F1D1D",
            "stroke-width": 1.0,
        }
    },
    "flooded_roads": {
        "input_filename": "flooded_roads.geojson",
        "output_filename": "flooded_roads_3d.geojson",
        "default_height": 5.0,            # 5 meters vertical profile / embankment clearance
        "default_offset": 2.2,            # Elevated above 2.0m flood water level for visibility
        "clamp_to_ground": False,         # Renders above water surface
        "classification_type": "NONE",
        "style": {
            "stroke": "#F77F00",
            "stroke-width": 4.0,
            "stroke-opacity": 0.95,
        }
    },
    "flooded_facilities": {
        "input_filename": "flooded_facilities.geojson",
        "output_filename": "flooded_facilities_3d.geojson",
        "default_height": 10.0,           # 10m default facility height
        "default_offset": 0.5,            # 0.5m offset
        "clamp_to_ground": False,
        "classification_type": "NONE",
        "style": {
            "marker-size": "medium",
            "marker-color": "#D62828",
        }
    }
}


# ---------------------------------------------------------------------------
# FILE LOCATOR
# ---------------------------------------------------------------------------
def locate_input_geojson(filename: str, custom_dir: Optional[Path] = None) -> Path:
    """Search for the target GeoJSON file in standard workspace paths."""
    candidate_dirs = [
        custom_dir,
        Path.cwd(),
        SCRIPT_DIR.parent.parent,
        SCRIPT_DIR,
        DOWNLOADS_DIR,
    ]

    for d in candidate_dirs:
        if d:
            p = d / filename
            if p.is_file() and p.stat().st_size > 50:
                return p.resolve()

    # Recursive fallback
    for d in [SCRIPT_DIR.parent.parent, Path.cwd()]:
        for match in d.rglob(filename):
            if match.is_file() and match.stat().st_size > 50:
                return match.resolve()

    raise FileNotFoundError(f"Could not locate required layer: '{filename}'")


# ---------------------------------------------------------------------------
# DYNAMIC HEIGHT & ATTRIBUTE CALCULATOR
# ---------------------------------------------------------------------------
def compute_building_height(props: Dict[str, Any], default_h: float = 10.0) -> float:
    """Calculate realistic building height based on area or OSM building tags."""
    area_sqm = props.get("area_sqm")
    if area_sqm is not None and area_sqm > 0:
        # Smaller rural outbuildings vs multi-story commercial buildings
        if area_sqm < 40:
            return 4.5    # ~1 story
        elif area_sqm < 100:
            return 7.5    # ~2 stories
        elif area_sqm < 300:
            return 10.5   # ~3 stories
        else:
            return 14.0   # 4+ stories
    return default_h


def compute_facility_height(props: Dict[str, Any], default_h: float = 10.0) -> Tuple[float, str]:
    """Calculate facility height and marker color based on amenity category."""
    amenity = str(props.get("amenity", "")).lower()
    if "hospital" in amenity:
        return 14.0, "#E63946"  # Red for major hospitals
    elif "clinic" in amenity:
        return 8.0, "#F77F00"   # Orange for health clinics
    elif "school" in amenity or "college" in amenity:
        return 9.0, "#457B9D"   # Blue for schools
    elif "police" in amenity:
        return 10.0, "#1D3557"  # Navy for police
    return default_h, "#6C757D"


def compute_road_offset_and_color(props: Dict[str, Any], default_h: float = 5.0, default_off: float = 2.2) -> Tuple[float, float, str, float]:
    """Calculate road 3D offset, clearance, and stroke width by highway class."""
    h_class = str(props.get("highway", "")).lower()
    if "trunk" in h_class:
        return 6.0, 2.5, "#D62828", 5.0   # Major highway: elevated 2.5m, 6m clearance, bold red
    elif "primary" in h_class:
        return 5.5, 2.3, "#E76F51", 4.5   # Primary arterial: elevated 2.3m, orange-red
    elif "secondary" in h_class:
        return 4.5, 2.1, "#F4A261", 3.5   # Secondary road: elevated 2.1m, yellow-orange
    elif "tertiary" in h_class:
        return 3.5, 2.0, "#2A9D8F", 3.0   # Tertiary link: elevated 2.0m, teal
    return default_h, default_off, "#E9C46A", 2.5


# ---------------------------------------------------------------------------
# 3D TERRAIN LAYER GENERATOR
# ---------------------------------------------------------------------------
def process_layer_to_3d(
    layer_key: str,
    config: Dict[str, Any],
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None
) -> Tuple[Path, int]:
    """Loads a GeoJSON layer, applies 3D height/elevation_offset, and saves with _3d suffix."""
    in_filename = config["input_filename"]
    out_filename = config["output_filename"]

    in_path = locate_input_geojson(in_filename, input_dir)
    out_dir = output_dir or DOWNLOADS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_filename

    print(f"[*] Processing: {in_filename} -> {out_filename}")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    n_features = len(gdf)
    print(f"    - Loaded {n_features:,} features from {in_path.name}")

    if n_features == 0:
        print(f"    [!] Layer has 0 features, writing empty 3D GeoJSON.")
        out_path.write_text(gdf.to_json(indent=2), encoding="utf-8")
        return out_path, 0

    # 1. Compute Heights, Elevation Offsets, and Cesium Properties
    heights = []
    offsets = []
    extruded_heights = []
    clamp_flags = []
    classifications = []

    # Optional styling attributes
    custom_colors = []
    custom_widths = []

    for _, row in gdf.iterrows():
        props = row.to_dict()

        if layer_key == "flood_polygons":
            h = config["default_height"]
            off = config["default_offset"]
            heights.append(h)
            offsets.append(off)
            extruded_heights.append(round(off + h, 2))
            clamp_flags.append(True)
            classifications.append("CESIUM_3D_TILE")

        elif layer_key == "flooded_buildings":
            h = compute_building_height(props, config["default_height"])
            off = config["default_offset"]
            heights.append(round(h, 2))
            offsets.append(off)
            extruded_heights.append(round(off + h, 2))
            clamp_flags.append(False)
            classifications.append("NONE")

        elif layer_key == "flooded_roads":
            h, off, color, width = compute_road_offset_and_color(props, config["default_height"], config["default_offset"])
            heights.append(round(h, 2))
            offsets.append(round(off, 2))
            extruded_heights.append(round(off + h, 2))
            clamp_flags.append(False)
            classifications.append("NONE")
            custom_colors.append(color)
            custom_widths.append(width)

        elif layer_key == "flooded_facilities":
            h, color = compute_facility_height(props, config["default_height"])
            off = config["default_offset"]
            heights.append(round(h, 2))
            offsets.append(off)
            extruded_heights.append(round(off + h, 2))
            clamp_flags.append(False)
            classifications.append("NONE")
            custom_colors.append(color)

    # Inject calculated 3D attributes into GeoDataFrame
    gdf["height"] = heights
    gdf["elevation_offset"] = offsets
    gdf["extrudedHeight"] = extruded_heights
    gdf["clampToGround"] = clamp_flags
    gdf["classificationType"] = classifications

    # Inject Cesium styling cues
    style = config.get("style", {})
    if layer_key == "flood_polygons":
        gdf["fill"] = style["fill"]
        gdf["fill-opacity"] = style["fill-opacity"]
        gdf["stroke"] = style["stroke"]
        gdf["stroke-width"] = style["stroke-width"]
    elif layer_key == "flooded_buildings":
        gdf["fill"] = style["fill"]
        gdf["fill-opacity"] = style["fill-opacity"]
        gdf["stroke"] = style["stroke"]
        gdf["stroke-width"] = style["stroke-width"]
    elif layer_key == "flooded_roads":
        gdf["stroke"] = custom_colors
        gdf["stroke-width"] = custom_widths
        gdf["stroke-opacity"] = style.get("stroke-opacity", 0.95)
    elif layer_key == "flooded_facilities":
        gdf["marker-color"] = custom_colors
        gdf["marker-size"] = style.get("marker-size", "medium")

    # 2. Upgrade Geometries to 3D Coordinates (lon, lat, z) using Shapely
    # The coordinate z value represents the base altitude (elevation_offset) or extruded elevation
    z_coords = np.array(offsets, dtype=float)
    try:
        # Shapely 2.x vectorized force_3d
        gdf.geometry = shapely.force_3d(gdf.geometry, z=z_coords)
    except Exception as e:
        print(f"    [!] Warning setting 3D coordinates: {e}")

    # 3. Export to GeoJSON
    out_json = gdf.to_json(indent=2)
    out_path.write_text(out_json, encoding="utf-8")
    file_size_kb = out_path.stat().st_size / 1024
    print(f"    [+] Saved 3D layer: {out_path.name} ({file_size_kb:.1f} KB / {file_size_kb / 1024:.2f} MB)")

    # Save convenience copies to project root and workspace root
    convenience_paths = [
        SCRIPT_DIR.parent.parent / out_filename,
        Path.cwd() / out_filename,
    ]
    for alt_p in convenience_paths:
        if alt_p.resolve() != out_path.resolve():
            alt_p.write_text(out_json, encoding="utf-8")
            print(f"    [+] Convenience copy: {alt_p}")

    return out_path, n_features


# ---------------------------------------------------------------------------
# MAIN PIPELINE EXECUTION
# ---------------------------------------------------------------------------
def run_3d_terrain_pipeline(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None
) -> Dict[str, Tuple[Path, int]]:
    """Runs the complete Cesium 3D terrain preparation pipeline across all 4 layers."""
    t0 = time.time()
    print("=" * 75)
    print(" FLOODLENS AI — PREPARE CESIUM-COMPATIBLE 3D TERRAIN LAYERS")
    print("=" * 75)
    print("[*] Target Engine : CesiumJS / Cesium 3D Tiles / WebGL 3D GIS")
    print("[*] Coordinate Sys: WGS84 Geographic with 3D Z-Extrusion (EPSG:4326 + Height)")

    results = {}
    for layer_key, cfg in LAYER_3D_CONFIGS.items():
        print()
        out_path, count = process_layer_to_3d(layer_key, cfg, input_dir, output_dir)
        results[layer_key] = (out_path, count)

    dt = time.time() - t0
    print("\n" + "=" * 75)
    print(" 3D TERRAIN LAYERS GENERATION SUMMARY")
    print("=" * 75)
    print(f"{'Layer Key':<22} | {'Output File':<30} | {'Features':>10} | {'Height (m)':<12} | {'Offset (m)'}")
    print("-" * 90)

    for layer_key, (out_path, count) in results.items():
        cfg = LAYER_3D_CONFIGS[layer_key]
        h_str = f"{cfg['default_height']}m"
        off_str = f"{cfg['default_offset']}m"
        print(f"{layer_key:<22} | {out_path.name:<30} | {count:>10,} | {h_str:<12} | {off_str}")

    print("\n[+] All 4 layers prepared with Cesium 3D attributes & coordinates!")
    print(f"[+] Total execution time: {dt:.2f} seconds.")
    print("=" * 75)
    return results


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Prepare Cesium-compatible 3D terrain layers with heights and elevation offsets."
    )
    parser.add_argument(
        "--input-dir", "-i",
        type=str,
        default=None,
        help="Directory containing generated 2D GeoJSON outputs."
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Directory where _3d GeoJSON files should be written."
    )

    args = parser.parse_args()

    in_dir = Path(args.input_dir).resolve() if args.input_dir else None
    out_dir = Path(args.output_dir).resolve() if args.output_dir else None

    run_3d_terrain_pipeline(input_dir=in_dir, output_dir=out_dir)


if __name__ == "__main__":
    main()
