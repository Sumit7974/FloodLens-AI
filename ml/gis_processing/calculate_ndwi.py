"""
calculate_ndwi.py
=================
FloodLens AI -- NDWI Flood Detection Pipeline
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

Expected file layout in downloads/
    pre_flood_B03.tif   - Green band, pre-flood  (from fetch_planetary_computer.py)
    pre_flood_B08.tif   - NIR   band, pre-flood
    post_flood_B03.tif  - Green band, post-flood
    post_flood_B08.tif  - NIR   band, post-flood

Outputs (written to downloads/)
    flood_mask.tif       - Binary GeoTIFF (1 = flooded, 0 = not flooded, 255 = nodata)
    flood_comparison.png - 3-panel side-by-side visualisation

Dependencies (in priority order):
    Primary : tifffile, numpy, matplotlib   (lightweight, pure-Python)
    Enhanced: rasterio                      (optional -- adds full georeferencing)

Author : FloodLens AI Team
"""

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend -- safe on any machine
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import tifffile

# Optional rasterio -- enhanced georeferencing when available
try:
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

# ---------------------------------------------------------------------------
# PATHS
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
# HELPERS -- reading
# ---------------------------------------------------------------------------

def file_is_valid(path: Path) -> bool:
    """Return True only when the file exists AND is non-empty."""
    return path.exists() and path.stat().st_size > 0


def read_band_tifffile(path: Path) -> np.ndarray:
    """
    Read the first page/band of a (Geo)TIFF using tifffile.
    Returns float32 array; zero-value NoData pixels -> NaN.
    """
    with tifffile.TiffFile(str(path)) as tif:
        # pages[0] is the first band; use asarray for memory efficiency
        data = tif.pages[0].asarray().astype(np.float32)

    # Replace exact-zero runs that typically encode NoData in Sentinel-2
    # (real surface reflectance is never exactly 0 over large regions)
    # Keep individual zeros -- they can be valid water pixels.
    # Only flag pixels where BOTH bands are 0 (handled in compute_ndwi).
    data[data < 0] = np.nan
    return data


def read_band_rasterio(path: Path):
    """Read a band with rasterio (preserves CRS / transform). Returns (array, profile)."""
    with rasterio.open(path) as src:
        data    = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata  = src.nodata
    if nodata is not None:
        data[data == nodata] = np.nan
    data[data < 0] = np.nan
    return data, profile


def read_band(path: Path):
    """
    Smart dispatcher: use rasterio if available, else tifffile.
    Always returns (array, profile_or_None).
    """
    if HAS_RASTERIO:
        arr, profile = read_band_rasterio(path)
        return arr, profile
    else:
        arr = read_band_tifffile(path)
        return arr, None


# ---------------------------------------------------------------------------
# HELPERS -- NDWI & mask
# ---------------------------------------------------------------------------

def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """
    Compute NDWI = (Green - NIR) / (Green + NIR).
    Pixels where both bands are 0 are set to NaN (NoData).
    Result clipped to [-1, 1].
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

    A pixel is FLOODED (1) when:
      - Post-flood NDWI > threshold   (surface water present after the event)
      - Post-flood NDWI > pre-flood NDWI  (new water -- excludes permanent water bodies)

    Returns:
      0   = land / dry
      1   = flooded (new water)
      255 = no-data
    """
    new_water  = (ndwi_post > threshold) & (ndwi_post > ndwi_pre)
    has_nodata = np.isnan(ndwi_pre) | np.isnan(ndwi_post)
    mask = np.where(has_nodata, 255, np.where(new_water, 1, 0)).astype(np.uint8)
    return mask


# ---------------------------------------------------------------------------
# HELPERS -- saving
# ---------------------------------------------------------------------------

def _geotiff_extratags(height: int, width: int):
    """
    Build minimal GeoTIFF extratags for WGS-84 / Koshi Basin bounding box.
    Used only when rasterio is not available.

    tifffile extratag format: (tagcode, dtype, count, value, writeonce)
    dtype: 'B'=uint8, 'H'=uint16, 'I'=uint32, 'd'=float64, 's'=bytes
    """
    dx = (88.2 - 86.5) / width
    dy = (27.8 - 26.2) / height

    # ModelPixelScaleTag (33550): 3 doubles [dx, dy, 0]
    pixel_scale = (33550, 'd', 3, (dx, dy, 0.0), False)

    # ModelTiepointTag (33922): 6 doubles [i,j,k, x,y,z]
    tiepoint = (33922, 'd', 6, (0.0, 0.0, 0.0, 86.5, 27.8, 0.0), False)

    # GeoKeyDirectoryTag (34736): 16 uint16s
    # Header: version=1, revision=1, minor=0, nkeys=3
    # Key 1024 (GTModelTypeGeoKey)  = 1  (Geographic)
    # Key 1025 (GTRasterTypeGeoKey) = 1  (PixelIsArea)
    # Key 2048 (GeographicTypeGeoKey) = 4326 (WGS-84)
    geo_keys = (34736, 'H', 16, (
        1, 1, 0, 3,
        1024, 0, 1, 1,
        1025, 0, 1, 1,
        2048, 0, 1, 4326,
    ), False)

    return [pixel_scale, tiepoint, geo_keys]


def save_mask_tifffile(mask: np.ndarray, out_path: Path) -> None:
    """Save the flood mask as a GeoTIFF using tifffile with WGS-84 tags."""
    h, w = mask.shape
    extratags = _geotiff_extratags(h, w)
    tifffile.imwrite(
        str(out_path),
        mask,
        photometric="minisblack",
        compression="deflate",
        extratags=extratags,
    )


def save_mask_rasterio(mask: np.ndarray, profile: dict, out_path: Path) -> None:
    """Save the flood mask GeoTIFF using rasterio (full CRS/transform)."""
    profile = profile.copy()
    profile.update(
        driver    = "GTiff",
        dtype     = "uint8",
        count     = 1,
        nodata    = 255,
        compress  = "lzw",
        tiled     = True,
        blockxsize= 256,
        blockysize= 256,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mask, 1)


def save_flood_mask(mask: np.ndarray, profile, out_path: Path) -> None:
    """Dispatcher: rasterio if available, else tifffile."""
    if HAS_RASTERIO and profile is not None:
        save_mask_rasterio(mask, profile, out_path)
    else:
        save_mask_tifffile(mask, out_path)
    kb = out_path.stat().st_size / 1024
    print(f"  [SAVED]  {out_path.name}  ({kb:.1f} KB)")


# ---------------------------------------------------------------------------
# SYNTHETIC DATA FALLBACK
# ---------------------------------------------------------------------------

def make_synthetic_scene(seed: int,
                         shape: tuple = (512, 512)) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic-looking synthetic Green + NIR bands.

    Land pixels : NIR >> Green  -> NDWI negative  (vegetation / soil)
    Water pixels: Green > NIR   -> NDWI positive  (flood water)
    """
    rng = np.random.default_rng(seed)
    h, w = shape

    # Base land (NIR dominant)
    green = rng.integers(300,  900,  (h, w), dtype=np.uint16).astype(np.float32)
    nir   = rng.integers(1200, 3000, (h, w), dtype=np.uint16).astype(np.float32)

    # Inject a flooded patch (Green > NIR)
    fh = int(h * 0.18)
    fw = int(w * 0.55)
    fy = rng.integers(h // 4, h // 2)
    fx = rng.integers(w // 4, w // 2)
    green[fy:fy+fh, fx:fx+fw] = rng.integers(600, 1000, (fh, fw)).astype(np.float32)
    nir  [fy:fy+fh, fx:fx+fw] = rng.integers(100,  500, (fh, fw)).astype(np.float32)

    # Noise
    green = np.clip(green + rng.normal(0, 30, (h, w)).astype(np.float32), 0, 10000)
    nir   = np.clip(nir   + rng.normal(0, 60, (h, w)).astype(np.float32), 0, 10000)
    return green, nir


def write_synthetic_tif(arr: np.ndarray, path: Path) -> None:
    """Write a synthetic band as a minimal GeoTIFF via tifffile."""
    h, w = arr.shape
    extratags = _geotiff_extratags(h, w)
    tifffile.imwrite(
        str(path),
        arr.astype(np.float32),
        photometric="minisblack",
        extratags=extratags,
    )
    print(f"  [SYNTHETIC]  Written -> {path.name}")


# ---------------------------------------------------------------------------
# VISUALISATION
# ---------------------------------------------------------------------------

def plot_comparison(ndwi_pre:   np.ndarray,
                    ndwi_post:  np.ndarray,
                    flood_mask: np.ndarray,
                    out_path:   Path,
                    is_synthetic: bool = False) -> None:
    """
    Three-panel figure:
      Panel 1 -- Pre-flood NDWI
      Panel 2 -- Post-flood NDWI
      Panel 3 -- Flood-extent mask
    """
    fig, axes = plt.subplots(1, 3, figsize=(19, 6),
                             gridspec_kw={"wspace": 0.08})
    cmap  = plt.cm.RdYlBu
    vmin, vmax = -0.6, 0.6

    # -- Panel 1: Pre-flood NDWI ------------------------------------------
    ax = axes[0]
    im = ax.imshow(ndwi_pre, cmap=cmap, vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    ax.set_title("Pre-Flood NDWI\n(Jul 2017 -- Koshi Basin)",
                 fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("NDWI value", fontsize=9)
    cb.ax.tick_params(labelsize=8)
    cb.ax.axhline(NDWI_THRESHOLD, color="navy", lw=1.5, ls="--")
    cb.ax.text(1.35, NDWI_THRESHOLD, f" thresh={NDWI_THRESHOLD}",
               va="center", fontsize=7, color="navy",
               transform=cb.ax.transData)

    # -- Panel 2: Post-flood NDWI -----------------------------------------
    ax = axes[1]
    im = ax.imshow(ndwi_post, cmap=cmap, vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    ax.set_title("Post-Flood NDWI\n(Aug 2017 -- Koshi Basin)",
                 fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")
    cb = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("NDWI value", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    # -- Panel 3: Flood mask -----------------------------------------------
    ax = axes[2]
    h, w   = flood_mask.shape
    rgb    = np.zeros((h, w, 3), dtype=np.float32)
    LAND   = np.array([0.87, 0.80, 0.63])
    WATER  = np.array([0.12, 0.56, 1.00])
    NODATA = np.array([0.78, 0.78, 0.78])
    rgb[flood_mask == 0]   = LAND
    rgb[flood_mask == 1]   = WATER
    rgb[flood_mask == 255] = NODATA

    ax.imshow(rgb, interpolation="nearest")
    ax.set_title("Flood-Extent Mask\n(New water: post > pre, NDWI > 0.10)",
                 fontsize=12, fontweight="bold", pad=8)
    ax.axis("off")

    legend_els = [
        Patch(facecolor=WATER,  edgecolor="navy",        label="Flooded -- new water"),
        Patch(facecolor=LAND,   edgecolor="saddlebrown", label="Land / dry"),
        Patch(facecolor=NODATA, edgecolor="grey",        label="No-data"),
    ]
    ax.legend(handles=legend_els, loc="lower right",
              fontsize=8, framealpha=0.88)

    # Flood pixel count annotation
    flooded  = int(np.sum(flood_mask == 1))
    total_v  = int(np.sum(flood_mask != 255))
    pct      = flooded / total_v * 100 if total_v else 0
    ax.text(0.02, 0.02,
            f"Flooded: {flooded:,} px  ({pct:.1f}%)",
            transform=ax.transAxes, fontsize=8,
            color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="navy", alpha=0.75))

    # -- Super-title -------------------------------------------------------
    note = ("[!]  SYNTHETIC DEMO DATA  (run fetch_planetary_computer.py for real imagery)"
            if is_synthetic else
            "Source: Sentinel-2 L2A -- Microsoft Planetary Computer")
    fig.suptitle(f"FloodLens AI -- NDWI Flood Detection  |  Koshi River Basin, Nepal\n{note}",
                 fontsize=13, fontweight="bold", y=1.02)

    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
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
    # Ensure UTF-8 output on Windows cp1252 consoles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 62)
    print("  FloodLens AI - NDWI Flood Detection Pipeline")
    backend = "rasterio + tifffile" if HAS_RASTERIO else "tifffile (rasterio not installed)"
    print(f"  Backend    : {backend}")
    print(f"  Input dir  : {DOWNLOAD_DIR}")
    print(f"  Threshold  : NDWI > {NDWI_THRESHOLD}  =>  flooded")
    print("=" * 62 + "\n")

    # -- 1. Check for real files --
    real_ok = {
        "pre_flood_B03 (Green)":  file_is_valid(PRE_GREEN),
        "pre_flood_B08 (NIR)":    file_is_valid(PRE_NIR),
        "post_flood_B03 (Green)": file_is_valid(POST_GREEN),
        "post_flood_B08 (NIR)":   file_is_valid(POST_NIR),
    }
    all_real     = all(real_ok.values())
    is_synthetic = not all_real

    if all_real:
        print("  [OK]  All 4 Sentinel-2 band files found - using real data.\n")
    else:
        missing = [k for k, v in real_ok.items() if not v]
        print("  [!]  Missing / empty files:")
        for m in missing:
            print(f"         - {m}")
        print("\n  [->]  Generating synthetic stand-in data ...\n")

        pre_g,  pre_n  = make_synthetic_scene(seed=42)
        post_g, post_n = make_synthetic_scene(seed=77)

        write_synthetic_tif(pre_g,  PRE_GREEN)
        write_synthetic_tif(pre_n,  PRE_NIR)
        write_synthetic_tif(post_g, POST_GREEN)
        write_synthetic_tif(post_n, POST_NIR)
        print()

    # -- 2. Read bands --
    print("  [STEP 1]  Reading Green (B03) + NIR (B08) ...")
    pre_green,  pre_prof   = read_band(PRE_GREEN)
    pre_nir,    _          = read_band(PRE_NIR)
    post_green, post_prof  = read_band(POST_GREEN)
    post_nir,   _          = read_band(POST_NIR)

    print(f"    Pre-flood  : {pre_green.shape}  dtype={pre_green.dtype}")
    print(f"    Post-flood : {post_green.shape}  dtype={post_green.dtype}")

    # -- 3. Compute NDWI --
    print("\n  [STEP 2]  Computing NDWI = (Green - NIR) / (Green + NIR) ...")
    ndwi_pre  = compute_ndwi(pre_green,  pre_nir)
    ndwi_post = compute_ndwi(post_green, post_nir)
    print("    [OK] NDWI computed for both epochs.")

    # -- 4. Flood mask --
    print("\n  [STEP 3]  Building flood-extent mask ...")
    flood_mask = build_flood_mask(ndwi_pre, ndwi_post, NDWI_THRESHOLD)
    print("    [OK] Mask created  (1=flooded, 0=land, 255=nodata).")

    # -- 5. Save GeoTIFF --
    print("\n  [STEP 4]  Saving flood_mask.tif ...")
    save_flood_mask(flood_mask, post_prof, MASK_OUT)

    # -- 6. Statistics --
    print_stats(ndwi_pre, ndwi_post, flood_mask)

    # -- 7. Visualisation --
    print("  [STEP 5]  Generating flood_comparison.png ...")
    plot_comparison(ndwi_pre, ndwi_post, flood_mask, PNG_OUT,
                    is_synthetic=is_synthetic)

    # -- Summary --
    print("\n" + "=" * 62)
    print("  [DONE]  All outputs written:")
    print(f"    -> {MASK_OUT}")
    print(f"    -> {PNG_OUT}")
    if is_synthetic:
        print("\n  NOTE: Run fetch_planetary_computer.py first to download")
        print("        real Sentinel-2 scenes, then re-run this script.")
    print("=" * 62)


if __name__ == "__main__":
    main()
