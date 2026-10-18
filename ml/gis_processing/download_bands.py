"""
download_bands.py
=================
Targeted downloader: fetches ONLY pre_flood_B03, pre_flood_B08,
post_flood_B03, post_flood_B08 from Microsoft Planetary Computer.
Skips any file that already exists and is non-empty.
"""
import os
import sys
import requests
import pathlib

try:
    import planetary_computer
    import pystac_client
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install pystac-client planetary-computer tqdm requests")
    sys.exit(1)

CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION  = "sentinel-2-l2a"
AOI_BBOX    = [86.5, 26.2, 88.2, 27.8]   # Koshi River Basin

PRE_WINDOW  = ("2017-06-01", "2017-07-31")
POST_WINDOW = ("2017-08-05", "2017-08-31")

OUT_DIR = pathlib.Path(__file__).parent / "downloads"
OUT_DIR.mkdir(exist_ok=True)

TARGETS = {
    "pre_flood":  PRE_WINDOW,
    "post_flood": POST_WINDOW,
}
BANDS = ["B03", "B08"]


def search_best(start, end, label):
    print(f"\n[SEARCH] {label} ({start} -> {end}) ...")
    catalog = pystac_client.Client.open(
        CATALOG_URL, modifier=planetary_computer.sign_inplace
    )
    search = catalog.search(
        collections=[COLLECTION],
        bbox=AOI_BBOX,
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": 95}},
        sortby="+properties.eo:cloud_cover",
        max_items=50,
    )
    items = list(search.items())
    if not items:
        print(f"  [WARN] No items found for {label}")
        return None
    best = sorted(items, key=lambda i: i.properties.get("eo:cloud_cover", 999))[0]
    print(f"  [OK] {best.id}  cloud={best.properties.get('eo:cloud_cover')}%  "
          f"date={best.properties.get('datetime','?')[:10]}")
    return best


def download_band(item, band, label):
    out_path = OUT_DIR / f"{label}_{band}.tif"
    if out_path.exists() and out_path.stat().st_size > 10000:
        print(f"  [SKIP] Already exists: {out_path.name} ({out_path.stat().st_size//1024} KB)")
        return True

    if band not in item.assets:
        print(f"  [SKIP] Band {band} not in assets")
        return False

    href = item.assets[band].href
    print(f"  [DL] {out_path.name} ...")
    r = requests.get(href, stream=True, timeout=300)
    r.raise_for_status()

    total = int(r.headers.get("content-length", 0))
    with open(out_path, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, unit_divisor=1024, leave=False
    ) as bar:
        for chunk in r.iter_content(8192):
            f.write(chunk)
            bar.update(len(chunk))

    sz = out_path.stat().st_size
    print(f"  [OK] Saved {out_path.name}  ({sz//1024//1024} MB)")
    return True


def main():
    print("=" * 56)
    print("  FloodLens AI - Targeted Band Downloader (B03, B08)")
    print("=" * 56)

    items = {}
    for label, (start, end) in TARGETS.items():
        items[label] = search_best(start, end, label)

    print()
    for label, item in items.items():
        if item is None:
            print(f"[SKIP] No scene found for {label}")
            continue
        print(f"\n[DOWNLOAD] {label} bands ...")
        for band in BANDS:
            download_band(item, band, label)

    print("\n" + "=" * 56)
    print("  Done. Files in downloads/:")
    for f in sorted(OUT_DIR.glob("*.tif")):
        print(f"    {f.name:35s}  {f.stat().st_size//1024:>8} KB")
    print("=" * 56)


if __name__ == "__main__":
    main()
