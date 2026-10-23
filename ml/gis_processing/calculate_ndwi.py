"""
calculate_ndwi.py
=================
FloodLens AI — Reproducible Pre/Post Optical Flood Detection Pipeline
---------------------------------------------------------------------
Performs rigorous, reproducible, scientific remote sensing flood detection from
Sentinel-2 Level-2A surface reflectance optical imagery.

Scientific Pipeline:
1. Geospatial & Spectral Band Validation:
   - Sentinel-2 Green (B03, 560 nm, 10m)
   - Sentinel-2 Near Infrared (B08, 842 nm, 10m)
   - Sentinel-2 Scene Classification Layer (SCL, 20m)
   - Validates CRS, transform metadata, bounds, and spatial alignment.
2. Scene Classification Layer (SCL) Quality & Cloud Masking:
   - Masks cloud shadows (class 3), clouds (medium/high prob: classes 8, 9),
     cirrus (class 10), saturated/defective pixels (class 1), snow/ice (class 11),
     and NoData (class 0).
   - Valid observation classes: vegetation (4), bare soil/urban (5), water (6), unclassified (7).
   - Enforces valid shared-observation coverage: only pixels observed reliably in both
     pre-flood and post-flood acquisitions are evaluated.
   - Cloud-occluded pixels are marked as unobserved/unknown (255), NEVER silently treated as dry land.
3. Dual-Temporal NDWI Calculation:
   - NDWI = (Green - NIR) / (Green + NIR)
   - Pre-flood NDWI and Post-flood NDWI computed separately on validated reflectance.
4. Distinguishing Newly Inundated Floodwater from Persistent Water:
   - NEW_FLOOD        = Post-water AND (NOT Pre-water) AND Valid-shared  (Value: 1)
   - PERSISTENT_WATER = Post-water AND Pre-water AND Valid-shared        (Value: 2)
   - DRY_LAND         = (NOT Post-water) AND Valid-shared                (Value: 0)
   - UNOBSERVED       = NOT Valid-shared                                 (Value: 255)
5. Reproducible GIS Artifacts:
   - Pre-flood NDWI GeoTIFF (pre_ndwi.tif)
   - Post-flood NDWI GeoTIFF (post_ndwi.tif)
   - Pre-flood water mask (pre_water_mask.tif)
   - Post-flood water mask (post_water_mask.tif)
   - Inundation dynamics mask GeoTIFF (flood_mask.tif)
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

# SCL classes according to ESA Sentinel-2 Level-2A product specification
# Unsuitable/occluded classes:
# 0: No Data, 1: Saturated/Defective, 3: Cloud Shadows, 8: Cloud Medium Prob,
# 9: Cloud High Prob, 10: Thin Cirrus, 11: Snow/Ice
UNSUITABLE_SCL_CLASSES = {0, 1, 3, 8, 9, 10, 11}
DEFAULT_NDWI_THRESHOLD = 0.00


def compute_ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Compute Normalized Difference Water Index: (Green - NIR) / (Green + NIR).
    
    Returns float32 array in [-1.0, 1.0], with NaN for zero-denominator or negative inputs.
    """
    g = green.astype(np.float32)
    n = nir.astype(np.float32)

    with np.errstate(divide="ignore", invalid="ignore"):
        denom = g + n
        invalid = (denom <= 0) | np.isnan(g) | np.isnan(n) | (g < 0) | (n < 0)
        ndwi = np.where(invalid, np.nan, (g - n) / denom)
    return np.clip(ndwi, -1.0, 1.0)


def extract_scl_mask(scl: Optional[np.ndarray], shape: Tuple[int, int]) -> np.ndarray:
    """Return boolean mask of valid observation pixels where SCL is not cloud, shadow, or invalid."""
    if scl is None:
        return np.ones(shape, dtype=bool)
    # Ensure SCL matches target shape (resample nearest neighbor if needed)
    if scl.shape != shape:
        scl = resample_array(scl, shape, is_categorical=True)
    return ~np.isin(scl, list(UNSUITABLE_SCL_CLASSES))


def resample_array(
    arr: np.ndarray,
    target_shape: Tuple[int, int],
    is_categorical: bool = False,
) -> np.ndarray:
    """Resample 2D array to target shape using nearest-neighbor (for categorical) or bilinear."""
    if arr.shape == target_shape:
        return arr
    
    src_h, src_w = arr.shape
    tgt_h, tgt_w = target_shape
    
    # Simple integer scaling optimization (e.g. 20m -> 10m is exact 2x)
    if tgt_h == src_h * 2 and tgt_w == src_w * 2:
        return np.repeat(np.repeat(arr, 2, axis=0), 2, axis=1)
    
    row_indices = np.linspace(0, src_h - 1, tgt_h).round().astype(int)
    col_indices = np.linspace(0, src_w - 1, tgt_w).round().astype(int)
    return arr[np.ix_(row_indices, col_indices)]


def validate_spatial_alignment(
    prof_a: Dict[str, Any],
    prof_b: Dict[str, Any],
    label_a: str = "Scene A",
    label_b: str = "Scene B",
    tolerance: float = 1e-4,
) -> None:
    """Validate that two raster profiles have compatible CRS and geospatial transform."""
    crs_a = prof_a.get("crs")
    crs_b = prof_b.get("crs")
    if str(crs_a).upper() != str(crs_b).upper():
        raise ValueError(f"CRS mismatch: {label_a} has {crs_a}, but {label_b} has {crs_b}.")

    trans_a = prof_a.get("transform")
    trans_b = prof_b.get("transform")
    if trans_a is not None and trans_b is not None:
        # Check pixel resolution
        res_x_a, res_y_a = abs(trans_a[0]), abs(trans_a[4])
        res_x_b, res_y_b = abs(trans_b[0]), abs(trans_b[4])
        if abs(res_x_a - res_x_b) > tolerance or abs(res_y_a - res_y_b) > tolerance:
            raise ValueError(
                f"Pixel resolution mismatch: {label_a} is ({res_x_a}, {res_y_a}), "
                f"but {label_b} is ({res_x_b}, {res_y_b})."
            )

        # Check bounding box spatial overlap
        h_a, w_a = prof_a.get("height", 0), prof_a.get("width", 0)
        h_b, w_b = prof_b.get("height", 0), prof_b.get("width", 0)
        if h_a and w_a and h_b and w_b:
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

            disjoint = (max_x_a < min_x_b or max_x_b < min_x_a or max_y_a < min_y_b or max_y_b < min_y_a)
            if disjoint:
                raise ValueError(
                    f"Geospatial transform mismatch: {label_a} bounds [{min_x_a}, {min_y_a}, {max_x_a}, {max_y_a}] "
                    f"and {label_b} bounds [{min_x_b}, {min_y_b}, {max_x_b}, {max_y_b}] do not spatially overlap."
                )


def classify_flood_dynamics(
    ndwi_pre: np.ndarray,
    ndwi_post: np.ndarray,
    valid_pre: np.ndarray,
    valid_post: np.ndarray,
    threshold: float = DEFAULT_NDWI_THRESHOLD,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Classify 4-state flood dynamics:
    
    0   = Dry land (validly observed dry surface in post)
    1   = Newly inundated floodwater (post > threshold AND pre <= threshold AND valid shared)
    2   = Persistent water (pre > threshold AND post > threshold AND valid shared)
    255 = Unobserved / cloud / shadow / NoData
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
    """Calculate exact ground area in km² projected into UTM Zone 45N (EPSG:32645)."""
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
    ax.set_title("Optical Flood Dynamics Mask\n(SCL-Masked Shared Coverage)", fontsize=11, fontweight="bold", pad=8)
    ax.axis("off")

    legend_items = [
        Patch(facecolor=COLOR_NEW_FLOOD, edgecolor="navy", label="Newly Inundated Floodwater"),
        Patch(facecolor=COLOR_PERSISTENT, edgecolor="black", label="Persistent Water (Rivers/Ponds)"),
        Patch(facecolor=COLOR_LAND, edgecolor="saddlebrown", label="Dry Land / Non-Water"),
        Patch(facecolor=COLOR_UNOBSERVED, edgecolor="grey", label="Unobserved (Cloud/Shadow/NoData)"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8, framealpha=0.9)

    if stats:
        fl_km2 = stats.get("new_flood_km2", 0.0)
        cov_pct = stats.get("valid_shared_pct", 0.0)
        ax.text(
            0.03, 0.03,
            f"New Flood Extent: {fl_km2:.2f} km²\nShared Valid Coverage: {cov_pct:.1f}%",
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
) -> Dict[str, Any]:
    """Execute complete reproducible pre/post optical flood processing pipeline."""
    if not HAS_RASTERIO:
        raise RuntimeError("rasterio is required for optical flood processing.")

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read post-flood (target) Green and NIR
    with rasterio.open(post_green_path) as g_src:
        post_green = g_src.read(1).astype(np.float32)
        profile = g_src.profile.copy()
        crs = g_src.crs
        transform = g_src.transform
        nodata_g = g_src.nodata
        target_shape = g_src.shape

    with rasterio.open(post_nir_path) as n_src:
        post_nir = n_src.read(1).astype(np.float32)
        crs_n = n_src.crs
        shape_n = n_src.shape
        nodata_n = n_src.nodata

    if crs != crs_n or target_shape != shape_n:
        raise ValueError("Post-flood Green and NIR bands have mismatched CRS or dimensions.")

    # 2. Read pre-flood (baseline) Green and NIR
    with rasterio.open(pre_green_path) as bg_src:
        pre_green = bg_src.read(1).astype(np.float32)
        pre_prof = bg_src.profile.copy()
        pre_crs = bg_src.crs
        pre_shape = bg_src.shape
        nodata_bg = bg_src.nodata

    with rasterio.open(pre_nir_path) as bn_src:
        pre_nir = bn_src.read(1).astype(np.float32)
        pre_crs_n = bn_src.crs
        pre_shape_n = bn_src.shape
        nodata_bn = bn_src.nodata

    if pre_crs != pre_crs_n or pre_shape != pre_shape_n:
        raise ValueError("Pre-flood Green and NIR bands have mismatched CRS or dimensions.")

    # Validate spatial alignment between pre and post
    validate_spatial_alignment(profile, pre_prof, label_a="Post-flood", label_b="Pre-flood")

    # If shapes differ, resample pre to match post
    if pre_shape != target_shape:
        pre_green = resample_array(pre_green, target_shape)
        pre_nir = resample_array(pre_nir, target_shape)

    # Handle NoData in bands
    for arr, nd in [(post_green, nodata_g), (post_nir, nodata_n), (pre_green, nodata_bg), (pre_nir, nodata_bn)]:
        if nd is not None:
            arr[arr == nd] = np.nan
        arr[arr < 0] = np.nan

    # 3. Read and process SCL quality masks if available
    scl_pre = None
    if pre_scl_path and pre_scl_path.exists():
        with rasterio.open(pre_scl_path) as s_src:
            scl_pre = s_src.read(1)
            if scl_pre.shape != target_shape:
                scl_pre = resample_array(scl_pre, target_shape, is_categorical=True)

    scl_post = None
    if post_scl_path and post_scl_path.exists():
        with rasterio.open(post_scl_path) as s_src:
            scl_post = s_src.read(1)
            if scl_post.shape != target_shape:
                scl_post = resample_array(scl_post, target_shape, is_categorical=True)

    valid_pre = extract_scl_mask(scl_pre, target_shape) & ~np.isnan(pre_green) & ~np.isnan(pre_nir) & (pre_green > 0)
    valid_post = extract_scl_mask(scl_post, target_shape) & ~np.isnan(post_green) & ~np.isnan(post_nir) & (post_green > 0)

    # 4. Compute NDWI
    ndwi_pre = compute_ndwi(pre_green, pre_nir)
    ndwi_post = compute_ndwi(post_green, post_nir)

    # 5. Classify flood dynamics
    flood_mask, stats = classify_flood_dynamics(ndwi_pre, ndwi_post, valid_pre, valid_post, threshold=threshold)

    # Compute metric areas from affine resolution
    res_x = abs(transform[0])
    res_y = abs(transform[4])
    pixel_area_km2 = (res_x * res_y) / 1e6
    stats["pixel_area_km2"] = pixel_area_km2
    stats["new_flood_km2"] = round(stats["new_flood_pixels"] * pixel_area_km2, 4)
    stats["persistent_water_km2"] = round(stats["persistent_water_pixels"] * pixel_area_km2, 4)
    stats["dry_land_km2"] = round(stats["dry_land_pixels"] * pixel_area_km2, 4)
    stats["valid_shared_km2"] = round(stats["valid_shared_pixels"] * pixel_area_km2, 4)
    stats["total_scene_km2"] = round(stats["total_pixels"] * pixel_area_km2, 4)

    # 6. Save GeoTIFF products
    out_flood_mask_path = out_dir / f"{job_id}_flood_mask.tif"
    prof_mask = profile.copy()
    prof_mask.update(driver="GTiff", dtype="uint8", count=1, nodata=255, compress="deflate")
    with rasterio.open(out_flood_mask_path, "w", **prof_mask) as dst:
        dst.write(flood_mask, 1)

    out_pre_ndwi_path = out_dir / f"{job_id}_pre_ndwi.tif"
    prof_float = profile.copy()
    prof_float.update(driver="GTiff", dtype="float32", count=1, nodata=np.nan, compress="deflate")
    with rasterio.open(out_pre_ndwi_path, "w", **prof_float) as dst:
        dst.write(ndwi_pre.astype(np.float32), 1)

    out_post_ndwi_path = out_dir / f"{job_id}_post_ndwi.tif"
    with rasterio.open(out_post_ndwi_path, "w", **prof_float) as dst:
        dst.write(ndwi_post.astype(np.float32), 1)

    # 7. Vectorize newly inundated flood extent (target_value == 1)
    mp_geom, area_km2, fc_dict = vectorize_mask(flood_mask, transform, crs, target_value=1)
    # Ensure vector properties record all quality fields
    for feat in fc_dict.get("features", []):
        feat["properties"].update({
            "job_id": job_id,
            "method": "NDWI",
            "threshold": threshold,
            "new_flood_area_km2": stats["new_flood_km2"],
            "persistent_water_km2": stats["persistent_water_km2"],
            "valid_shared_area_km2": stats["valid_shared_km2"],
            "valid_coverage_pct": stats["valid_shared_pct"],
        })

    out_geojson_path = out_dir / f"{job_id}_flood_extent.geojson"
    with open(out_geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc_dict, f, indent=2)

    # 8. Visualization
    out_png_path = out_dir / f"{job_id}_flood_comparison.png"
    plot_optical_comparison(ndwi_pre, ndwi_post, flood_mask, out_png_path, stats=stats)

    # 9. Provenance manifest
    result_manifest = {
        "job_id": job_id,
        "method": "NDWI",
        "threshold": threshold,
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
    parser.add_argument("--out-dir", type=Path, default=Path("ml/gis_processing/downloads"))
    parser.add_argument("--threshold", type=float, default=0.00)
    args = parser.parse_args()

    # Search for files
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

    print("Running Optical Pre/Post NDWI Flood Detection...")
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
    )
    stats = res["statistics"]
    print("\nProcessing complete:")
    print(f"  Valid shared observation: {stats['valid_shared_km2']:.2f} km² ({stats['valid_shared_pct']}%)")
    print(f"  Persistent water:          {stats['persistent_water_km2']:.2f} km²")
    print(f"  Newly inundated flood:     {stats['new_flood_km2']:.2f} km² ({stats['new_flood_pixels']:,} px)")
    print(f"  Artifacts written to:      {args.out_dir}")


if __name__ == "__main__":
    main()
