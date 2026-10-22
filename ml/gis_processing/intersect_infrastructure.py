"""
intersect_infrastructure.py
===========================
FloodLens AI — Road & Critical Facility Flood Exposure Pipeline
---------------------------------------------------------------
Fetches the road transportation network (highways) and critical facilities
(hospitals, clinics, schools, police stations) across the Koshi River Basin
bounding box [86.5, 26.2, 88.2, 27.8] using the OpenStreetMap Overpass API
(with multi-endpoint failover and local caching).

Performs spatial intersection with Sentinel-2 flood polygons (flood_polygons.geojson)
using geopandas and shapely to calculate infrastructure disruption, metric lengths,
and facility vulnerability.

Outputs:
    flooded_roads.geojson      - Inundated road segments with metric length (m, km)
    flooded_facilities.geojson - Inundated & high-risk critical facilities

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
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, shape
from shapely.strtree import STRtree
import geopandas as gpd


# ---------------------------------------------------------------------------
# DEFAULT PARAMETERS & PATHS
# ---------------------------------------------------------------------------
DEFAULT_BBOX = [86.5, 26.2, 88.2, 27.8]  # [min_lon, min_lat, max_lon, max_lat]
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

ROADS_CACHE_FILE = DOWNLOADS_DIR / "osm_roads_cache.json"
FACILITIES_CACHE_FILE = DOWNLOADS_DIR / "osm_facilities_cache.json"

DEFAULT_ROADS_OUT = DOWNLOADS_DIR / "flooded_roads.geojson"
DEFAULT_FACILITIES_OUT = DOWNLOADS_DIR / "flooded_facilities.geojson"

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
def query_overpass(query: str, timeout_sec: int = 45) -> Optional[Dict[str, Any]]:
    """Query Overpass API with automatic failover across public mirror endpoints."""
    for ep in OVERPASS_ENDPOINTS:
        try:
            r = requests.post(ep, data={"data": query}, headers=REQUEST_HEADERS, timeout=timeout_sec)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    pass
            elif r.status_code in (403, 429, 502, 504):
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
# CRITICAL FACILITIES FETCHER
# ---------------------------------------------------------------------------
def fetch_critical_facilities(bbox: List[float], use_cache: bool = True) -> List[Dict[str, Any]]:
    """Fetch hospitals, clinics, schools, and police stations within bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox

    if use_cache and FACILITIES_CACHE_FILE.is_file() and FACILITIES_CACHE_FILE.stat().st_size > 1000:
        try:
            cached = json.loads(FACILITIES_CACHE_FILE.read_text(encoding="utf-8"))
            if len(cached) > 0:
                print(f"[+] Loaded {len(cached):,} critical facilities from local cache.")
                return cached
        except Exception as e:
            print(f"[!] Warning reading facilities cache: {e}")

    print(f"[*] Querying Overpass API for critical facilities in bbox [{min_lon}, {min_lat}, {max_lon}, {max_lat}]...")
    q = f"""
    [out:json][timeout:45];
    (
      node["amenity"~"hospital|clinic|school|police"]({min_lat}, {min_lon}, {max_lat}, {max_lon});
      way["amenity"~"hospital|clinic|school|police"]({min_lat}, {min_lon}, {max_lat}, {max_lon});
    );
    out geom;
    """

    res = query_overpass(q, timeout_sec=45)
    if res and "elements" in res:
        elements = res["elements"]
        print(f"[+] Retrieved {len(elements):,} critical facilities from Overpass API.")
        try:
            FACILITIES_CACHE_FILE.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return elements

    if FACILITIES_CACHE_FILE.is_file():
        print("[!] Live query timed out or throttled. Falling back to cached facilities...")
        return json.loads(FACILITIES_CACHE_FILE.read_text(encoding="utf-8"))

    print("[!] Warning: Could not retrieve critical facilities and no cache is present.")
    return []


# ---------------------------------------------------------------------------
# ROAD NETWORK FETCHER
# ---------------------------------------------------------------------------
def fetch_road_network(
    bbox: List[float],
    flood_bounds: Tuple[float, float, float, float],
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """Fetch arterial and major roads within the flood hazard envelope."""
    if use_cache and ROADS_CACHE_FILE.is_file() and ROADS_CACHE_FILE.stat().st_size > 1000:
        try:
            cached = json.loads(ROADS_CACHE_FILE.read_text(encoding="utf-8"))
            if len(cached) > 0:
                print(f"[+] Loaded {len(cached):,} road segments from local cache.")
                return cached
        except Exception as e:
            print(f"[!] Warning reading roads cache: {e}")

    # Use the flood extent envelope to focus on vulnerable transportation links
    min_lon, min_lat, max_lon, max_lat = flood_bounds
    # Add a small 2km margin (~0.02 deg)
    pad = 0.02
    query_box = (
        max(min_lat - pad, bbox[1]),
        max(min_lon - pad, bbox[0]),
        min(max_lat + pad, bbox[3]),
        min(max_lon + pad, bbox[2]),
    )

    print(f"[*] Querying Overpass API for road network in flood hazard envelope {query_box}...")
    q = f"""
    [out:json][timeout:45];
    (
      way["highway"~"motorway|trunk|primary|secondary|tertiary"]({query_box[0]:.4f}, {query_box[1]:.4f}, {query_box[2]:.4f}, {query_box[3]:.4f});
    );
    out geom;
    """

    res = query_overpass(q, timeout_sec=45)
    if res and "elements" in res:
        elements = res["elements"]
        print(f"[+] Retrieved {len(elements):,} road segments from Overpass API.")
        try:
            ROADS_CACHE_FILE.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return elements

    if ROADS_CACHE_FILE.is_file():
        print("[!] Live road query timed out or throttled. Falling back to cached roads...")
        return json.loads(ROADS_CACHE_FILE.read_text(encoding="utf-8"))

    print("[!] Warning: Could not retrieve roads and no cache is present.")
    return []


# ---------------------------------------------------------------------------
# FLOOD POLYGON LOADER
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
# INFRASTRUCTURE INTERSECTION WORKFLOW
# ---------------------------------------------------------------------------
def run_infrastructure_intersection(
    bbox: List[float] = DEFAULT_BBOX,
    flood_geojson_path: Optional[str] = None,
    roads_out_path: Optional[Path] = None,
    facilities_out_path: Optional[Path] = None,
    use_cache: bool = True
) -> Tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Intersects road network and critical facilities with flood polygons."""
    t0 = time.time()
    min_lon, min_lat, max_lon, max_lat = bbox

    print("=" * 75)
    print(" FLOODLENS AI — ROAD & FACILITY FLOOD EXPOSURE PIPELINE")
    print("=" * 75)
    print(f"[*] Geographic Bounding Box : Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]")
    print(f"[*] Study Region           : Koshi River Basin, Eastern Nepal")

    # 1. Load Flood Polygons
    flood_gdf = load_flood_polygons(flood_geojson_path)
    flood_bounds = flood_gdf.total_bounds  # [minx, miny, maxx, maxy]
    print(f"    - Flood Envelope Bounds : Lon [{flood_bounds[0]:.4f}, {flood_bounds[2]:.4f}], "
          f"Lat [{flood_bounds[1]:.4f}, {flood_bounds[3]:.4f}]")

    flood_geoms = [geom for geom in flood_gdf.geometry if geom and not geom.is_empty]
    flood_tree = STRtree(flood_geoms)

    # 2. Process Critical Facilities
    print("\n" + "-" * 75)
    print(" 1. CRITICAL FACILITIES EXPOSURE ANALYSIS")
    print("-" * 75)
    raw_facilities = fetch_critical_facilities(bbox, use_cache=use_cache)
    print(f"[*] Parsing and spatially indexing {len(raw_facilities):,} critical facilities...")

    fac_records = []
    for f in raw_facilities:
        t = f.get("type")
        tags = f.get("tags", {})
        amenity = tags.get("amenity", "facility")
        name = tags.get("name:en") or tags.get("name") or f"Unnamed {amenity.capitalize()}"

        geom = None
        if t == "node":
            lat, lon = f.get("lat"), f.get("lon")
            if lat is not None and lon is not None:
                geom = Point(lon, lat)
        elif t == "way" and "geometry" in f:
            pts = f["geometry"]
            if len(pts) >= 3:
                poly = Polygon([(p["lon"], p["lat"]) for p in pts])
                if not poly.is_valid:
                    poly = poly.buffer(0)
                geom = poly
            elif len(pts) >= 1:
                geom = Point(pts[0]["lon"], pts[0]["lat"])

        if geom is None or geom.is_empty:
            continue

        # Spatial check against flood polygons
        matches = flood_tree.query(geom)
        is_direct = any(geom.intersects(flood_geoms[idx]) for idx in matches)

        # Buffer checks (100m ~ 0.001 deg, 500m ~ 0.005 deg)
        b500 = geom.buffer(0.005)
        m500 = flood_tree.query(b500)
        is_500 = any(flood_geoms[idx].intersects(b500) for idx in m500)

        if is_direct or is_500:
            if is_direct:
                status = "inundated"
            else:
                b100 = geom.buffer(0.001)
                is_100 = any(flood_geoms[idx].intersects(b100) for idx in flood_tree.query(b100))
                status = "high_risk_100m" if is_100 else "moderate_risk_500m"

            fac_records.append({
                "osm_id": f["id"],
                "amenity": amenity,
                "name": name,
                "operator": tags.get("operator", "public/private"),
                "emergency": tags.get("emergency", "no"),
                "impact_status": status,
                "geometry": geom,
            })

    flooded_facilities_gdf = gpd.GeoDataFrame(fac_records, crs="EPSG:4326")
    print(f"[+] Total Exposed Critical Facilities: {len(flooded_facilities_gdf):,}")

    status_counts = flooded_facilities_gdf["impact_status"].value_counts()
    for s_name, c in status_counts.items():
        print(f"    • {s_name:<22}: {c:>4} facilities")

    print("\n    Breakdown by Facility Category:")
    cat_counts = flooded_facilities_gdf["amenity"].value_counts()
    for a_name, c in cat_counts.items():
        print(f"    • {a_name:<22}: {c:>4} facilities")

    # 3. Process Road Transportation Network
    print("\n" + "-" * 75)
    print(" 2. ROAD TRANSPORTATION NETWORK INUNDATION ANALYSIS")
    print("-" * 75)
    raw_roads = fetch_road_network(bbox, tuple(flood_bounds), use_cache=use_cache)
    print(f"[*] Parsing and intersecting {len(raw_roads):,} major road segments...")

    road_records = []
    for r in raw_roads:
        pts = r.get("geometry", [])
        if len(pts) < 2:
            continue
        try:
            line = LineString([(p["lon"], p["lat"]) for p in pts])
            matches = flood_tree.query(line)
            intersecting_indices = [idx for idx in matches if line.intersects(flood_geoms[idx])]

            if intersecting_indices:
                tags = r.get("tags", {})
                name = tags.get("name:en") or tags.get("name") or "Unnamed Arterial Road"
                ref = tags.get("ref", "")
                highway = tags.get("highway", "road")

                road_records.append({
                    "osm_id": r["id"],
                    "highway": highway,
                    "name": name,
                    "ref": ref,
                    "surface": tags.get("surface", "paved"),
                    "bridge": tags.get("bridge", "no"),
                    "impact_status": "submerged",
                    "geometry": line,
                })
        except Exception:
            continue

    flooded_roads_gdf = gpd.GeoDataFrame(road_records, crs="EPSG:4326")

    # Calculate metric lengths in UTM Zone 45N (EPSG:32645)
    print("[*] Calculating metric road segment lengths in UTM Zone 45N (meters)...")
    if len(flooded_roads_gdf) > 0:
        roads_utm = flooded_roads_gdf.to_crs(epsg=32645)
        flooded_roads_gdf["length_m"] = [round(float(l), 1) for l in roads_utm.geometry.length]
        flooded_roads_gdf["length_km"] = [round(float(l) / 1000.0, 3) for l in roads_utm.geometry.length]
    else:
        flooded_roads_gdf["length_m"] = []
        flooded_roads_gdf["length_km"] = []

    total_roads_flooded = len(flooded_roads_gdf)
    total_km_flooded = flooded_roads_gdf["length_km"].sum() if total_roads_flooded > 0 else 0.0

    print(f"[+] Total Inundated Road Segments : {total_roads_flooded:,}")
    print(f"[+] Total Cut-Off Road Length     : {total_km_flooded:.2f} km ({total_km_flooded * 1000:,.0f} m)")

    print("\n    Inundated Road Network by Classification:")
    h_counts = flooded_roads_gdf["highway"].value_counts()
    for h_type, count in h_counts.items():
        km = flooded_roads_gdf[flooded_roads_gdf["highway"] == h_type]["length_km"].sum()
        print(f"    • {h_type:<18}: {count:>3} segments ({km:>6.2f} km)")

    # 4. Export Outputs to Web/Mobile Compatible GeoJSON (RFC 7946)
    print("\n" + "-" * 75)
    print(" 3. EXPORTING WEB & MOBILE GEODATA LAYERS")
    print("-" * 75)

    r_out = roads_out_path or DEFAULT_ROADS_OUT
    f_out = facilities_out_path or DEFAULT_FACILITIES_OUT

    r_out.parent.mkdir(parents=True, exist_ok=True)
    f_out.parent.mkdir(parents=True, exist_ok=True)

    # Save Roads
    roads_json = flooded_roads_gdf.to_json(indent=2)
    r_out.write_text(roads_json, encoding="utf-8")
    print(f"[+] Saved Inundated Roads: {r_out} ({r_out.stat().st_size / 1024:.1f} KB)")

    # Save Facilities
    facilities_json = flooded_facilities_gdf.to_json(indent=2)
    f_out.write_text(facilities_json, encoding="utf-8")
    print(f"[+] Saved Exposed Facilities: {f_out} ({f_out.stat().st_size / 1024:.1f} KB)")

    # Convenience copies in project root and workspace root
    convenience_targets = [
        (SCRIPT_DIR.parent.parent / "flooded_roads.geojson", roads_json),
        (SCRIPT_DIR.parent.parent / "flooded_facilities.geojson", facilities_json),
        (Path.cwd() / "flooded_roads.geojson", roads_json),
        (Path.cwd() / "flooded_facilities.geojson", facilities_json),
    ]

    for p_tgt, json_str in convenience_targets:
        if p_tgt.resolve() not in (r_out.resolve(), f_out.resolve()):
            p_tgt.write_text(json_str, encoding="utf-8")
            print(f"[+] Convenience copy saved to: {p_tgt}")

    dt = time.time() - t0
    print("\n" + "=" * 75)
    print(f" INFRASTRUCTURE INTERSECTION COMPLETED SUCCESSFULLY IN {dt:.2f}s")
    print("=" * 75)
    return flooded_roads_gdf, flooded_facilities_gdf


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Intersect OSM road network and critical facilities with flood polygons."
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
        "--roads-out", "-r",
        type=str,
        default=None,
        help="Path to output flooded_roads.geojson."
    )
    parser.add_argument(
        "--facilities-out", "-c",
        type=str,
        default=None,
        help="Path to output flooded_facilities.geojson."
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and re-query Overpass API."
    )

    args = parser.parse_args()

    r_path = Path(args.roads_out).resolve() if args.roads_out else None
    f_path = Path(args.facilities_out).resolve() if args.facilities_out else None

    run_infrastructure_intersection(
        bbox=args.bbox,
        flood_geojson_path=args.flood_polygons,
        roads_out_path=r_path,
        facilities_out_path=f_path,
        use_cache=not args.no_cache
    )


if __name__ == "__main__":
    main()
