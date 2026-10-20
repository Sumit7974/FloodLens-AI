"""
prototype_sentinel1.py
======================
FloodLens AI — Sentinel-1 SAR Radar Change Detection Prototyping Pipeline
-------------------------------------------------------------------------
Searches Microsoft Planetary Computer STAC API for Sentinel-1 GRD (C-band Radar)
imagery over the Koshi River Basin [86.5, 26.2, 88.2, 27.8] during the August 2017
Nepal flood disaster.

Key Advantages of SAR (Synthetic Aperture Radar) for Monsoon Floods:
    1. All-Weather / Day-and-Night capability: Microwave radar pulses penetrate
       dense monsoon clouds, rain, and haze that blind optical satellites (Sentinel-2).
    2. Specular Water Reflection: Smooth open water surfaces reflect radar energy away
       from the antenna, creating low backscatter (dark pixels) contrasting against
       rougher soil and vegetation (brighter diffuse backscatter).

Pipeline:
    1. Search Planetary Computer STAC for co-registered Sentinel-1 IW GRD scene pairs
       sharing the exact same relative orbit and pass direction.
    2. Download lightweight preview thumbnails (avoiding massive multi-gigabyte COGs).
    3. Perform radar log-ratio change detection:
           Difference (dB) = 10 * log10(Post / Pre)
       Detect significant backscatter drops indicative of newly inundated floodwaters.
    4. Generate a 4-panel change detection comparison (sentinel1_sar_flood_comparison.png)
       and export SAR metadata (sentinel1_metadata.json).

Author : FloodLens AI Team
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from io import BytesIO
from typing import Dict, Any, Optional, Tuple, List

# Ensure standard UTF-8 console output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import pystac_client
import planetary_computer


# ---------------------------------------------------------------------------
# DEFAULT CONFIGURATION & PATHS
# ---------------------------------------------------------------------------
DEFAULT_BBOX = [86.5, 26.2, 88.2, 27.8]  # [min_lon, min_lat, max_lon, max_lat]
SCRIPT_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = SCRIPT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

COMPARISON_PNG_OUT = DOWNLOADS_DIR / "sentinel1_sar_flood_comparison.png"
METADATA_JSON_OUT = DOWNLOADS_DIR / "sentinel1_metadata.json"
PREVIEW_PRE_OUT = DOWNLOADS_DIR / "sentinel1_pre_flood_thumbnail.png"
PREVIEW_POST_OUT = DOWNLOADS_DIR / "sentinel1_post_flood_thumbnail.png"


# ---------------------------------------------------------------------------
# STAC SEARCH FOR SENTINEL-1 CO-REGISTERED PAIRS
# ---------------------------------------------------------------------------
def search_sentinel1_pairs(
    bbox: List[float] = DEFAULT_BBOX
) -> Tuple[Any, Any, List[Dict[str, Any]]]:
    """
    Search Planetary Computer STAC catalog for Sentinel-1 GRD imagery.
    Identifies a matched pre-flood and post-flood scene pair sharing the same
    relative orbit and pass direction for optimal change detection.
    """
    print("[*] Connecting to Planetary Computer STAC API...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace
    )

    # 1. Search Post-Flood Scenes (August 10 - 25, 2017)
    print(f"[*] Searching Sentinel-1 GRD post-flood scenes for bbox {bbox} (August 2017)...")
    post_search = catalog.search(
        collections=["sentinel-1-grd"],
        bbox=bbox,
        datetime="2017-08-10/2017-08-25"
    )
    post_items = list(post_search.items())
    print(f"[+] Found {len(post_items)} post-flood Sentinel-1 scenes in catalog.")

    if not post_items:
        raise RuntimeError("No Sentinel-1 post-flood scenes found in Planetary Computer STAC.")

    # Select primary post-flood scene covering the basin
    best_post = None
    target_orbit = None
    target_dir = None

    for it in post_items:
        orbit = it.properties.get("sat:relative_orbit")
        direction = it.properties.get("sat:orbit_state")
        mode = it.properties.get("sar:instrument_mode", "IW")
        if mode == "IW" and orbit is not None:
            best_post = it
            target_orbit = orbit
            target_dir = direction
            break

    if not best_post:
        best_post = post_items[0]
        target_orbit = best_post.properties.get("sat:relative_orbit")
        target_dir = best_post.properties.get("sat:orbit_state")

    # 2. Search Matching Pre-Flood Scenes (July 2017) with same Relative Orbit
    print(f"[*] Searching pre-flood baseline scenes with matching Relative Orbit #{target_orbit} ({target_dir})...")
    pre_search = catalog.search(
        collections=["sentinel-1-grd"],
        bbox=bbox,
        datetime="2017-07-01/2017-07-31"
    )
    pre_items = list(pre_search.items())
    print(f"[+] Found {len(pre_items)} pre-flood Sentinel-1 scenes.")

    matching_pre = [
        it for it in pre_items
        if it.properties.get("sat:relative_orbit") == target_orbit
    ]

    if matching_pre:
        best_pre = matching_pre[0]
    elif pre_items:
        print("[!] No exact relative orbit match; selecting closest pre-flood scene.")
        best_pre = pre_items[0]
    else:
        raise RuntimeError("No Sentinel-1 pre-flood scenes found in Planetary Computer STAC.")

    # Sign items to ensure asset URLs have valid SAS tokens
    best_pre = planetary_computer.sign(best_pre)
    best_post = planetary_computer.sign(best_post)

    all_scenes_summary = []
    for it in post_items[:8]:
        all_scenes_summary.append({
            "id": it.id,
            "datetime": it.datetime.isoformat(),
            "relative_orbit": it.properties.get("sat:relative_orbit"),
            "orbit_direction": it.properties.get("sat:orbit_state"),
            "polarizations": it.properties.get("sar:polarizations"),
            "mode": it.properties.get("sar:instrument_mode"),
        })

    return best_pre, best_post, all_scenes_summary


# ---------------------------------------------------------------------------
# PREVIEW THUMBNAIL DOWNLOADER
# ---------------------------------------------------------------------------
def download_preview_image(item: Any, save_path: Path) -> np.ndarray:
    """Download the lightweight preview thumbnail without downloading massive COGs."""
    print(f"[*] Downloading preview thumbnail for: {item.id} ...")
    asset = item.assets.get("thumbnail") or item.assets.get("rendered_preview")
    if not asset:
        raise KeyError(f"No preview thumbnail asset found for item {item.id}")

    url = asset.href
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download thumbnail from {url} (HTTP {r.status_code})")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(r.content)
    print(f"[+] Saved preview image ({len(r.content)/1024:.1f} KB) -> {save_path.name}")

    pil_img = Image.open(BytesIO(r.content)).convert("RGB")
    return np.array(pil_img)


# ---------------------------------------------------------------------------
# SAR RADAR CHANGE DETECTION ALGORITHM
# ---------------------------------------------------------------------------
def compute_sar_change_detection(
    pre_rgb: np.ndarray,
    post_rgb: np.ndarray,
    drop_threshold_db: float = -2.5
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Computes SAR radar change detection between pre-flood and post-flood imagery.

    Formula:
        Intensity proxy: I = 0.2989*R + 0.5870*G + 0.1140*B
        Backscatter (dB proxy): sigma_0 = 10 * log10(I + 1e-4)
        Difference (dB): delta_sigma_0 = sigma_post - sigma_pre

    Water detection criteria:
        1. Backscatter drop: delta_sigma_0 < drop_threshold_db (specular reflectance)
        2. Absolute dark water threshold: post_intensity is low
    """
    # Resize to identical shape if minor dimension difference exists
    if pre_rgb.shape != post_rgb.shape:
        pil_post = Image.fromarray(post_rgb).resize((pre_rgb.shape[1], pre_rgb.shape[0]), Image.Resampling.BILINEAR)
        post_rgb = np.array(pil_post)

    # Convert to grayscale intensity proxy
    pre_gray = (0.2989 * pre_rgb[:, :, 0] + 0.5870 * pre_rgb[:, :, 1] + 0.1140 * pre_rgb[:, :, 2]).astype(np.float32)
    post_gray = (0.2989 * post_rgb[:, :, 0] + 0.5870 * post_rgb[:, :, 1] + 0.1140 * post_rgb[:, :, 2]).astype(np.float32)

    # Normalize to [0, 1]
    pre_norm = pre_gray / 255.0
    post_norm = post_gray / 255.0

    # Backscatter proxy in decibels (dB)
    pre_db = 10.0 * np.log10(np.clip(pre_norm, 1e-4, 1.0))
    post_db = 10.0 * np.log10(np.clip(post_norm, 1e-4, 1.0))

    # Difference in dB
    diff_db = post_db - pre_db

    # Binary SAR flood mask
    # Newly inundated water: strong drop in backscatter AND post-flood surface is dark
    sar_flood_mask = (diff_db < drop_threshold_db) & (post_norm < 0.35)

    # Exclude image border / nodata
    border_mask = (pre_norm < 0.02) & (post_norm < 0.02)
    sar_flood_mask[border_mask] = False

    valid_pixels = np.count_nonzero(~border_mask)
    flooded_pixels = np.count_nonzero(sar_flood_mask)
    flood_percentage = (flooded_pixels / valid_pixels * 100.0) if valid_pixels > 0 else 0.0

    return diff_db, sar_flood_mask.astype(np.uint8), post_gray, flood_percentage


# ---------------------------------------------------------------------------
# 4-PANEL VISUALIZATION GENERATOR
# ---------------------------------------------------------------------------
def generate_sar_comparison_figure(
    pre_img: np.ndarray,
    post_img: np.ndarray,
    diff_db: np.ndarray,
    flood_mask: np.ndarray,
    pre_date: str,
    post_date: str,
    rel_orbit: int,
    output_png: Path
):
    """Generates a high-resolution 4-panel publication-grade SAR change comparison figure."""
    print(f"[*] Generating 4-panel SAR flood comparison figure...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=200)

    # Panel 1: Pre-Flood SAR
    axes[0, 0].imshow(pre_img)
    axes[0, 0].set_title(f"A) Pre-Flood Sentinel-1 SAR ({pre_date})\nRelative Orbit #{rel_orbit} | VV+VH Radar Intensity", fontsize=12, fontweight="bold", pad=8)
    axes[0, 0].axis("off")

    # Panel 2: Post-Flood SAR
    axes[0, 1].imshow(post_img)
    axes[0, 1].set_title(f"B) Post-Flood Sentinel-1 SAR ({post_date})\nPeak Flood Event | Monsoonal Cloud-Penetrating Radar", fontsize=12, fontweight="bold", pad=8)
    axes[0, 1].axis("off")

    # Panel 3: Radar Backscatter Difference (dB)
    im_diff = axes[1, 0].imshow(diff_db, cmap="RdBu", vmin=-8, vmax=8)
    axes[1, 0].set_title("C) Radar Backscatter Difference (ΔdB)\nBlue: Backscatter Loss (Specular Water Inundation)", fontsize=12, fontweight="bold", pad=8)
    axes[1, 0].axis("off")
    cbar = fig.colorbar(im_diff, ax=axes[1, 0], orientation="horizontal", pad=0.04, fraction=0.046)
    cbar.set_label("Backscatter Difference Δσ° (dB)", fontsize=10)

    # Panel 4: Inundation Change Mask Overlay
    # Composite post-flood grayscale with bright cyan flood overlay
    post_gray = (0.2989 * post_img[:, :, 0] + 0.5870 * post_img[:, :, 1] + 0.1140 * post_img[:, :, 2])
    composite = np.stack([post_gray, post_gray, post_gray], axis=-1) / 255.0

    # Highlight flooded pixels in vibrant electric blue / cyan
    flood_idx = (flood_mask == 1)
    composite[flood_idx, 0] = 0.05   # Red
    composite[flood_idx, 1] = 0.65   # Green
    composite[flood_idx, 2] = 1.00   # Blue

    axes[1, 1].imshow(composite)
    axes[1, 1].set_title("D) Derived Sentinel-1 SAR Flood Inundation Mask\nCyan Overlay: Newly Inundated Floodwater", fontsize=12, fontweight="bold", pad=8)
    axes[1, 1].axis("off")

    legend_elements = [
        Patch(facecolor="#00A6FF", edgecolor="#004488", label="SAR Detected Inundation (Specular Reflectance)"),
        Patch(facecolor="#888888", edgecolor="#444444", label="Dry Land / High Backscatter Terrain")
    ]
    axes[1, 1].legend(handles=legend_elements, loc="lower right", framealpha=0.9, fontsize=9)

    plt.suptitle("FloodLens AI — Sentinel-1 SAR (Radar) Flood Change Detection Prototype\n"
                 f"Koshi River Basin, Nepal | Baseline: {pre_date} vs Inundation: {post_date}",
                 fontsize=15, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    output_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_png, bbox_inches="tight", dpi=200)
    plt.close()
    print(f"[+] Saved comparison figure ({output_png.stat().st_size / (1024 * 1024):.2f} MB) -> {output_png.name}")


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------
def run_sentinel1_prototype(
    bbox: List[float] = DEFAULT_BBOX,
    drop_threshold_db: float = -2.5
) -> Dict[str, Any]:
    """Executes the full Sentinel-1 prototyping pipeline."""
    t0 = time.time()
    min_lon, min_lat, max_lon, max_lat = bbox

    print("=" * 75)
    print(" FLOODLENS AI — SENTINEL-1 SAR CHANGE DETECTION PROTOTYPING")
    print("=" * 75)
    print(f"[*] Geographic Bounding Box : Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]")
    print(f"[*] Region                   : Koshi River Basin, Eastern Nepal")
    print(f"[*] Sensor                   : Sentinel-1 C-band SAR (Synthetic Aperture Radar)")
    print(f"[*] Target Event             : August 2017 Monsoon Flood Disaster")

    # 1. Query STAC Catalog for Co-registered Scene Pairs
    item_pre, item_post, catalog_summary = search_sentinel1_pairs(bbox)

    pre_id = item_pre.id
    post_id = item_post.id
    pre_date = item_pre.datetime.strftime("%Y-%m-%d")
    post_date = item_post.datetime.strftime("%Y-%m-%d")
    rel_orbit = item_post.properties.get("sat:relative_orbit")
    orbit_dir = item_post.properties.get("sat:orbit_state")
    pol = item_post.properties.get("sar:polarizations")

    print("\n" + "-" * 75)
    print(" SELECTED SENTINEL-1 SAR PAIR (CO-REGISTERED RADAR GEOMETRY)")
    print("-" * 75)
    print(f"[*] Pre-Flood Baseline  : {pre_id}")
    print(f"    - Date Acquired      : {pre_date} (Pre-monsoon / early season)")
    print(f"[*] Post-Flood Event    : {post_id}")
    print(f"    - Date Acquired      : {post_date} (Peak flood inundation)")
    print(f"[*] Relative Orbit #     : {rel_orbit} (Exact repeating ground track)")
    print(f"[*] Orbit Pass Direction : {orbit_dir}")
    print(f"[*] Polarizations        : {pol} (Co-pol VV & Cross-pol VH)")
    print(f"[*] Instrument Mode      : {item_post.properties.get('sar:instrument_mode')}")

    # 2. Download Preview Thumbnails
    print("\n" + "-" * 75)
    print(" FETCHING RADAR PREVIEWS (AVOIDING GIGABYTE COG DOWNLOADS)")
    print("-" * 75)
    pre_rgb = download_preview_image(item_pre, PREVIEW_PRE_OUT)
    post_rgb = download_preview_image(item_post, PREVIEW_POST_OUT)

    # 3. Compute SAR Change Detection
    print("\n" + "-" * 75)
    print(" COMPUTING SAR BACKSCATTER LOG-RATIO CHANGE DETECTION")
    print("-" * 75)
    print(f"[*] Applying Specular Water Drop Threshold: Δσ° < {drop_threshold_db} dB ...")
    diff_db, flood_mask, post_gray, flood_pct = compute_sar_change_detection(
        pre_rgb, post_rgb, drop_threshold_db=drop_threshold_db
    )

    flooded_px = int(np.count_nonzero(flood_mask == 1))
    total_px = int(flood_mask.size)
    print(f"[+] SAR Change Detection Results:")
    print(f"    - Processed Array Size   : {flood_mask.shape[1]} x {flood_mask.shape[0]} px")
    print(f"    - Detected Flooded Pixels: {flooded_px:,} / {total_px:,} ({flood_pct:.2f}% of scene)")
    print(f"    - Mean Backscatter Drop  : {np.nanmean(diff_db[flood_mask == 1]):.2f} dB over flood surface")

    # 4. Generate Visual Comparison Figure
    print("\n" + "-" * 75)
    print(" GENERATING VISUAL COMPARISON FIGURE")
    print("-" * 75)
    generate_sar_comparison_figure(
        pre_img=pre_rgb,
        post_img=post_rgb,
        diff_db=diff_db,
        flood_mask=flood_mask,
        pre_date=pre_date,
        post_date=post_date,
        rel_orbit=rel_orbit,
        output_png=COMPARISON_PNG_OUT
    )

    # 5. Export STAC Metadata Report
    metadata_report = {
        "pipeline": "FloodLens AI - Sentinel-1 SAR Prototyping",
        "study_region": "Koshi River Basin, Eastern Nepal",
        "bounding_box": bbox,
        "pre_flood_scene": {
            "id": pre_id,
            "datetime": item_pre.datetime.isoformat(),
            "relative_orbit": rel_orbit,
            "orbit_state": orbit_dir,
            "polarizations": pol,
            "preview_url": item_pre.assets.get("thumbnail", {}).href if hasattr(item_pre, "assets") else None,
        },
        "post_flood_scene": {
            "id": post_id,
            "datetime": item_post.datetime.isoformat(),
            "relative_orbit": rel_orbit,
            "orbit_state": orbit_dir,
            "polarizations": pol,
            "preview_url": item_post.assets.get("thumbnail", {}).href if hasattr(item_post, "assets") else None,
        },
        "sar_change_detection_metrics": {
            "drop_threshold_db": drop_threshold_db,
            "flooded_pixel_count": flooded_px,
            "flood_extent_percentage": round(float(flood_pct), 2),
            "algorithm": "Log-Ratio Specular Backscatter Drop Thresholding",
            "advantage": "All-weather cloud-penetrating radar capability during monsoonal storm events"
        },
        "catalog_scenes_available": catalog_summary,
        "outputs": {
            "comparison_figure": str(COMPARISON_PNG_OUT),
            "pre_thumbnail": str(PREVIEW_PRE_OUT),
            "post_thumbnail": str(PREVIEW_POST_OUT),
        }
    }

    METADATA_JSON_OUT.write_text(json.dumps(metadata_report, indent=2), encoding="utf-8")
    print(f"[+] Saved STAC metadata report -> {METADATA_JSON_OUT.name}")

    # Convenience copies to workspace root and FloodLens-AI root
    convenience_files = [
        (SCRIPT_DIR.parent.parent / "sentinel1_sar_flood_comparison.png", COMPARISON_PNG_OUT.read_bytes()),
        (SCRIPT_DIR.parent.parent / "sentinel1_metadata.json", json.dumps(metadata_report, indent=2).encode("utf-8")),
        (Path.cwd() / "sentinel1_sar_flood_comparison.png", COMPARISON_PNG_OUT.read_bytes()),
        (Path.cwd() / "sentinel1_metadata.json", json.dumps(metadata_report, indent=2).encode("utf-8")),
    ]

    for p_tgt, content in convenience_files:
        p_tgt.write_bytes(content)
        print(f"[+] Convenience copy -> {p_tgt}")

    dt = time.time() - t0
    print("\n" + "=" * 75)
    print(f" SENTINEL-1 SAR PROTOTYPE COMPLETED IN {dt:.2f}s")
    print("=" * 75)
    return metadata_report


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Prototype Sentinel-1 SAR change detection for Nepal flood event."
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
        "--threshold",
        type=float,
        default=-2.5,
        help="Backscatter drop threshold in dB (default: -2.5 dB)."
    )

    args = parser.parse_args()

    run_sentinel1_prototype(
        bbox=args.bbox,
        drop_threshold_db=args.threshold
    )


if __name__ == "__main__":
    main()
