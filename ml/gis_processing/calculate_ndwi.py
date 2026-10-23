"""
calculate_ndwi.py
=================
FloodLens AI — Reproducible Pre/Post Optical Flood Detection Pipeline
---------------------------------------------------------------------
Performs rigorous, reproducible, scientific remote sensing flood detection from
Sentinel-2 Level-2A surface reflectance optical imagery.

Scientific Pipeline:
1. Exact Affine-Grid & Spectral Band Validation:
   - Sentinel-2 Green (B03, 560 nm, 10m)
   - Sentinel-2 Near Infrared (B08, 842 nm, 10m)
   - Sentinel-2 Scene Classification Layer (SCL, 20m)
   - Validates CRS, affine transform metadata, spatial bounds, and ground alignment.
   - Enforces exact affine-grid alignment within scenes (e.g. B03 vs B08).
   - Rejects incompatible input or disjoint bounds instead of comparing shifted pixels by array index.
   - Reprojects cross-scene or multi-resolution inputs (such as 20m SCL) onto the exact target
     geospatial reference grid using rasterio transforms and nearest-neighbor resampling.
2. Scene Classification Layer (SCL) Quality & Cloud Masking:
   - ESA Sentinel-2 Level-2A SCL class specifications:
       0: No Data
       1: Saturated or Defective Pixel
       2: Cast Shadow / Dark Area Pixels
       3: Cloud Shadows
       4: Vegetation
       5: Not-Vegetated (Bare soil, rock, urban)
       6: Water
       7: Unclassified (Ambiguous classification from Sen2Cor)
       8: Cloud Medium Probability
       9: Cloud High Probability
      10: Thin Cirrus
      11: Snow / Ice
   - Documented Quality Policies:
     a) CONSERVATIVE POLICY (DEFAULT):
        Masks {0, 1, 2, 3, 7, 8, 9, 10, 11}.
        Retains ONLY certified surface classes: Vegetation (4), Bare Soil (5), Water (6).
        * Class 2 (Dark area / cast shadows) MUST be masked: topographic cast shadows and
          dark surface features receive low NIR, artificially inflating NDWI > 0 and causing
          severe false-positive flood inundation detections.
        * Class 7 (Unclassified) MUST be masked: Sen2Cor assigns Class 7 to low-confidence pixels
          (haze, cloud boundaries, mixed pixels). Under conservative flood safety standards,
          ambiguous surfaces cannot be certified as clear dry land or water and are marked
          unobserved (255).
     b) PERMISSIVE POLICY:
        Masks {0, 1, 3, 8, 9, 10, 11}. Permits Class 2 and Class 7.
3. Sentinel-2 Radiometric Calibration & Processing-Baseline Offsets:
   - Converts DN to surface reflectance: Reflectance = (DN + BOA_ADD_OFFSET) / QUANTIFICATION_VALUE.
   - For Processing Baseline < 04.00 (e.g. PB 02.12 used in our 2017 historical scenes):
     BOA_ADD_OFFSET = 0.0, QUANTIFICATION_VALUE = 10000.0.
   - For Processing Baseline >= 04.00 (harmonized post-Jan 2022):
     BOA_ADD_OFFSET = -1000.0 (prevents negative reflectance truncation).
4. Dual-Temporal NDWI Calculation:
   - NDWI = (Green - NIR) / (Green + NIR)
   - Computed separately on validated surface reflectance in [-1.0, 1.0].
5. Distinguishing Newly Inundated Floodwater from Persistent Water:
   - NEW_FLOOD        = Post-water AND (NOT Pre-water) AND Valid-shared  (Value: 1)
   - PERSISTENT_WATER = Post-water AND Pre-water AND Valid-shared        (Value: 2)
   - DRY_LAND         = (NOT Post-water) AND Valid-shared                (Value: 0)
   - UNOBSERVED       = NOT Valid-shared                                 (Value: 255)
6. Reproducible GIS Artifacts:
   - Pre-flood NDWI GeoTIFF (pre_ndwi.tif)
   - Post-flood NDWI GeoTIFF (post_ndwi.tif)
   - 4-State Inundation Dynamics Mask GeoTIFF (flood_mask.tif)
   - Vectorized newly inundated flood polygons (flood_polygons.geojson, EPSG:4326)
   - Multi-panel visual comparison (flood_comparison.png)
   - Provenance manifest and audit report

Author: FloodLens AI GIS & Remote Sensing Team
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.colors import ListedColormap
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import shapes
    from rasterio.warp import reproject, transform_geom
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    import shapely
    import shapely.ops
    from shapely.geometry import MultiPolygon, Polygon, mapping, shape
    from shapely.validation import make_valid
    import pyproj
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

logger = logging.getLogger("floodlens.calculate_ndwi")

# SCL Quality Policies
# 1. Conservative Quality Policy (DEFAULT):
# Excludes: NoData (0), Saturated (1), Cast Shadows / Dark Area (2), Cloud Shadows (3),
#           Unclassified (7), Cloud Medium (8), Cloud High (9), Cirrus (10), Snow (11).
# Valid: Vegetation (4), Not-Vegetated (5), Water (6).
CONSERVATIVE_UNSUITABLE_SCL_CLASSES = {0, 1, 2, 3, 7, 8, 9, 10, 11}

# 2. Permissive Quality Policy (legacy/exploratory):
# Excludes: NoData (0), Saturated (1), Cloud Shadows (3), Cloud Medium (8),
#           Cloud High (9), Cirrus (10), Snow (11).
# Permits Class 2 and Class 7.
PERMISSIVE_UNSUITABLE_SCL_CLASSES = {0, 1, 3, 8, 9, 10, 11}

DEFAULT_NDWI_THRESHOLD = 0.00
DEFAULT_QUANTIFICATION_VALUE = 10000.0


def dn_to_reflectance(
    dn_array: np.ndarray,
    scale_factor: float = DEFAULT_QUANTIFICATION_VALUE,
    boa_offset: float = 0.0,
    nodata: Optional[float] = None,
) -> np.ndarray:
    """Convert raw digital numbers (DN) to surface reflectance taking into account
    Sentinel-2 processing baseline offsets.

    Reflectance = (DN + boa_offset) / scale_factor

    Parameters:
        dn_array: Input raw DN raster (e.g. uint16).
        scale_factor: Radiometric quantification value (10000.0 for Sentinel-2 L2A).
        boa_offset: Processing baseline offset:
            - 0.0 for Processing Baseline < 04.00 (e.g. PB 02.12).
            - -1000.0 for Processing Baseline >= 04.00.
        nodata: Value representing NoData in the source raster.
    Returns:
        float32 array with valid surface reflectance in [0.0, ~1.0], or NaN for invalid.
    """
    arr = dn_array.astype(np.float32)
    if nodata is not None:
        arr[arr == nodata] = np.nan
    # Sentinel-2 DN 0 is native NoData
    arr[arr <= 0] = np.nan

    with np.errstate(invalid="ignore"):
        refl = (arr + float(boa_offset)) / float(scale_factor)
        refl[refl < 0] = np.nan
    return refl


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute Normalized Difference Water Index: (Green - NIR) / (Green + NIR).

    Parameters:
        green: Surface reflectance in green band (B03, ~560 nm).
        nir: Surface reflectance in near-infrared band (B08, ~842 nm).
    Returns:
        float32 array in [-1.0, 1.0], with NaN for zero-denominator or negative inputs.
    """
    g = green.astype(np.float32)
    n = nir.astype(np.float32)

    with np.errstate(divide="ignore", invalid="ignore"):
        denom = g + n
        invalid = (denom <= 0) | np.isnan(g) | np.isnan(n) | (g < 0) | (n < 0)
        ndwi = np.where(invalid, np.nan, (g - n) / denom)
    return np.clip(ndwi, -1.0, 1.0)


def extract_scl_mask(
    scl: Optional[np.ndarray],
    shape: Tuple[int, int],
    policy: str = "conservative",
) -> np.ndarray:
    """Return boolean mask of valid ground observation pixels based on Scene Classification Layer.

    Parameters:
        scl: SCL raster matching target grid shape (uint8).
        shape: Expected 2D grid shape (height, width).
        policy: Quality policy:
            - 'conservative' (DEFAULT): masks {0, 1, 2, 3, 7, 8, 9, 10, 11}.
              Strictly masks dark features / cast shadows (2) and unclassified / ambiguous (7).
            - 'permissive': masks {0, 1, 3, 8, 9, 10, 11}.
    """
    if scl is None:
        return np.ones(shape, dtype=bool)

    if scl.shape != shape:
        raise ValueError(f"SCL array shape {scl.shape} does not match expected grid shape {shape}.")

    unsuitable_classes = (
        CONSERVATIVE_UNSUITABLE_SCL_CLASSES
        if str(policy).lower() == "conservative"
        else PERMISSIVE_UNSUITABLE_SCL_CLASSES
    )
    return ~np.isin(scl, list(unsuitable_classes))


def validate_spatial_alignment(
    prof_a: Dict[str, Any],
    prof_b: Dict[str, Any],
    label_a: str = "Scene A",
    label_b: str = "Scene B",
    tolerance: float = 1e-4,
    require_identical_grid: bool = False,
) -> bool:
    """Validate geospatial compatibility between two raster profiles.

    Parameters:
        prof_a: Rasterio profile of first dataset.
        prof_b: Rasterio profile of second dataset.
        label_a: Human-readable label for dataset A.
        label_b: Human-readable label for dataset B.
        tolerance: Coordinate and resolution tolerance.
        require_identical_grid: If True, enforces exact matching CRS, resolution,
            affine transform, and grid dimensions (e.g. for intra-scene B03 vs B08).
            Raises ValueError if grids are not identical.
            If False, verifies CRS and non-disjoint bounding boxes, returning True
            if identical or False if reprojection is required.
    Returns:
        bool: True if grids are identical, False if reprojection is required.
    Raises:
        ValueError: If CRS is incompatible, bounds do not overlap, or required identical
            grids are mismatched.
    """
    crs_a = prof_a.get("crs")
    crs_b = prof_b.get("crs")
    if not crs_a or not crs_b:
        raise ValueError(f"Missing CRS metadata: {label_a} has {crs_a}, {label_b} has {crs_b}.")
    if str(crs_a).upper() != str(crs_b).upper():
        raise ValueError(f"CRS mismatch: {label_a} has {crs_a}, but {label_b} has {crs_b}.")

    trans_a = prof_a.get("transform")
    trans_b = prof_b.get("transform")
    if trans_a is None or trans_b is None:
        raise ValueError(f"Missing geospatial transform: {label_a}={trans_a}, {label_b}={trans_b}.")

    h_a, w_a = prof_a.get("height", 0), prof_a.get("width", 0)
    h_b, w_b = prof_b.get("height", 0), prof_b.get("width", 0)

    # Calculate exact bounding boxes in projected coordinates
    left_a, top_a = trans_a[2], trans_a[5]
    right_a = left_a + w_a * trans_a[0]
    bottom_a = top_a + h_a * trans_a[4]
    min_x_a, max_x_a = min(left_a, right_a), max(left_a, right_a)
    min_y_a, max_y_a = min(top_a, bottom_a), max(top_a, bottom_a)

    left_b, top_b = trans_b[2], trans_b[5]
    right_b = left_b + w_b * trans_b[0]
    bottom_b = top_b + h_b * trans_b[4]
    min_x_b, max_x_b = min(left_b, right_b), max(left_b, right_b)
    min_y_b, max_y_b = min(top_b, bottom_b), max(top_b, bottom_b)

    # Check for non-disjoint intersection
    disjoint = (max_x_a <= min_x_b or max_x_b <= min_x_a or max_y_a <= min_y_b or max_y_b <= min_y_a)
    if disjoint:
        raise ValueError(
            f"Geospatial transform mismatch: {label_a} bounds [{min_x_a}, {min_y_a}, {max_x_a}, {max_y_a}] "
            f"and {label_b} bounds [{min_x_b}, {min_y_b}, {max_x_b}, {max_y_b}] do not spatially intersect."
        )

    # Check if identical grid
    res_x_a, res_y_a = abs(trans_a[0]), abs(trans_a[4])
    res_x_b, res_y_b = abs(trans_b[0]), abs(trans_b[4])
    res_match = abs(res_x_a - res_x_b) <= tolerance and abs(res_y_a - res_y_b) <= tolerance
    origin_match = abs(trans_a[2] - trans_b[2]) <= tolerance and abs(trans_a[5] - trans_b[5]) <= tolerance
    dims_match = (h_a == h_b) and (w_a == w_b)

    is_identical = res_match and origin_match and dims_match

    if require_identical_grid and not is_identical:
        raise ValueError(
            f"Exact grid mismatch between {label_a} and {label_b}: "
            f"resolution=({res_x_a},{res_y_a}) vs ({res_x_b},{res_y_b}), "
            f"origin=({trans_a[2]},{trans_a[5]}) vs ({trans_b[2]},{trans_b[5]}), "
            f"dims=({h_a},{w_a}) vs ({h_b},{w_b})."
        )

    return is_identical


def reproject_to_target_grid(
    src_data: np.ndarray,
    src_transform: Any,
    src_crs: Any,
    target_shape: Tuple[int, int],
    target_transform: Any,
    target_crs: Any,
    is_categorical: bool = False,
    src_nodata: Optional[float] = None,
    dst_nodata: Optional[float] = None,
) -> np.ndarray:
    """Geospatially reproject or resample source raster onto the target reference grid.

    Uses rasterio.warp.reproject:
    - Resampling.nearest for categorical classification layers (e.g. SCL),
      preserving integer class values without interpolation.
    - Resampling.bilinear for continuous surface reflectance.

    Parameters:
        src_data: Source 2D numpy array.
        src_transform: Affine transform of source.
        src_crs: CRS of source.
        target_shape: Destination (height, width).
        target_transform: Affine transform of destination grid.
        target_crs: CRS of destination grid.
        is_categorical: If True, uses Resampling.nearest; else Resampling.bilinear.
        src_nodata: Source NoData value.
        dst_nodata: Destination NoData value.
    Returns:
        2D numpy array matching target_shape and target_transform.
    """
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio is required for geospatial raster reprojection.")

    # Fast path if grids are already identical
    t_match = (
        np.isclose(src_transform[0], target_transform[0], atol=1e-5)
        and np.isclose(src_transform[1], target_transform[1], atol=1e-5)
        and np.isclose(src_transform[2], target_transform[2], atol=1e-5)
        and np.isclose(src_transform[3], target_transform[3], atol=1e-5)
        and np.isclose(src_transform[4], target_transform[4], atol=1e-5)
        and np.isclose(src_transform[5], target_transform[5], atol=1e-5)
    )
    crs_match = str(src_crs).upper() == str(target_crs).upper()
    if t_match and crs_match and src_data.shape == target_shape:
        return src_data.copy()

    resampling_method = Resampling.nearest if is_categorical else Resampling.bilinear
    dtype = src_data.dtype
    if dst_nodata is None:
        dst_data = np.zeros(target_shape, dtype=dtype)
    else:
        dst_data = np.full(target_shape, dst_nodata, dtype=dtype)

    reproject(
        source=src_data,
        destination=dst_data,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=target_transform,
        dst_crs=target_crs,
        resampling=resampling_method,
        src_nodata=src_nodata,
        dst_nodata=dst_nodata,
    )
    return dst_data


def classify_flood_dynamics(
    ndwi_pre: np.ndarray,
    ndwi_post: np.ndarray,
    valid_pre: np.ndarray,
    valid_post: np.ndarray,
    threshold: float = DEFAULT_NDWI_THRESHOLD,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Classify 4-state flood dynamics on validated shared-observation coverage:

    0   = Dry land (validly observed non-water in post)
    1   = Newly inundated floodwater (post > threshold AND pre <= threshold AND valid shared)
    2   = Persistent water (pre > threshold AND post > threshold AND valid shared)
    255 = Unobserved / cloud / shadow / NoData / ambiguous unclassified

    Parameters:
        ndwi_pre: Valid pre-flood NDWI raster.
        ndwi_post: Valid post-flood NDWI raster.
        valid_pre: Boolean clear-observation mask for pre-flood.
        valid_post: Boolean clear-observation mask for post-flood.
        threshold: NDWI water threshold (default 0.00).
    """
    valid_shared = valid_pre & valid_post & ~np.isnan(ndwi_pre) & ~np.isnan(ndwi_post)

    water_pre = (ndwi_pre > threshold) & valid_pre & ~np.isnan(ndwi_pre)
    water_post = (ndwi_post > threshold) & valid_post & ~np.isnan(ndwi_post)

    new_flood = water_post & (~water_pre) & valid_shared
    persistent_water = water_post & water_pre & valid_shared
    dry_land = (~water_post) & valid_shared

    flood_mask = np.full(ndwi_post.shape, 255, dtype=np.uint8)
    flood_mask[dry_land] = 0
    flood_mask[persistent_water] = 2
    flood_mask[new_flood] = 1

    total_pixels = int(flood_mask.size)
    valid_shared_count = int(np.sum(valid_shared))
    valid_pre_count = int(np.sum(valid_pre))
    valid_post_count = int(np.sum(valid_post))
    new_flood_count = int(np.sum(new_flood))
    persistent_water_count = int(np.sum(persistent_water))
    dry_land_count = int(np.sum(dry_land))
    unobserved_count = total_pixels - valid_shared_count

    stats = {
        "total_pixels": total_pixels,
        "valid_shared_pixels": valid_shared_count,
        "valid_shared_pct": round(valid_shared_count / total_pixels * 100, 2) if total_pixels else 0.0,
        "valid_pre_pixels": valid_pre_count,
        "valid_pre_pct": round(valid_pre_count / total_pixels * 100, 2) if total_pixels else 0.0,
        "valid_post_pixels": valid_post_count,
        "valid_post_pct": round(valid_post_count / total_pixels * 100, 2) if total_pixels else 0.0,
        "new_flood_pixels": new_flood_count,
        "persistent_water_pixels": persistent_water_count,
        "dry_land_pixels": dry_land_count,
        "unobserved_pixels": unobserved_count,
        "threshold": threshold,
    }
    return flood_mask, stats


def compute_metric_area_km2(geom_wgs84: Any) -> float:
    """Calculate exact ground surface area in km² projected into UTM Zone 45N (EPSG:32645)."""
    if not HAS_SHAPELY or geom_wgs84 is None or geom_wgs84.is_empty:
        return 0.0
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
    geom_utm = shapely.ops.transform(transformer.transform, geom_wgs84)
    return round(float(geom_utm.area) / 1e6, 4)


def vectorize_mask(
    mask: np.ndarray,
    transform: Any,
    crs: Any,
    target_value: int = 1,
) -> Tuple[MultiPolygon, float, Dict[str, Any]]:
    """Convert binary raster pixels of target_value into EPSG:4326 MultiPolygon geometry and GeoJSON."""
    if not HAS_RASTERIO or not HAS_SHAPELY:
        raise RuntimeError("rasterio and shapely are required for vectorization.")

    binary_idx = (mask == target_value).astype(np.uint8)
    if np.count_nonzero(binary_idx) == 0:
        empty_mp = MultiPolygon([])
        fc = {"type": "FeatureCollection", "features": []}
        return empty_mp, 0.0, fc

    wgs84_polys = []
    for geom_dict, val in shapes(binary_idx, mask=(binary_idx == 1), transform=transform):
        if val != 1:
            continue
        try:
            if str(crs).upper() not in ("EPSG:4326", "WGS84"):
                geom_wgs84 = transform_geom(crs, "EPSG:4326", geom_dict)
            else:
                geom_wgs84 = geom_dict

            p = shape(geom_wgs84)
            if not p.is_valid:
                p = make_valid(p)
            if p.geom_type == "Polygon" and p.area > 0:
                wgs84_polys.append(p)
            elif p.geom_type == "MultiPolygon":
                wgs84_polys.extend([sub for sub in p.geoms if not sub.is_empty and sub.area > 0])
        except Exception as e:
            logger.warning("Skipping invalid vectorized polygon: %s", e)

    if not wgs84_polys:
        empty_mp = MultiPolygon([])
        return empty_mp, 0.0, {"type": "FeatureCollection", "features": []}

    merged = MultiPolygon(wgs84_polys)
    if not merged.is_valid:
        merged = make_valid(merged)
    if merged.geom_type == "Polygon":
        merged = MultiPolygon([merged])

    area_km2 = compute_metric_area_km2(merged)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {
                    "target_value": target_value,
                    "area_km2": area_km2,
                },
            }
        ],
    }
    return merged, area_km2, fc


def plot_optical_comparison(
    ndwi_pre: np.ndarray,
    ndwi_post: np.ndarray,
    flood_mask: np.ndarray,
    out_path: Path,
    title: str = "FloodLens AI — Pre/Post Optical NDWI Flood Detection",
    stats: Optional[Dict[str, Any]] = None,
) -> None:
    """Generate 3-panel visual rendering showing Pre-NDWI, Post-NDWI, and Flood Dynamics."""
    if not HAS_MATPLOTLIB:
        logger.warning("matplotlib not installed; skipping PNG comparison plot.")
        return
    h, w = flood_mask.shape
    step = max(1, h // 1000)

    pre_disp = ndwi_pre[::step, ::step]
    post_disp = ndwi_post[::step, ::step]
    mask_disp = flood_mask[::step, ::step]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), gridspec_kw={"wspace": 0.12})
    cmap_ndwi = plt.cm.RdYlBu
    vmin, vmax = -0.5, 0.5

    # Panel 1: Pre-Flood NDWI
    ax = axes[0]
    im0 = ax.imshow(pre_disp, cmap=cmap_ndwi, vmin=vmin, vmax=vmax, interpolation="bilinear")
    ax.set_title("Pre-Flood Baseline NDWI\n(June 2017 Dry Season)", fontsize=11, fontweight="bold", pad=8)
    ax.axis("off")
    cb0 = plt.colorbar(im0, ax=ax, fraction=0.046, pad=0.04)
    cb0.set_label("NDWI", fontsize=9)

    # Panel 2: Post-Flood NDWI
    ax = axes[1]
    im1 = ax.imshow(post_disp, cmap=cmap_ndwi, vmin=vmin, vmax=vmax, interpolation="bilinear")
    ax.set_title("Post-Flood Inundation NDWI\n(August 2017 Post-Peak Flood)", fontsize=11, fontweight="bold", pad=8)
    ax.axis("off")
    cb1 = plt.colorbar(im1, ax=ax, fraction=0.046, pad=0.04)
    cb1.set_label("NDWI", fontsize=9)

    # Panel 3: Inundation Dynamics Mask
    ax = axes[2]
    # Colors: 0=dry land (tan), 1=newly flooded (bright cyan), 2=persistent water (deep navy), 255=unobserved (grey)
    dh, dw = mask_disp.shape
    rgb = np.zeros((dh, dw, 3), dtype=np.float32)
    COLOR_LAND = np.array([0.86, 0.82, 0.72])
    COLOR_NEW_FLOOD = np.array([0.10, 0.65, 0.95])
    COLOR_PERSISTENT = np.array([0.05, 0.20, 0.60])
    COLOR_UNOBSERVED = np.array([0.75, 0.75, 0.75])

    rgb[mask_disp == 0] = COLOR_LAND
    rgb[mask_disp == 1] = COLOR_NEW_FLOOD
    rgb[mask_disp == 2] = COLOR_PERSISTENT
    rgb[mask_disp == 255] = COLOR_UNOBSERVED

    ax.imshow(rgb, interpolation="nearest")
    ax.set_title("Optical Flood Dynamics Mask\n(Conservative SCL-Masked)", fontsize=11, fontweight="bold", pad=8)
    ax.axis("off")

    legend_items = [
        Patch(facecolor=COLOR_NEW_FLOOD, edgecolor="navy", label="Newly Inundated Floodwater"),
        Patch(facecolor=COLOR_PERSISTENT, edgecolor="black", label="Persistent Water (Rivers/Ponds)"),
        Patch(facecolor=COLOR_LAND, edgecolor="saddlebrown", label="Dry Land / Non-Water"),
        Patch(facecolor=COLOR_UNOBSERVED, edgecolor="grey", label="Unobserved (Cloud/Shadow/NoData/Ambiguous)"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8, framealpha=0.9)

    if stats:
        fl_km2 = stats.get("new_flood_km2", 0.0)
        cov_pct = stats.get("valid_shared_pct", 0.0)
        policy_lbl = stats.get("scl_policy", "conservative").capitalize()
        ax.text(
            0.03, 0.03,
            f"Policy: {policy_lbl}\nNew Flood Extent: {fl_km2:.2f} km²\nShared Valid Coverage: {cov_pct:.1f}%",
            transform=ax.transAxes,
            fontsize=8,
            color="white",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc="navy", alpha=0.85),
        )

    fig.suptitle(title, fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def process_optical_flood_pair(
    pre_green_path: Path,
    pre_nir_path: Path,
    post_green_path: Path,
    post_nir_path: Path,
    out_dir: Path,
    pre_scl_path: Optional[Path] = None,
    post_scl_path: Optional[Path] = None,
    threshold: float = DEFAULT_NDWI_THRESHOLD,
    job_id: str = "optical_flood",
    scl_policy: str = "conservative",
    boa_offset: float = 0.0,
    scale_factor: float = DEFAULT_QUANTIFICATION_VALUE,
) -> Dict[str, Any]:
    """Execute complete reproducible pre/post optical flood processing pipeline.

    Parameters:
        pre_green_path: Path to pre-flood Green band (B03).
        pre_nir_path: Path to pre-flood NIR band (B08).
        post_green_path: Path to post-flood Green band (B03) — defines target reference grid.
        post_nir_path: Path to post-flood NIR band (B08).
        out_dir: Destination directory for GeoTIFF and GeoJSON artifacts.
        pre_scl_path: Path to pre-flood SCL quality layer.
        post_scl_path: Path to post-flood SCL quality layer.
        threshold: NDWI water threshold (default 0.00).
        job_id: Identifier for job outputs.
        scl_policy: 'conservative' (DEFAULT, masks 0,1,2,3,7,8,9,10,11) or 'permissive'.
        boa_offset: Radiometric BOA offset (0.0 for PB < 04.00, -1000.0 for PB >= 04.00).
        scale_factor: DN quantification value (10000.0).
    """
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio is required for optical flood processing.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Target reference grid defined by Post-Flood Green (B03)
    with rasterio.open(post_green_path) as g_src:
        post_green_raw = g_src.read(1)
        target_profile = g_src.profile.copy()
        target_crs = g_src.crs
        target_transform = g_src.transform
        target_shape = g_src.shape
        nodata_post_g = g_src.nodata

    # Validate Post-Flood NIR (B08) on the EXACT same affine grid
    with rasterio.open(post_nir_path) as n_src:
        post_nir_raw = n_src.read(1)
        post_nir_prof = n_src.profile.copy()
        nodata_post_n = n_src.nodata

    validate_spatial_alignment(
        target_profile, post_nir_prof,
        label_a="Post-flood Green (B03)", label_b="Post-flood NIR (B08)",
        require_identical_grid=True,
    )

    # 2. Baseline Pre-Flood Green and NIR
    with rasterio.open(pre_green_path) as bg_src:
        pre_green_raw = bg_src.read(1)
        pre_green_prof = bg_src.profile.copy()
        nodata_pre_g = bg_src.nodata

    with rasterio.open(pre_nir_path) as bn_src:
        pre_nir_raw = bn_src.read(1)
        pre_nir_prof = bn_src.profile.copy()
        nodata_pre_n = bn_src.nodata

    validate_spatial_alignment(
        pre_green_prof, pre_nir_prof,
        label_a="Pre-flood Green (B03)", label_b="Pre-flood NIR (B08)",
        require_identical_grid=True,
    )

    # Validate pre/post spatial overlap and reproject onto target reference grid if needed
    is_pre_identical = validate_spatial_alignment(
        target_profile, pre_green_prof,
        label_a="Post-flood Target Grid", label_b="Pre-flood Baseline Grid",
        require_identical_grid=False,
    )

    if is_pre_identical:
        pre_green_aligned = pre_green_raw
        pre_nir_aligned = pre_nir_raw
    else:
        # Geospatially reproject baseline onto target reference grid
        pre_green_aligned = reproject_to_target_grid(
            pre_green_raw, pre_green_prof["transform"], pre_green_prof["crs"],
            target_shape, target_transform, target_crs,
            is_categorical=False, src_nodata=nodata_pre_g, dst_nodata=np.nan,
        )
        pre_nir_aligned = reproject_to_target_grid(
            pre_nir_raw, pre_nir_prof["transform"], pre_nir_prof["crs"],
            target_shape, target_transform, target_crs,
            is_categorical=False, src_nodata=nodata_pre_n, dst_nodata=np.nan,
        )

    # 3. Read and Reproject SCL using rasterio transforms and nearest-neighbor resampling
    post_scl = None
    if post_scl_path and post_scl_path.exists():
        with rasterio.open(post_scl_path) as s_src:
            scl_raw = s_src.read(1)
            # Verify spatial overlap with target grid
            validate_spatial_alignment(
                target_profile, s_src.profile,
                label_a="Post-flood Target Grid", label_b="Post-flood SCL",
                require_identical_grid=False,
            )
            post_scl = reproject_to_target_grid(
                scl_raw, s_src.transform, s_src.crs,
                target_shape, target_transform, target_crs,
                is_categorical=True, src_nodata=0, dst_nodata=0,
            )

    pre_scl = None
    if pre_scl_path and pre_scl_path.exists():
        with rasterio.open(pre_scl_path) as ps_src:
            pscl_raw = ps_src.read(1)
            validate_spatial_alignment(
                target_profile, ps_src.profile,
                label_a="Post-flood Target Grid", label_b="Pre-flood SCL",
                require_identical_grid=False,
            )
            pre_scl = reproject_to_target_grid(
                pscl_raw, ps_src.transform, ps_src.crs,
                target_shape, target_transform, target_crs,
                is_categorical=True, src_nodata=0, dst_nodata=0,
            )

    # 4. Radiometric Calibration & Processing-Baseline Scaling
    refl_post_g = dn_to_reflectance(post_green_raw, scale_factor=scale_factor, boa_offset=boa_offset, nodata=nodata_post_g)
    refl_post_n = dn_to_reflectance(post_nir_raw, scale_factor=scale_factor, boa_offset=boa_offset, nodata=nodata_post_n)
    refl_pre_g = dn_to_reflectance(pre_green_aligned, scale_factor=scale_factor, boa_offset=boa_offset, nodata=nodata_pre_g)
    refl_pre_n = dn_to_reflectance(pre_nir_aligned, scale_factor=scale_factor, boa_offset=boa_offset, nodata=nodata_pre_n)

    # 5. Dual-Temporal NDWI Calculation
    ndwi_post = compute_ndwi(refl_post_g, refl_post_n)
    ndwi_pre = compute_ndwi(refl_pre_g, refl_pre_n)

    # 6. SCL Quality Masking according to documented policy
    valid_post = extract_scl_mask(post_scl, target_shape, policy=scl_policy) & ~np.isnan(ndwi_post)
    valid_pre = extract_scl_mask(pre_scl, target_shape, policy=scl_policy) & ~np.isnan(ndwi_pre)

    # 7. Classify 4-State Flood Dynamics
    flood_mask, stats = classify_flood_dynamics(ndwi_pre, ndwi_post, valid_pre, valid_post, threshold=threshold)

    # Compute metric area in km² using projected affine resolution
    res_x = abs(target_transform[0])
    res_y = abs(target_transform[4])
    pixel_area_km2 = (res_x * res_y) / 1e6
    stats["pixel_area_km2"] = pixel_area_km2
    stats["new_flood_km2"] = round(stats["new_flood_pixels"] * pixel_area_km2, 4)
    stats["persistent_water_km2"] = round(stats["persistent_water_pixels"] * pixel_area_km2, 4)
    stats["dry_land_km2"] = round(stats["dry_land_pixels"] * pixel_area_km2, 4)
    stats["valid_shared_km2"] = round(stats["valid_shared_pixels"] * pixel_area_km2, 4)
    stats["total_scene_km2"] = round(stats["total_pixels"] * pixel_area_km2, 4)
    stats["scl_policy"] = scl_policy
    stats["boa_offset"] = boa_offset
    stats["scale_factor"] = scale_factor

    # 8. Save Output GeoTIFFs
    out_flood_mask_path = out_dir / f"{job_id}_flood_mask.tif"
    prof_mask = target_profile.copy()
    prof_mask.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.open(out_flood_mask_path, "w", **prof_mask) as dst:
        dst.write(flood_mask, 1)

    out_pre_ndwi_path = out_dir / f"{job_id}_pre_ndwi.tif"
    prof_float = target_profile.copy()
    prof_float.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(out_pre_ndwi_path, "w", **prof_float) as dst:
        dst.write(ndwi_pre.astype(np.float32), 1)

    out_post_ndwi_path = out_dir / f"{job_id}_post_ndwi.tif"
    with rasterio.open(out_post_ndwi_path, "w", **prof_float) as dst:
        dst.write(ndwi_post.astype(np.float32), 1)

    # 9. Vectorize Newly Inundated Flood Mask
    mp_geom, area_km2, fc_dict = vectorize_mask(flood_mask, target_transform, target_crs, target_value=1)
    for feat in fc_dict.get("features", []):
        feat["properties"].update({
            "job_id": job_id,
            "method": "NDWI",
            "threshold": threshold,
            "scl_policy": scl_policy,
            "new_flood_area_km2": stats["new_flood_km2"],
            "persistent_water_km2": stats["persistent_water_km2"],
            "valid_shared_area_km2": stats["valid_shared_km2"],
            "valid_coverage_pct": stats["valid_shared_pct"],
        })

    out_geojson_path = out_dir / f"{job_id}_flood_extent.geojson"
    with open(out_geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc_dict, f, indent=2)

    # 10. Visualization Plot
    out_png_path = out_dir / f"{job_id}_flood_comparison.png"
    plot_optical_comparison(ndwi_pre, ndwi_post, flood_mask, out_png_path, stats=stats)

    # 11. Provenance Manifest
    result_manifest = {
        "job_id": job_id,
        "method": "NDWI",
        "threshold": threshold,
        "scl_policy": scl_policy,
        "radiometric_calibration": {
            "scale_factor": scale_factor,
            "boa_offset": boa_offset,
        },
        "statistics": stats,
        "artifacts": {
            "flood_mask_tif": str(out_flood_mask_path),
            "pre_ndwi_tif": str(out_pre_ndwi_path),
            "post_ndwi_tif": str(out_post_ndwi_path),
            "flood_extent_geojson": str(out_geojson_path),
            "flood_comparison_png": str(out_png_path),
        },
        "inputs": {
            "pre_green": str(pre_green_path),
            "pre_nir": str(pre_nir_path),
            "pre_scl": str(pre_scl_path) if pre_scl_path else None,
            "post_green": str(post_green_path),
            "post_nir": str(post_nir_path),
            "post_scl": str(post_scl_path) if post_scl_path else None,
        },
    }
    manifest_out = out_dir / f"{job_id}_manifest.json"
    with open(manifest_out, "w", encoding="utf-8") as f:
        json.dump(result_manifest, f, indent=2)

    result_manifest["multipolygon"] = mp_geom
    result_manifest["area_km2"] = stats["new_flood_km2"]
    return result_manifest


def main():
    parser = argparse.ArgumentParser(description="FloodLens AI Optical NDWI Flood Detection")
    parser.add_argument("--pre-dir", type=Path, default=Path("data/historical_koshi_optical/pre_flood"))
    parser.add_argument("--post-dir", type=Path, default=Path("data/historical_koshi_optical/post_flood"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/historical_koshi_optical/outputs"))
    parser.add_argument("--threshold", type=float, default=0.00)
    parser.add_argument("--scl-policy", type=str, default="conservative", choices=["conservative", "permissive"])
    parser.add_argument("--boa-offset", type=float, default=0.0)
    args = parser.parse_args()

    def _find(d: Path, pattern: str) -> Optional[Path]:
        matches = list(d.glob(pattern))
        return matches[0] if matches else None

    pre_g = _find(args.pre_dir, "*B03*.tif")
    pre_n = _find(args.pre_dir, "*B08*.tif")
    pre_s = _find(args.pre_dir, "*SCL*.tif")
    post_g = _find(args.post_dir, "*B03*.tif")
    post_n = _find(args.post_dir, "*B08*.tif")
    post_s = _find(args.post_dir, "*SCL*.tif")

    if not (pre_g and pre_n and post_g and post_n):
        print(f"Error: Missing required bands in {args.pre_dir} or {args.post_dir}")
        sys.exit(1)

    print(f"Running Optical Pre/Post NDWI Flood Detection (Policy: {args.scl_policy})...")
    res = process_optical_flood_pair(
        pre_green_path=pre_g,
        pre_nir_path=pre_n,
        post_green_path=post_g,
        post_nir_path=post_n,
        pre_scl_path=pre_s,
        post_scl_path=post_s,
        out_dir=args.out_dir,
        threshold=args.threshold,
        job_id="historical_koshi_ndwi",
        scl_policy=args.scl_policy,
        boa_offset=args.boa_offset,
    )
    stats = res["statistics"]
    print("\nProcessing complete:")
    print(f"  Quality Policy:            {stats['scl_policy']}")
    print(f"  Valid shared observation: {stats['valid_shared_km2']:.4f} km² ({stats['valid_shared_pct']}%)")
    print(f"  Persistent water:          {stats['persistent_water_km2']:.4f} km²")
    print(f"  Newly inundated flood:     {stats['new_flood_km2']:.4f} km² ({stats['new_flood_pixels']:,} px)")
    print(f"  Dry land:                  {stats['dry_land_km2']:.4f} km²")
    print(f"  Unobserved:                {(stats['total_pixels'] - stats['valid_shared_pixels']) * stats['pixel_area_km2']:.4f} km²")
    print(f"  Artifacts written to:      {args.out_dir}")


if __name__ == "__main__":
    main()
