"""
download_missing_b08.py
=======================
Downloads the missing Sentinel-2 NIR (B08) bands:
  1. pre_flood_B08.tif
  2. post_flood_B08.tif

Uses freshly signed Planetary Computer SAS URLs and robust download/resume.
"""

import sys
import subprocess
import pathlib
import requests
import pystac_client
import planetary_computer
import tifffile

DOWNLOAD_DIR = pathlib.Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION  = "sentinel-2-l2a"
AOI_BBOX    = [86.5, 26.2, 88.2, 27.8]   # Koshi Basin

SCENES = {
    "pre_flood_B08": {
        "dates": ("2017-06-01", "2017-07-31"),
        "filename": "pre_flood_B08.tif",
    },
    "post_flood_B08": {
        "dates": ("2017-08-05", "2017-08-31"),
        "filename": "post_flood_B08.tif",
    }
}


def is_valid_geotiff(path: pathlib.Path) -> bool:
    if not path.exists() or path.stat().st_size < 10 * 1024 * 1024:
        return False
    try:
        with tifffile.TiffFile(str(path)) as t:
            arr = t.pages[0].asarray()
            print(f"  [VERIFIED] {path.name}: shape={arr.shape}, dtype={arr.dtype}, min={arr.min()}, max={arr.max()}")
        return True
    except Exception as e:
        print(f"  [CORRUPT/INCOMPLETE] {path.name}: {e}")
        return False


def get_fresh_asset_url(start_date: str, end_date: str, band: str = "B08"):
    print(f"  Querying STAC for {start_date} to {end_date}...")
    catalog = pystac_client.Client.open(CATALOG_URL)
    search = catalog.search(
        collections=[COLLECTION],
        bbox=AOI_BBOX,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": 95}},
        sortby="+properties.eo:cloud_cover",
        max_items=10
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No scene found for {start_date} - {end_date}")
    best_item = items[0]
    raw_href = best_item.assets[band].href
    signed_url = planetary_computer.sign_url(raw_href)
    return best_item.id, signed_url


def download_file(url: str, dest_path: pathlib.Path):
    print(f"  Starting download to {dest_path.name}...")
    # Use curl.exe with resume (-C -) and auto-retry
    cmd = [
        "curl.exe",
        "-L",
        "-C", "-",
        "--retry", "10",
        "--retry-delay", "5",
        "--retry-max-time", "3600",
        "-o", str(dest_path),
        url
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        # Fallback to requests if curl fails
        print("  curl exited with code", res.returncode, ", trying requests...")
        existing = dest_path.stat().st_size if dest_path.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing > 0 else {}
        r = requests.get(url, headers=headers, stream=True, timeout=120)
        r.raise_for_status()
        mode = "ab" if (existing > 0 and r.status_code == 206) else "wb"
        with open(dest_path, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def main():
    print("=" * 60)
    print("  FloodLens AI - Download Missing B08 (NIR) Bands")
    print("=" * 60)

    for key, info in SCENES.items():
        dest = DOWNLOAD_DIR / info["filename"]
        print(f"\n[CHECK] {info['filename']}...")
        if is_valid_geotiff(dest):
            print(f"  -> Already exists and valid: {dest.name}")
            continue

        print(f"  -> Fetching fresh download URL for {key}...")
        item_id, signed_url = get_fresh_asset_url(info["dates"][0], info["dates"][1], "B08")
        print(f"  -> Scene: {item_id}")
        
        # Download
        download_file(signed_url, dest)

        # Validate
        if not is_valid_geotiff(dest):
            print(f"  [ERROR] {dest.name} validation failed after download!")
            sys.exit(1)
        print(f"  [SUCCESS] {dest.name} downloaded and verified!\n")

    print("\n" + "=" * 60)
    print("  All B08 bands ready!")
    print("=" * 60)


if __name__ == "__main__":
    main()
