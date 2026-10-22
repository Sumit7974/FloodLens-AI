"""
intersect_settlements.py
========================
FloodLens AI — Settlement & Building Flood Intersection Pipeline
----------------------------------------------------------------
Fetches building footprints and settlement locations for the Koshi River
Basin bounding box [86.5, 26.2, 88.2, 27.8] via the OpenStreetMap Overpass
API (using requests with multi-endpoint fallback and local caching).

Performs spatial intersection with Sentinel-2 flood polygons
(flood_polygons.geojson) using geopandas to calculate building-level flood
impact and exports the result as flooded_buildings.geojson.

Author : FloodLens AI Team
"""

import os
import sys
import json
import time
import argparse
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Ensure standard UTF-8 console output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
import numpy as np
from shapely.geometry import Point, Polygon, shape, box
from shapely.strtree import STRtree
import geopandas as gpd


# ---------------------------------------------------------------------------
# DEFAULT PARAMETERS & PATHS
# ---------------------------------------------------------------------------
DEFAULT_BBOX = [86.5, 26.2, 88.2, 27.8]  # [min_lon, min_lat, max_lon, max_lat]
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

SETTLEMENTS_CACHE_FILE = DOWNLOADS_DIR / "osm_settlements_cache.json"
BUILDINGS_CACHE_FILE = DOWNLOADS_DIR / "osm_buildings_cache.json"
DEFAULT_OUTPUT_GEOJSON = DOWNLOADS_DIR / "flooded_buildings.geojson"

OVERPASS_ENDPOINTS = [
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

REQUEST_HEADERS = {
    "User-Agent": "FloodLensAI/1.0 (contact@floodlens.org)"
}


# ---------------------------------------------------------------------------
# OVERPASS API CLIENT WITH MULTI-ENDPOINT FALLBACK
# ---------------------------------------------------------------------------
def query_overpass(query: str, timeout_sec: int = 40) -> Optional[Dict[str, Any]]:
    """Query Overpass API with automatic failover across public mirror endpoints."""
    for ep in OVERPASS_ENDPOINTS:
        try:
            # Try POST first
            r = requests.post(ep, data={"data": query}, headers=REQUEST_HEADERS, timeout=timeout_sec)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    pass
            elif r.status_code in (403, 429, 502, 504):
                # Try GET as secondary option on this endpoint
                url = f"{ep}?data={urllib.parse.quote(query)}"
                rg = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout_sec)
                if rg.status_code == 200:
                    try:
                        return rg.json()
                    except Exception:
                        pass
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# SETTLEMENT FETCHER
# ---------------------------------------------------------------------------
def fetch_settlements(bbox: List[float], use_cache: bool = True) -> List[Dict[str, Any]]:
    """Fetch settlement locations (cities, towns, villages, hamlets) within bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox

    # Check cache first if requested
    if use_cache and SETTLEMENTS_CACHE_FILE.is_file() and SETTLEMENTS_CACHE_FILE.stat().st_size > 1000:
        try:
            cached_data = json.loads(SETTLEMENTS_CACHE_FILE.read_text(encoding="utf-8"))
            if len(cached_data) > 0:
                print(f"[+] Loaded {len(cached_data):,} settlements from local cache.")
                return cached_data
        except Exception as e:
            print(f"[!] Warning reading settlement cache: {e}")

    print(f"[*] Querying Overpass API for settlements in bbox [{min_lon}, {min_lat}, {max_lon}, {max_lat}]...")
    q = f"""
    [out:json][timeout:45];
    (
      node["place"~"city|town|village|hamlet|suburb"]({min_lat}, {min_lon}, {max_lat}, {max_lon});
    );
    out body;
    """

    res = query_overpass(q, timeout_sec=45)
    if res and "elements" in res:
        elements = res["elements"]
        print(f"[+] Retrieved {len(elements):,} settlements from Overpass API.")
        try:
            SETTLEMENTS_CACHE_FILE.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return elements

    # Fallback to cache if network query failed
    if SETTLEMENTS_CACHE_FILE.is_file():
        print("[!] Live query timed out or throttled. Falling back to cached settlements...")
        return json.loads(SETTLEMENTS_CACHE_FILE.read_text(encoding="utf-8"))

    print("[!] Warning: Could not retrieve settlements and no cache is present.")
    return []


# ---------------------------------------------------------------------------
# BUILDING FETCHER
# ---------------------------------------------------------------------------
def fetch_buildings(
    bbox: List[float],
    affected_settlements: List[Dict[str, Any]],
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Fetch building footprints for the flood-affected area.
    Queries buildings surrounding settlements that overlap or lie within proximity
    of flood polygons, falling back to local cache if available.
    """
    # Check cache first
    if use_cache and BUILDINGS_CACHE_FILE.is_file() and BUILDINGS_CACHE_FILE.stat().st_size > 1000:
        try:
            cached_b = json.loads(BUILDINGS_CACHE_FILE.read_text(encoding="utf-8"))
            if len(cached_b) > 0:
                print(f"[+] Loaded {len(cached_b):,} building footprints from local cache.")
                return cached_b
        except Exception as e:
            print(f"[!] Warning reading building cache: {e}")

    print(f"[*] Querying Overpass API for building footprints across flood-affected zones...")
    all_buildings = []
    seen_ids = set()

    for i, s in enumerate(affected_settlements[:20]):
        lat, lon = s["lat"], s["lon"]
        d = 0.012  # ~1.3km box around each flood-affected settlement
        q = f"""
        [out:json][timeout:30];
        (
          way["building"]({lat-d:.4f}, {lon-d:.4f}, {lat+d:.4f}, {lon+d:.4f});
        );
        out geom;
        """
        try:
            time.sleep(1.0)
            res = query_overpass(q, timeout_sec=30)
            if res and "elements" in res:
                elems = res["elements"]
                new_elems = [e for e in elems if e["id"] not in seen_ids]
                for e in new_elems:
                    seen_ids.add(e["id"])
                    e["settlement_name"] = s.get("name", "Settlement")
                all_buildings.extend(new_elems)
                print(f"    [{i+1}/{min(20, len(affected_settlements))}] {s.get('name')}: +{len(new_elems):,} buildings (Total: {len(all_buildings):,})")
        except Exception as e:
            print(f"    [{i+1}] Error querying {s.get('name')}: {e}")

    if all_buildings:
        try:
            BUILDINGS_CACHE_FILE.write_text(json.dumps(all_buildings, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[+] Saved {len(all_buildings):,} building footprints to local cache.")
        except Exception:
            pass
        return all_buildings

    if BUILDINGS_CACHE_FILE.is_file():
        print("[!] Live building query timed out or throttled. Falling back to cached buildings...")
        return json.loads(BUILDINGS_CACHE_FILE.read_text(encoding="utf-8"))

    return []


# ---------------------------------------------------------------------------
# FLOOD POLYGON LOCATOR & LOADER
# ---------------------------------------------------------------------------
def load_flood_polygons(custom_path: Optional[str] = None) -> gpd.GeoDataFrame:
    """Locate and load flood_polygons.geojson into a GeoDataFrame."""
    candidate_paths = [
        Path(custom_path) if custom_path else None,
        SCRIPT_DIR.parent.parent / "flood_polygons.geojson",
        SCRIPT_DIR / "flood_polygons.geojson",
        DOWNLOADS_DIR / "flood_polygons.geojson",
        Path.cwd() / "flood_polygons.geojson",
    ]

    selected_path = None
    for p in candidate_paths:
        if p and p.is_file() and p.stat().st_size > 1000:
            selected_path = p.resolve()
            break

    if not selected_path:
        raise FileNotFoundError(
            "Could not find 'flood_polygons.geojson'. Please run vectorize_flood.py first."
        )

    print(f"[*] Loading flood polygons from: {selected_path} ...")
    with open(selected_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
    print(f"[+] Loaded {len(gdf):,} flood polygons into GeoDataFrame.")
    return gdf


# ---------------------------------------------------------------------------
# MAIN INTERSECTION PIPELINE
# ---------------------------------------------------------------------------
def run_intersection(
    bbox: List[float] = DEFAULT_BBOX,
    flood_geojson_path: Optional[str] = None,
    output_geojson_path: Optional[Path] = None,
    use_cache: bool = True
) -> gpd.GeoDataFrame:
    """Executes the settlement and building flood intersection pipeline."""
    t0 = time.time()
    min_lon, min_lat, max_lon, max_lat = bbox

    print("=" * 75)
    print(" FLOODLENS AI — SETTLEMENT & BUILDING FLOOD INTERSECTION PIPELINE")
    print("=" * 75)
    print(f"[*] Target Basin Bounding Box : Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]")
    print(f"[*] Region                   : Koshi River Basin, Eastern Nepal")

    # 1. Load Flood Polygons
    flood_gdf = load_flood_polygons(flood_geojson_path)
    flood_bounds = flood_gdf.total_bounds  # [minx, miny, maxx, maxy]
    print(f"    - Flood Envelope Extent   : Lon [{flood_bounds[0]:.4f}, {flood_bounds[2]:.4f}], "
          f"Lat [{flood_bounds[1]:.4f}, {flood_bounds[3]:.4f}]")

    # 2. Fetch Settlements
    settlements_raw = fetch_settlements(bbox, use_cache=use_cache)
    settlement_records = []
    for s in settlements_raw:
        lat = s.get("lat")
        lon = s.get("lon")
        if lat is None or lon is None:
            continue
        tags = s.get("tags", {})
        name = tags.get("name:en") or tags.get("name") or "Unnamed"
        place = tags.get("place", "settlement")
        settlement_records.append({
            "osm_id": s["id"],
            "name": name,
            "place": place,
            "lat": lat,
            "lon": lon,
            "geometry": Point(lon, lat),
        })

    settlements_gdf = gpd.GeoDataFrame(settlement_records, crs="EPSG:4326")
    print(f"[+] Created Settlements GeoDataFrame with {len(settlements_gdf):,} features.")

    # 3. Identify Flood-Affected Settlements
    print("[*] Assessing settlement flood exposure (within 1.5 km buffer of flood extent)...")
    # Spatial indexing for flood polygons
    flood_geoms = [geom for geom in flood_gdf.geometry if geom and not geom.is_empty]
    flood_tree = STRtree(flood_geoms)

    affected_settlements = []
    for _, s in settlements_gdf.iterrows():
        pt = s["geometry"]
        b = pt.buffer(0.015)  # ~1.5 km
        matches = flood_tree.query(b)
        for idx in matches:
            if flood_geoms[idx].intersects(b):
                affected_settlements.append(s.to_dict())
                break

    print(f"[+] Identified {len(affected_settlements):,} settlements in the flood hazard corridor.")
    print("    Sample flood-affected settlements:")
    for s in affected_settlements[:8]:
        print(f"     • {s['name']} ({s['place']}) at {s['lat']:.4f}°N, {s['lon']:.4f}°E")

    # Save affected settlements GeoJSON
    affected_settlements_file = DOWNLOADS_DIR / "affected_settlements.geojson"
    if affected_settlements:
        aff_gdf = gpd.GeoDataFrame(affected_settlements, crs="EPSG:4326")
        aff_gdf.to_json()
        affected_settlements_file.write_text(aff_gdf.to_json(indent=2), encoding="utf-8")
        print(f"[+] Saved {len(aff_gdf):,} affected settlements to: {affected_settlements_file}")

    # 4. Fetch Building Footprints
    buildings_raw = fetch_buildings(bbox, affected_settlements, use_cache=use_cache)
    print(f"[*] Parsing and validating {len(buildings_raw):,} OSM building footprints...")
    building_records = []
    for b in buildings_raw:
        coords = b.get("geometry", [])
        if len(coords) < 3:
            continue
        poly_pts = [(p["lon"], p["lat"]) for p in coords]
        try:
            poly = Polygon(poly_pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area <= 0:
                continue

            tags = b.get("tags", {})
            building_records.append({
                "osm_id": b["id"],
                "settlement": b.get("settlement_name") or tags.get("addr:city") or "Nearby Settlement",
                "building": tags.get("building", "yes"),
                "name": tags.get("name", "Unnamed"),
                "amenity": tags.get("amenity", "none"),
                "geometry": poly,
            })
        except Exception:
            continue

    buildings_gdf = gpd.GeoDataFrame(building_records, crs="EPSG:4326")
    print(f"[+] Created Buildings GeoDataFrame with {len(buildings_gdf):,} valid geometries.")

    # 5. Intersect Buildings with Flood Polygons using GeoPandas
    print("[*] Performing spatial join (gpd.sjoin) to detect building-flood intersections...")
    # Perform spatial join using predicate 'intersects'
    intersected_raw = gpd.sjoin(
        buildings_gdf,
        flood_gdf[["geometry", "id", "class", "area_m2"]].rename(columns={"id": "flood_poly_id"}),
        how="inner",
        predicate="intersects"
    )

    # Remove duplicates where a building polygon touches multiple adjacent flood polygons
    flooded_buildings_gdf = intersected_raw.drop_duplicates(subset=["osm_id"]).copy()

    # Calculate accurate metric area in UTM Zone 45N (EPSG:32645)
    print("[*] Calculating metric building footprint areas (m²)...")
    flooded_utm = flooded_buildings_gdf.to_crs(epsg=32645)
    flooded_buildings_gdf["area_sqm"] = [round(float(a), 1) for a in flooded_utm.geometry.area]
    flooded_buildings_gdf["impact_status"] = "inundated"

    # Clean and order attributes
    output_cols = [
        "osm_id", "settlement", "building", "name", "amenity",
        "area_sqm", "impact_status", "flood_poly_id", "geometry"
    ]
    flooded_buildings_gdf = flooded_buildings_gdf[[c for c in output_cols if c in flooded_buildings_gdf.columns]]

    # 6. Calculate Impact Metrics & Statistics
    num_flooded = len(flooded_buildings_gdf)
    total_buildings = len(buildings_gdf)
    total_flooded_area_m2 = flooded_buildings_gdf["area_sqm"].sum() if num_flooded > 0 else 0.0

    print("\n" + "=" * 75)
    print(" FLOOD DAMAGE & IMPACT ASSESSMENT RESULTS")
    print("=" * 75)
    print(f"[*] Geographic Bounding Box        : [{min_lon}, {min_lat}, {max_lon}, {max_lat}]")
    print(f"[*] Total Settlements Evaluated    : {len(settlements_gdf):,}")
    print(f"[*] Settlements in Flood Corridor  : {len(affected_settlements):,}")
    print(f"[*] Total Building Footprints      : {total_buildings:,}")
    print(f"[*] TOTAL AFFECTED BUILDINGS       : {num_flooded:,}")
    print(f"[*] Total Inundated Building Area  : {total_flooded_area_m2:,.1f} m² ({total_flooded_area_m2 / 10000.0:.2f} ha)")

    if num_flooded > 0:
        print("\n[*] Affected Buildings by Settlement:")
        settlement_counts = flooded_buildings_gdf["settlement"].value_counts()
        for s_name, count in settlement_counts.items():
            print(f"    • {s_name:<25}: {count:>4} buildings")

        print("\n[*] Affected Buildings by Category:")
        cat_counts = flooded_buildings_gdf["building"].value_counts()
        for cat_name, count in cat_counts.items():
            print(f"    • {cat_name:<25}: {count:>4} buildings")

    # 7. Save Output GeoJSON
    out_path = output_geojson_path or DEFAULT_OUTPUT_GEOJSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n[*] Exporting affected buildings to: {out_path} ...")
    geojson_data = flooded_buildings_gdf.to_json(indent=2)
    out_path.write_text(geojson_data, encoding="utf-8")
    print(f"[+] Output GeoJSON successfully saved ({out_path.stat().st_size / 1024:.1f} KB).")

    # Also save convenience copies to project root and workspace root
    alt_paths = [
        SCRIPT_DIR.parent.parent / "flooded_buildings.geojson",
        Path.cwd() / "flooded_buildings.geojson",
    ]
    for alt in alt_paths:
        if alt.resolve() != out_path.resolve():
            alt.write_text(geojson_data, encoding="utf-8")
            print(f"[+] Convenience copy saved to: {alt}")

    dt = time.time() - t0
    print(f"[+] Intersection workflow finished in {dt:.2f} seconds.")
    print("=" * 75)
    return flooded_buildings_gdf


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Intersect OSM buildings and settlements with flood polygons."
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=DEFAULT_BBOX,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Bounding box [min_lon, min_lat, max_lon, max_lat]."
    )
    parser.add_argument(
        "--flood-polygons", "-f",
        type=str,
        default=None,
        help="Path to flood_polygons.geojson."
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Path to output flooded_buildings.geojson."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and re-query Overpass API."
    )

    args = parser.parse_args()

    out_file = Path(args.output).resolve() if args.output else DEFAULT_OUTPUT_GEOJSON

    run_intersection(
        bbox=args.bbox,
        flood_geojson_path=args.flood_polygons,
        output_geojson_path=out_file,
        use_cache=not args.no_cache
    )


if __name__ == "__main__":
    main()
