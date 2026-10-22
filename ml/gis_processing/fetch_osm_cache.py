import os
import sys
import json
import time
import requests
from pathlib import Path
from shapely.geometry import Point, Polygon, shape
from shapely.strtree import STRtree

# Reconfigure stdout to utf-8 to avoid Windows cp1252 charmap errors
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

SETTLEMENTS_CACHE = DOWNLOADS_DIR / "osm_settlements_cache.json"
BUILDINGS_CACHE = DOWNLOADS_DIR / "osm_buildings_cache.json"

ep = "https://overpass.openstreetmap.fr/api/interpreter"
headers = {"User-Agent": "FloodLensAI/1.0 (contact@floodlens.org)"}

# 1. Fetch Settlements
print("[*] Fetching settlements across Koshi River Basin [86.5, 26.2, 88.2, 27.8]...", flush=True)
q_settlements = """
[out:json][timeout:45];
(
  node["place"~"city|town|village|hamlet|suburb"](26.2, 86.5, 27.8, 88.2);
);
out body;
"""
r = requests.post(ep, data={"data": q_settlements}, headers=headers, timeout=45)
if r.status_code == 200:
    settlements = r.json().get("elements", [])
    print(f"[+] Successfully fetched {len(settlements)} settlements.", flush=True)
    SETTLEMENTS_CACHE.write_text(json.dumps(settlements, ensure_ascii=False, indent=2), encoding="utf-8")
else:
    print(f"[!] Failed to fetch settlements: status {r.status_code}", flush=True)
    if SETTLEMENTS_CACHE.exists():
        settlements = json.loads(SETTLEMENTS_CACHE.read_text(encoding="utf-8"))
    else:
        settlements = []

# 2. Identify Settlements in Flood Zone
print("[*] Loading flood polygons to find flood-affected settlements...", flush=True)
flood_geojson_path = SCRIPT_DIR.parent.parent / "flood_polygons.geojson"
if not flood_geojson_path.exists():
    flood_geojson_path = DOWNLOADS_DIR / "flood_polygons.geojson"

with open(flood_geojson_path, "r", encoding="utf-8") as f:
    flood_data = json.load(f)

flood_geoms = [shape(f["geometry"]) for f in flood_data["features"] if not shape(f["geometry"]).is_empty]
print(f"[+] Loaded {len(flood_geoms)} flood polygons. Indexing...", flush=True)
tree = STRtree(flood_geoms)

affected_settlements = []
for s in settlements:
    pt = Point(s["lon"], s["lat"])
    # 1.5 km buffer ~ 0.015 deg
    b = pt.buffer(0.015)
    matches = tree.query(b)
    for idx in matches:
        if flood_geoms[idx].intersects(b):
            name = s.get("tags", {}).get("name:en") or s.get("tags", {}).get("name", "Unnamed")
            affected_settlements.append({
                "id": s["id"],
                "name": name,
                "place": s.get("tags", {}).get("place", "settlement"),
                "lat": s["lat"],
                "lon": s["lon"]
            })
            break

print(f"[+] Identified {len(affected_settlements)} settlements in/near flood zones.", flush=True)

# 3. Fetch Buildings around Affected Settlements
print("[*] Fetching building footprints around flood-affected settlements...", flush=True)
all_buildings = []
seen_building_ids = set()

# Select prominent settlements in the flood zones
for i, s in enumerate(affected_settlements[:15]):
    lat, lon = s["lat"], s["lon"]
    d = 0.012  # ~1.3km box around settlement
    q_b = f"""
    [out:json][timeout:30];
    (
      way["building"]({lat-d:.4f}, {lon-d:.4f}, {lat+d:.4f}, {lon+d:.4f});
    );
    out geom;
    """
    try:
        time.sleep(1.2)
        rb = requests.post(ep, data={"data": q_b}, headers=headers, timeout=30)
        if rb.status_code == 200:
            elems = rb.json().get("elements", [])
            new_elems = [e for e in elems if e["id"] not in seen_building_ids]
            for e in new_elems:
                seen_building_ids.add(e["id"])
                e["settlement_name"] = s["name"]
            all_buildings.extend(new_elems)
            print(f"    [{i+1}/{min(15, len(affected_settlements))}] {s['name']} ({s['place']}): +{len(new_elems)} buildings (Total: {len(all_buildings)})", flush=True)
        else:
            print(f"    [{i+1}] {s['name']}: HTTP {rb.status_code}", flush=True)
    except Exception as ex:
        print(f"    [{i+1}] {s['name']}: {ex}", flush=True)

BUILDINGS_CACHE.write_text(json.dumps(all_buildings, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[+] Saved {len(all_buildings)} buildings to {BUILDINGS_CACHE}", flush=True)
