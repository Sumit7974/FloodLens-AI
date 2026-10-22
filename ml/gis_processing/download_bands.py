"""
download_bands.py
=================
Targeted downloader: fetches pre_flood and post_flood B03, B08 bands
from Microsoft Planetary Computer, with chunked resume + retry logic.
"""
import os
import sys
import time
import pathlib
import requests

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

MAX_RETRIES  = 5
CHUNK_SIZE   = 65536   # 64 KB chunks — more resilient on flaky connections
TIMEOUT      = 120     # seconds per request


def is_valid_tif(path: pathlib.Path, min_mb: float = 5.0) -> bool:
    """
    Return True only if the file exists, is above min_mb, AND the pixel
    data decompresses without error (catches truncated downloads).
    """
    if not path.exists():
        return False
    if path.stat().st_size < min_mb * 1024 * 1024:
        return False
    try:
        import tifffile
        with tifffile.TiffFile(str(path)) as t:
            # Must attempt a full decode — header reads fine even on truncated files
            _ = t.pages[0].asarray()
        return True
    except Exception:
        return False


def search_best(start, end, label):
    print(f"\n[SEARCH] {label} ({start} -> {end}) ...")
    for attempt in range(3):
        try:
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
            print(f"  [OK] {best.id}")
            print(f"       date={best.properties.get('datetime','?')[:10]}  "
                  f"cloud={best.properties.get('eo:cloud_cover','?'):.1f}%")
            return best
        except Exception as e:
            print(f"  [RETRY {attempt+1}/3] Search error: {e}")
            time.sleep(5)
    return None


def download_with_retry(url: str, out_path: pathlib.Path, label: str) -> bool:
    """Download url -> out_path with up to MAX_RETRIES retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        # Re-sign URL on each retry (tokens expire)
        try:
            import planetary_computer as pc
            signed_href = pc.sign(url)
        except Exception:
            signed_href = url

        existing = out_path.stat().st_size if out_path.exists() else 0
        headers  = {"Range": f"bytes={existing}-"} if existing > 0 else {}

        try:
            print(f"  [DL attempt {attempt}/{MAX_RETRIES}] {out_path.name}"
                  + (f"  (resume from {existing//1024//1024} MB)" if existing else ""))
            r = requests.get(signed_href, stream=True, timeout=TIMEOUT, headers=headers)

            if r.status_code == 416:
                # Range not satisfiable -> file already complete
                print(f"  [OK] Already complete: {out_path.name}")
                return True
            r.raise_for_status()

            mode   = "ab" if (existing > 0 and r.status_code == 206) else "wb"
            total  = int(r.headers.get("content-length", 0))
            offset = existing if mode == "ab" else 0

            with open(out_path, mode) as f, tqdm(
                total=(total + offset) if total else None,
                initial=offset,
                unit="B", unit_scale=True, unit_divisor=1024,
                desc=f"    {out_path.name}",
                leave=True,
            ) as bar:
                for chunk in r.iter_content(CHUNK_SIZE):
                    f.write(chunk)
                    bar.update(len(chunk))

            final_mb = out_path.stat().st_size / 1024 / 1024
            print(f"  [OK] {out_path.name}  ({final_mb:.1f} MB)")
            return True

        except Exception as e:
            print(f"  [ERR] Attempt {attempt} failed: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                wait = 10 * attempt
                print(f"  [WAIT] Retrying in {wait}s ...")
                time.sleep(wait)
            else:
                print(f"  [FAIL] Giving up on {out_path.name}")
                return False


def download_band(item, band: str, label: str) -> bool:
    out_path = OUT_DIR / f"{label}_{band}.tif"

    if is_valid_tif(out_path):
        mb = out_path.stat().st_size / 1024 / 1024
        print(f"  [SKIP] Already valid: {out_path.name} ({mb:.1f} MB)")
        return True

    if band not in item.assets:
        print(f"  [SKIP] Band {band} not in scene assets")
        return False

    # Re-sign to get a fresh URL
    asset = item.assets[band]
    try:
        signed = planetary_computer.sign(item)
        href   = signed.assets[band].href
    except Exception:
        href = asset.href

    return download_with_retry(href, out_path, label)


def main():
    print("=" * 60)
    print("  FloodLens AI - Targeted Band Downloader (B03 + B08)")
    print("=" * 60)

    # Search for scenes
    items = {}
    for label, (start, end) in TARGETS.items():
        items[label] = search_best(start, end, label)

    # Download missing/invalid bands
    print("\n" + "-" * 60)
    results = {}
    for label, item in items.items():
        if item is None:
            print(f"\n[SKIP] No scene for {label}")
            continue
        print(f"\n[DOWNLOAD] {label} ...")
        for band in BANDS:
            key = f"{label}_{band}"
            results[key] = download_band(item, band, label)

    # Final summary
    print("\n" + "=" * 60)
    print("  Download Summary:")
    for f in sorted(OUT_DIR.glob("*.tif")):
        valid = is_valid_tif(f)
        mb    = f.stat().st_size / 1024 / 1024
        status = "[OK]  " if valid else "[ERR] "
        print(f"    {status} {f.name:35s}  {mb:8.1f} MB")
    print("=" * 60)

    # Check if we have everything needed for NDWI
    needed = ["pre_flood_B03", "pre_flood_B08", "post_flood_B03", "post_flood_B08"]
    missing = [n for n in needed if not is_valid_tif(OUT_DIR / f"{n}.tif")]
    if missing:
        print(f"\n[!] Still missing: {missing}")
        print("    Re-run this script to retry.")
        return False
    else:
        print("\n[OK] All 4 NDWI band files ready!")
        return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
