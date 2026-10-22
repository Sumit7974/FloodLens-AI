"""
auto_runner.py
==============
Monitors and ensures complete download of:
  - pre_flood_B08.tif
  - post_flood_B08.tif
with auto-resume and fresh SAS tokens.
As soon as both files are complete and verified, automatically executes calculate_ndwi.py.
"""

import sys
import time
import subprocess
import pathlib
import tifffile
import pystac_client
import planetary_computer

DOWNLOAD_DIR = pathlib.Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION  = "sentinel-2-l2a"
AOI_BBOX    = [86.5, 26.2, 88.2, 27.8]

TARGETS = [
    {
        "name": "pre_flood_B08.tif",
        "dates": ("2017-06-01", "2017-07-31"),
        "band": "B08",
    },
    {
        "name": "post_flood_B08.tif",
        "dates": ("2017-08-05", "2017-08-31"),
        "band": "B08",
    }
]


def verify_file(path: pathlib.Path) -> bool:
    if not path.exists() or path.stat().st_size < 100 * 1024 * 1024:
        return False
    try:
        with tifffile.TiffFile(str(path)) as t:
            arr = t.pages[0].asarray()
            print(f"[VERIFIED] {path.name}: shape={arr.shape}, dtype={arr.dtype}, size={path.stat().st_size/1024/1024:.1f}MB")
        return True
    except Exception as e:
        print(f"[INCOMPLETE] {path.name}: {e}")
        return False


def get_fresh_url(start_date: str, end_date: str, band: str):
    catalog = pystac_client.Client.open(CATALOG_URL)
    search = catalog.search(
        collections=[COLLECTION],
        bbox=AOI_BBOX,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lt": 95}},
        sortby="+properties.eo:cloud_cover",
        max_items=5
    )
    items = list(search.items())
    if not items:
        raise RuntimeError(f"No scene for {start_date} - {end_date}")
    raw_href = items[0].assets[band].href
    return planetary_computer.sign_url(raw_href)


def download_with_auto_resume(target):
    dest = DOWNLOAD_DIR / target["name"]
    print(f"\n==========================================")
    print(f"Ensuring {target['name']} is complete...")
    print(f"==========================================")

    attempt = 1
    while not verify_file(dest):
        current_sz = dest.stat().st_size if dest.exists() else 0
        print(f"\n[Attempt {attempt}] Current size: {current_sz / 1024 / 1024:.2f} MB")
        
        try:
            print("  Fetching fresh signed URL...")
            url = get_fresh_url(target["dates"][0], target["dates"][1], target["band"])
            
            cmd = [
                "curl.exe",
                "-L",
                "-C", "-",
                "--speed-limit", "1000",
                "--speed-time", "25",
                "--connect-timeout", "30",
                "-o", str(dest),
                url
            ]
            print(f"  Running curl resume...")
            subprocess.run(cmd)
        except Exception as e:
            print(f"  Error during attempt {attempt}: {e}")
        
        if verify_file(dest):
            print(f"  -> {target['name']} successfully verified!")
            break
            
        attempt += 1
        print(f"  -> Incomplete, waiting 3s before resume...")
        time.sleep(3)


def main():
    print("=" * 60)
    print("  FloodLens AI - Automated Satellite Data & NDWI Pipeline")
    print("=" * 60)

    # 1. Download both B08 bands
    for target in TARGETS:
        download_with_auto_resume(target)

    # 2. Run calculate_ndwi.py
    print("\n" + "=" * 60)
    print("  All real bands downloaded and verified!")
    print("  Executing calculate_ndwi.py...")
    print("=" * 60 + "\n")

    cmd = [sys.executable, str(pathlib.Path(__file__).parent / "calculate_ndwi.py")]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("\n[COMPLETE] Real NDWI and flood mask generated successfully!")
    else:
        print("\n[ERROR] calculate_ndwi.py exited with code", res.returncode)
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()
