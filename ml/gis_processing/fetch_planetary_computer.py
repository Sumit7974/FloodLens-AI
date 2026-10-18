"""
fetch_planetary_computer.py
============================
FloodLens AI — Sentinel-2 Imagery via Microsoft Planetary Computer
-------------------------------------------------------------------
No account. No authentication. Completely free & open.

Fetches:
  • Sentinel-2 L2A — pre-flood  (July 2017, cloud ≤ 20 %)
  • Sentinel-2 L2A — post-flood (August 2017, cloud ≤ 20 %)

AOI  : Koshi River Basin, Nepal Terai
       [86.5°E – 88.2°E, 26.2°N – 27.8°N]

Downloads the Visual (TCI), B04 (Red), B03 (Green), B08 (NIR), B11 (SWIR)
GeoTIFF assets for the least-cloudy scene in each window.

Requirements:
    pip install pystac-client planetary-computer requests tqdm

Author: FloodLens AI Team
"""

import os
import requests
import planetary_computer
import pystac_client
from tqdm import tqdm

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION  = "sentinel-2-l2a"

# Koshi River Basin bounding box  [west, south, east, north]
AOI_BBOX = [86.5, 26.2, 88.2, 27.8]

# NOTE: Nepal's monsoon season (Jun-Sep) produces 65-100% cloud cover on
# ALL Sentinel-2 scenes. We use 95% as threshold to get the least-cloudy
# available scenes. SAR (Sentinel-1) is the primary tool for flood detection.
PRE_FLOOD_WINDOW  = ("2017-06-01", "2017-07-31")   # wider window for best pre-flood clear scene
POST_FLOOD_WINDOW = ("2017-08-05", "2017-08-31")

MAX_CLOUD_COVER = 95   # relaxed for monsoon season — pick least-cloudy available

# Bands to download per scene
BANDS = ["visual", "B04", "B03", "B08", "B11"]

# Output directory (same folder as this script)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def search_sentinel2(start: str, end: str, label: str):
    """Search Planetary Computer STAC for Sentinel-2 scenes."""
    print(f"\n[SEARCH]  {label} Sentinel-2 ({start} -> {end}) ...")

    catalog = pystac_client.Client.open(
        CATALOG_URL,
        modifier=planetary_computer.sign_inplace,   # anonymous token signing
    )

    search = catalog.search(
        collections=[COLLECTION],
        bbox=AOI_BBOX,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
        sortby="+properties.eo:cloud_cover",        # least cloudy first
        max_items=50,
    )

    items = list(search.items())
    print(f"   Found {len(items)} scene(s) with cloud cover < {MAX_CLOUD_COVER}%")

    if not items:
        print("   [WARN]  No scenes found -- try relaxing the cloud cover filter.")
        return None

    # Pick the scene with least cloud cover
    best = sorted(items, key=lambda i: i.properties.get("eo:cloud_cover", 999))[0]
    cloud = best.properties.get("eo:cloud_cover", "?")
    date  = best.properties.get("datetime", "?")[:10]
    print(f"   [OK]  Best scene  : {best.id}")
    print(f"         Date        : {date}")
    print(f"         Cloud cover : {cloud}%")
    return best


def download_asset(item, band: str, label: str):
    """Download a single band GeoTIFF from a signed STAC item."""
    if band not in item.assets:
        print(f"   [SKIP]  Band '{band}' not available in this scene -- skipping.")
        return

    asset = item.assets[band]
    href  = asset.href                     # already signed by sign_inplace modifier

    filename = f"{label}_{band}.tif"
    filepath = os.path.join(OUT_DIR, filename)

    if os.path.exists(filepath):
        print(f"   [CACHED]  Already exists, skipping : {filename}")
        return

    print(f"   [DL]  Downloading : {filename}")
    response = requests.get(href, stream=True, timeout=120)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    with open(filepath, "wb") as f, tqdm(
        desc=f"      {filename}",
        total=total,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        leave=False,
    ) as bar:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            bar.update(len(chunk))

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"   [OK]  Saved ({size_mb:.1f} MB) -> {filepath}")


def download_scene(item, label: str):
    """Download all configured bands for a given STAC item."""
    print(f"\n[DOWNLOAD]  Fetching bands for : {label}")
    for band in BANDS:
        download_asset(item, band, label)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  FloodLens AI -- Planetary Computer Sentinel-2 Downloader")
    print("=" * 60)
    print(f"  AOI      : Koshi River Basin, Nepal")
    print(f"  BBOX     : {AOI_BBOX}")
    print(f"  Out dir  : {OUT_DIR}")

    # Search
    pre_item  = search_sentinel2(*PRE_FLOOD_WINDOW,  label="Pre-Flood")
    post_item = search_sentinel2(*POST_FLOOD_WINDOW, label="Post-Flood")

    # Download
    if pre_item:
        download_scene(pre_item,  label="pre_flood")

    if post_item:
        download_scene(post_item, label="post_flood")

    # Summary
    print("\n" + "=" * 60)
    print("  [DONE]  Download complete!")
    downloaded = [f for f in os.listdir(OUT_DIR) if f.endswith(".tif")]
    print(f"  Files saved to: {OUT_DIR}")
    for f in sorted(downloaded):
        size_mb = os.path.getsize(os.path.join(OUT_DIR, f)) / (1024 * 1024)
        print(f"    - {f}  ({size_mb:.1f} MB)")
    print("=" * 60)
