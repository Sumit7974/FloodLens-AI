"""
calculate_ndwi.py
=================
FloodLens AI — NDWI Flood Detection Pipeline
---------------------------------------------
Reads Sentinel-2 Green (B03) and NIR (B08) bands for pre-flood and
post-flood scenes, computes the Normalized Difference Water Index (NDWI),
derives a binary flood-extent mask, saves it as flood_mask.tif, and
produces a side-by-side comparison figure saved as flood_comparison.png.

NDWI formula:
    NDWI = (Green - NIR) / (Green + NIR)

    Values in [-1, 1]
    Positive (> 0.1) -> water / flooded surface
    Negative         -> vegetation / bare soil

Expected file layout in downloads/:
    pre_flood_B03.tif   - Green band, pre-flood  (Sentinel-2 L2A)
    pre_flood_B08.tif   - NIR   band, pre-flood
    post_flood_B03.tif  - Green band, post-flood
    post_flood_B08.tif  - NIR   band, post-flood

Outputs (written to downloads/):
    flood_mask.tif       - Binary GeoTIFF (1 = flooded, 0 = not flooded, 255 = nodata)
    flood_comparison.png - 3-panel side-by-side visualisation

Author : FloodLens AI Team
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import tifffile

# Try rasterio if available
try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

# ---------------------------------------------------------------------------
# PATHS & PARAMETERS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
DOWNLOAD_DIR = SCRIPT_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

MASK_OUT = DOWNLOAD_DIR / "flood_mask.tif"
PNG_OUT  = DOWNLOAD_DIR / "flood_comparison.png"

PRE_GREEN  = DOWNLOAD_DIR / "pre_flood_B03.tif"
PRE_NIR    = DOWNLOAD_DIR / "pre_flood_B08.tif"
POST_GREEN = DOWNLOAD_DIR / "post_flood_B03.tif"
POST_NIR   = DOWNLOAD_DIR / "post_flood_B08.tif"

NDWI_THRESHOLD = 0.10


# ---------------------------------------------------------------------------
# HELPERS - VALIDATION & READING
# ---------------------------------------------------------------------------

def file_is_valid(path: Path) -> bool:
    """Return True only if file exists, is > 10MB, and decodes properly."""
    if not path.exists() or path.stat().st_size < 10 * 1024 * 1024:
        return False
    try:
        with tifffile.TiffFile(str(path)) as t:
            shape = t.pages[0].shape
            if len(shape) != 2 or shape[0] < 1000:
                return False
        return True
    except Exception:
        return False


def read_band_rasterio(path: Path):
    """Read a band with rasterio (preserves CRS / transform)."""
    with rasterio.open(path) as src:
        data    = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata  = src.nodata
    if nodata is not None:
        data[data == nodata] = np.nan
    data[data < 0] = np.nan
    return data, profile


def read_band_tifffile(path: Path) -> np.ndarray:
    """Read a band using tifffile."""
    with tifffile.TiffFile(str(path)) as tif:
        data = tif.pages[0].asarray().astype(np.float32)
    data[data < 0] = np.nan
    return data


def read_band(path: Path):
    """Smart dispatcher: rasterio if available, else tifffile."""
    if HAS_RASTERIO:
        try:
            return read_band_rasterio(path)
        except Exception:
            pass
    return read_band_tifffile(path), None


# ---------------------------------------------------------------------------
# HELPERS - NDWI & MASK COMPUTATION
# ---------------------------------------------------------------------------

def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """
    Compute NDWI = (Green - NIR) / (Green + NIR).
    Pixels where both bands are 0 are marked as NaN (NoData).
    Result is clipped to [-1, 1].
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        denom = green + nir
        denom[denom == 0] = np.nan
        ndwi = (green - nir) / denom
    return np.clip(ndwi, -1.0, 1.0)


def build_flood_mask(ndwi_pre: np.ndarray,
                     ndwi_post: np.ndarray,
                     threshold: float = NDWI_THRESHOLD) -> np.ndarray:
    """
    Binary flood-extent mask (uint8).
      0   = land / dry
      1   = flooded (new water: post > threshold AND post > pre)
      255 = no-data
    """
    new_water  = (ndwi_post > threshold) & (ndwi_post > ndwi_pre)
    has_nodata = np.isnan(ndwi_pre) | np.isnan(ndwi_post)
    mask = np.where(has_nodata, 255, np.where(new_water, 1, 0)).astype(np.uint8)
    return mask


# ---------------------------------------------------------------------------
# HELPERS - GEOTIFF SAVING
# ---------------------------------------------------------------------------

def extract_source_geotags(ref_path: Path):
    """Extract GeoTIFF projection/transform tags from reference Sentinel-2 file."""
    if not ref_path or not ref_path.exists():
        return None
    try:
        with tifffile.TiffFile(str(ref_path)) as src:
            tags = []
            for code in [33550, 33922, 34735, 34736, 34737]:
                if code in src.pages[0].tags:
                    t = src.pages[0].tags[code]
                    tags.append((t.code, t.dtype, t.count, t.value, False))
            if tags:
                return tags
    except Exception:
        pass
    return None


def save_mask_rasterio(mask: np.ndarray, profile: dict, out_path: Path) -> None:
    """Save the flood mask GeoTIFF using rasterio (full CRS/transform)."""
    prof = profile.copy()
    prof.update(
        driver    = "GTiff",
        dtype     = "uint8",
        count     = 1,
        nodata    = 255,
        compress  = "deflate",
        tiled     = True,
        blockxsize= 256,
        blockysize= 256,
    )
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(mask, 1)


def save_mask_tifffile(mask: np.ndarray, out_path: Path, ref_path: Path = None) -> None:
    """Save the flood mask as a GeoTIFF using tifffile with cloned GeoTIFF tags."""
    extratags = extract_source_geotags(ref_path)
    tifffile.imwrite(
        str(out_path),
        mask,
        photometric="minisblack",
        compression="deflate",
        extratags=extratags,
    )


def save_flood_mask(mask: np.ndarray, profile, out_path: Path, ref_path: Path = None) -> None:
    """Dispatcher: rasterio if available, else tifffile with cloned GeoTIFF metadata."""
    if HAS_RASTERIO and profile is not None:
        save_mask_rasterio(mask, profile, out_path)
    else:
        save_mask_tifffile(mask, out_path, ref_path)
    kb = out_path.stat().st_size / 1024
    print(f"  [SAVED]  {out_path.name}  ({kb:.1f} KB)")


# ---------------------------------------------------------------------------
# VISUALISATION
# ---------------------------------------------------------------------------

def plot_comparison(ndwi_pre:   np.ndarray,
                    ndwi_post:  np.ndarray,
                    flood_mask: np.ndarray,
                    out_path:   Path) -> None:
    """
    Generates a 3-panel comparison figure:
      Panel 1: Pre-Flood NDWI
      Panel 2: Post-Flood NDWI
      Panel 3: Flood-Extent Mask
    """
    h, w = flood_mask.shape
    step = max(1, h // 1200)

    # Subsample for smooth, memory-safe plotting
    ndwi_pre_disp  = ndwi_pre[::step, ::step]
    ndwi_post_disp = ndwi_post[::step, ::step]
    mask_disp      = flood_mask[::step, ::step]

    fig, axes = plt.subplots(1, 3, figsize=(19, 6), gridspec_kw={"wspace": 0.08})
    cmap = plt.cm.RdYlBu
    vmin, vmax = -0.6, 0.6

    # 1. Pre-flood NDWI
    ax = axes[0]
    im = ax.imshow(ndwi_pre_disp, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="bilinear")
    ax.set_title("Pre-Flood NDWI\n(Jun 2017 - Koshi Basin)", fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("NDWI value", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    # 2. Post-flood NDWI
    ax = axes[1]
    im = ax.imshow(ndwi_post_disp, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="bilinear")
    ax.set_title("Post-Flood NDWI\n(Aug 2017 - Koshi Basin)", fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("NDWI value", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    # 3. Flood Mask
    ax = axes[2]
    dh, dw = mask_disp.shape
    rgb = np.zeros((dh, dw, 3), dtype=np.float32)
    LAND   = np.array([0.87, 0.80, 0.63])
    WATER  = np.array([0.12, 0.56, 1.00])
    NODATA = np.array([0.78, 0.78, 0.78])
    rgb[mask_disp == 0]   = LAND
    rgb[mask_disp == 1]   = WATER
    rgb[mask_disp == 255] = NODATA

    ax.imshow(rgb, interpolation="nearest")
    ax.set_title("Flood-Extent Mask\n(New water: post > pre, NDWI > 0.10)", fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")

    legend_els = [
        Patch(facecolor=WATER,  edgecolor="navy",        label="Flooded - new water"),
        Patch(facecolor=LAND,   edgecolor="saddlebrown", label="Land / dry"),
        Patch(facecolor=NODATA, edgecolor="grey",        label="No-data"),
    ]
    ax.legend(handles=legend_els, loc="lower right", fontsize=8, framealpha=0.88)

    # Compute statistics on full resolution
    flooded = int(np.sum(flood_mask == 1))
    total_v = int(np.sum(flood_mask != 255))
    pct = flooded / total_v * 100 if total_v else 0
    ax.text(0.02, 0.02,
            f"Flooded: {flooded:,} px  ({pct:.2f}%)",
            transform=ax.transAxes, fontsize=8,
            color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="navy", alpha=0.75))

    fig.suptitle("FloodLens AI - NDWI Flood Detection  |  Koshi River Basin, Nepal (Sentinel-2 L2A)",
                 fontsize=13, fontweight="bold", y=1.02)

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    kb = out_path.stat().st_size / 1024
    print(f"  [SAVED]  {out_path.name}  ({kb:.0f} KB)")


# ---------------------------------------------------------------------------
# STATISTICS
# ---------------------------------------------------------------------------

def print_stats(ndwi_pre: np.ndarray, ndwi_post: np.ndarray,
                flood_mask: np.ndarray) -> None:
    def _s(arr, label):
        v = arr[~np.isnan(arr)]
        print(f"    {label:22s}  min={v.min():+.3f}  max={v.max():+.3f}"
              f"  mean={v.mean():+.3f}  std={v.std():.3f}")

    flooded = int(np.sum(flood_mask == 1))
    total_v = int(np.sum(flood_mask != 255))
    pct     = flooded / total_v * 100 if total_v else 0.0

    print("\n  -- NDWI Statistics -----------------------------------------")
    _s(ndwi_pre,  "Pre-flood  NDWI")
    _s(ndwi_post, "Post-flood NDWI")
    print(f"\n  -- Flood Mask ----------------------------------------------")
    print(f"    Grid size        : {flood_mask.shape[0]} x {flood_mask.shape[1]} px")
    print(f"    Valid pixels     : {total_v:,}")
    print(f"    Flooded pixels   : {flooded:,}  ({pct:.2f}% of valid area)")
    print(f"    NDWI threshold   : {NDWI_THRESHOLD}")
    print(f"    Mask values      : 0=land  1=flooded  255=nodata")
    print("  ------------------------------------------------------------\n")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 62)
    print("  FloodLens AI - NDWI Flood Detection Pipeline")
    backend = "rasterio" if HAS_RASTERIO else "tifffile (GeoTIFF metadata cloned)"
    print(f"  Backend    : {backend}")
    print(f"  Input dir  : {DOWNLOAD_DIR}")
    print(f"  Threshold  : NDWI > {NDWI_THRESHOLD}  =>  flooded")
    print("=" * 62 + "\n")

    # 1. Verify all 4 required real GeoTIFF files
    real_ok = {
        "pre_flood_B03 (Green)":  file_is_valid(PRE_GREEN),
        "pre_flood_B08 (NIR)":    file_is_valid(PRE_NIR),
        "post_flood_B03 (Green)": file_is_valid(POST_GREEN),
        "post_flood_B08 (NIR)":   file_is_valid(POST_NIR),
    }

    if not all(real_ok.values()):
        print("  [!] Error: Missing required Sentinel-2 band GeoTIFF files:")
        for name, ok in real_ok.items():
            status = "[OK]" if ok else "[MISSING]"
            print(f"       {status} {name}")
        print("\n  Please ensure all 4 band GeoTIFFs are downloaded to:")
        print(f"  {DOWNLOAD_DIR}")
        sys.exit(1)

    print("  [OK] All 4 Sentinel-2 band files verified.\n")

    # 2. Read Green and NIR bands
    print("  [STEP 1] Reading Green (B03) + NIR (B08) bands...")
    pre_green,  pre_prof   = read_band(PRE_GREEN)
    pre_nir,    _          = read_band(PRE_NIR)
    post_green, post_prof  = read_band(POST_GREEN)
    post_nir,   _          = read_band(POST_NIR)

    print(f"    Pre-flood  shape: {pre_green.shape}  dtype: {pre_green.dtype}")
    print(f"    Post-flood shape: {post_green.shape}  dtype: {post_green.dtype}")

    # 3. Compute NDWI
    print("\n  [STEP 2] Computing NDWI = (Green - NIR) / (Green + NIR)...")
    ndwi_pre  = compute_ndwi(pre_green,  pre_nir)
    ndwi_post = compute_ndwi(post_green, post_nir)
    print("    [OK] NDWI calculated for pre-flood and post-flood.")

    # 4. Build flood mask
    print("\n  [STEP 3] Generating binary flood extent mask...")
    flood_mask = build_flood_mask(ndwi_pre, ndwi_post, NDWI_THRESHOLD)
    print("    [OK] Mask generated (1=flooded, 0=land, 255=nodata).")

    # 5. Save GeoTIFF
    print("\n  [STEP 4] Saving flood_mask.tif...")
    save_flood_mask(flood_mask, post_prof, MASK_OUT, ref_path=POST_GREEN)

    # 6. Print Statistics
    print_stats(ndwi_pre, ndwi_post, flood_mask)

    # 7. Generate Visualization
    print("  [STEP 5] Generating flood_comparison.png...")
    plot_comparison(ndwi_pre, ndwi_post, flood_mask, PNG_OUT)

    print("=" * 62)
    print("  [SUCCESS] All outputs generated successfully:")
    print(f"    -> {MASK_OUT}")
    print(f"    -> {PNG_OUT}")
    print("=" * 62)


if __name__ == "__main__":
    main()
