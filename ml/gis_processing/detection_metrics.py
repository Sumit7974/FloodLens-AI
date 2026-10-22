"""
detection_metrics.py
====================
FloodLens AI — Scientific GIS Detection Accuracy Validation Engine
------------------------------------------------------------------
Provides rigorous, reproducible, programmatic remote sensing accuracy assessment
for flood extent masks following ISO 19157 (Geographic information — Data quality).

Key Scientific Guarantees:
1. Replaces hardcoded confusion matrix counts with empirical pixel evaluations.
2. Derives spatial resolution and cell areas directly from raster georeferencing
   affine transforms, avoiding fixed pixel-size assumptions.
3. Excludes uncovered, invalid, and NoData regions during raster alignment rather
   than treating unmapped territory as valid dry land.
4. Performs spatial, temporal, and coordinate reference system (CRS) alignment
   using nearest-neighbor resampling for categorical/binary masks.
5. Strictly distinguishes independent ground-truth validation from cross-sensor
   satellite inter-comparison (e.g. Optical vs SAR) and unit test fixtures.
   Synthetic test fixtures never qualify as empirical ground-truth validation.
6. A recognized string label alone (e.g. "COPERNICUS_EMS_VERIFIED") does NOT establish
   independent validation. Empirical validation requires verifiable reference evidence:
   identifiable source product, acquisition date, source URI or archive identifier,
   checksum, reference methodology, and an independent verification decision.
7. When no independent reference mask is available, truthfully reports
   status="NOT_VALIDATED" with detailed missing evidence declarations.
8. Rejects circular validation (evaluating a prediction against itself).
9. In cross-sensor vector evaluation, explicitly clips each geometry to the shared
   comparison footprint before projection, union, and IoU calculations.
10. Transparently distinguishes actual satellite acquisition footprints from bounding
    boxes inferred from detected flood polygons.

Author: FloodLens AI GIS & Remote Sensing Team
"""

import os
import sys
import math
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import numpy as np

# Optional rasterio import for GeoTIFF raster operations
try:
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

# Optional shapely import for vector geometric comparisons
try:
    from shapely.geometry import shape, box, mapping, Polygon, MultiPolygon
    from shapely.ops import unary_union, transform as shapely_transform
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    NOT_VALIDATED = "NOT_VALIDATED"
    UNVERIFIED = "UNVERIFIED"
    TEST_FIXTURE_VERIFIED = "TEST_FIXTURE_VERIFIED"
    CIRCULAR_REFERENCE_REJECTED = "CIRCULAR_REFERENCE_REJECTED"
    INVALID_INPUT = "INVALID_INPUT"


# Documented evidence fields required for empirical ground-truth validation
REQUIRED_EVIDENCE_FIELDS: Set[str] = {
    "source_product",
    "acquisition_date",
    "source_uri_or_id",
    "checksum",
    "reference_methodology",
    "independent_verification_decision"
}


# ---------------------------------------------------------------------------
# COORDINATE TRANSFORMATION UTILITIES (Pure-Python Fallback & Pyproj)
# ---------------------------------------------------------------------------
def project_wgs84_to_utm45n(lon: float, lat: float) -> Tuple[float, float]:
    """
    Mathematical forward transverse Mercator projection from WGS84 (lon, lat in deg)
    to UTM Zone 45N (EPSG:32645; central meridian 87°E, false easting 500,000m).
    Provides a standalone fallback that operates without requiring external C libraries.
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    b = a * (1.0 - f)
    e2 = (a**2 - b**2) / (a**2)
    ep2 = (a**2 - b**2) / (b**2)

    k0 = 0.9996
    lon0 = 87.0 * math.pi / 180.0

    phi = lat * math.pi / 180.0
    lam = lon * math.pi / 180.0

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    N = a / math.sqrt(1.0 - e2 * (sin_phi**2))
    T = tan_phi**2
    C = ep2 * (cos_phi**2)
    A = (lam - lon0) * cos_phi

    M = a * (
        (1.0 - e2 / 4.0 - 3.0 * (e2**2) / 64.0 - 5.0 * (e2**3) / 256.0) * phi
        - (3.0 * e2 / 8.0 + 3.0 * (e2**2) / 32.0 + 45.0 * (e2**3) / 1024.0) * math.sin(2.0 * phi)
        + (15.0 * (e2**2) / 256.0 + 45.0 * (e2**3) / 1024.0) * math.sin(4.0 * phi)
        - (35.0 * (e2**3) / 3072.0) * math.sin(6.0 * phi)
    )

    easting = 500000.0 + k0 * N * (
        A
        + (1.0 - T + C) * (A**3) / 6.0
        + (5.0 - 18.0 * T + (T**2) + 72.0 * C - 58.0 * ep2) * (A**5) / 120.0
    )
    northing = k0 * (
        M
        + N * tan_phi * (
            (A**2) / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * (C**2)) * (A**4) / 24.0
            + (61.0 - 58.0 * T + (T**2) + 600.0 * C - 330.0 * ep2) * (A**6) / 720.0
        )
    )
    return easting, northing


def transform_geom_to_utm45n(geom: Any) -> Any:
    """Transforms a Shapely geometry from WGS84 (EPSG:4326) to UTM Zone 45N (EPSG:32645)."""
    if not HAS_SHAPELY or geom is None:
        return geom
    try:
        import pyproj
        tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32645", always_xy=True)
        return shapely_transform(tr.transform, geom)
    except Exception:
        return shapely_transform(project_wgs84_to_utm45n, geom)


# ---------------------------------------------------------------------------
# CONFUSION MATRIX & ACCURACY INDICATORS
# ---------------------------------------------------------------------------
def calculate_confusion_matrix(
    pred_mask: np.ndarray,
    ref_mask: np.ndarray,
    valid_mask: Optional[np.ndarray] = None,
    nodata_values: Optional[Set[Union[int, float]]] = None
) -> Dict[str, int]:
    """
    Computes confusion matrix counts (TP, FP, FN, TN) between predicted and reference binary masks.
    Excludes invalid, uncovered, and NoData pixels so unmapped regions are NOT counted as dry land.
    """
    if pred_mask is None or ref_mask is None:
        raise ValueError("Both pred_mask and ref_mask must be provided.")

    if not isinstance(pred_mask, np.ndarray) or not isinstance(ref_mask, np.ndarray):
        pred_mask = np.asarray(pred_mask)
        ref_mask = np.asarray(ref_mask)

    if pred_mask.shape != ref_mask.shape:
        raise ValueError(
            f"Shape mismatch: pred_mask shape {pred_mask.shape} != ref_mask shape {ref_mask.shape}"
        )

    if pred_mask.size == 0:
        raise ValueError("Cannot evaluate empty masks (zero pixels).")

    # Establish default NoData values
    if nodata_values is None:
        active_nodata: Set[Union[int, float]] = {255, -9999, -32768}
    else:
        active_nodata = set(nodata_values)
        active_nodata.update({255, -9999, -32768})

    # Build active valid pixel mask
    is_valid = np.ones(pred_mask.shape, dtype=bool)

    # Exclude NaNs if floating point
    if np.issubdtype(pred_mask.dtype, np.floating):
        is_valid &= ~np.isnan(pred_mask)
    if np.issubdtype(ref_mask.dtype, np.floating):
        is_valid &= ~np.isnan(ref_mask)

    # Exclude NoData values in either raster
    for nd in active_nodata:
        is_valid &= (pred_mask != nd) & (ref_mask != nd)

    # Apply external valid mask (e.g. cloud/shadow mask, common boundary)
    if valid_mask is not None:
        if valid_mask.shape != pred_mask.shape:
            raise ValueError(
                f"valid_mask shape {valid_mask.shape} does not match mask shape {pred_mask.shape}"
            )
        is_valid &= valid_mask.astype(bool)

    total_pixels = int(pred_mask.size)
    valid_count = int(np.sum(is_valid))
    nodata_count = total_pixels - valid_count

    if valid_count == 0:
        return {
            "tp_pixels": 0,
            "fp_pixels": 0,
            "fn_pixels": 0,
            "tn_pixels": 0,
            "total_evaluated": 0,
            "nodata_excluded": nodata_count
        }

    p_valid = pred_mask[is_valid]
    r_valid = ref_mask[is_valid]

    # Convert to binary flags (positive flood = 1, negative non-flood = 0)
    p_bin = (p_valid > 0).astype(np.int32)
    r_bin = (r_valid > 0).astype(np.int32)

    tp = int(np.sum((p_bin == 1) & (r_bin == 1)))
    fp = int(np.sum((p_bin == 1) & (r_bin == 0)))
    fn = int(np.sum((p_bin == 0) & (r_bin == 1)))
    tn = int(np.sum((p_bin == 0) & (r_bin == 0)))

    return {
        "tp_pixels": tp,
        "fp_pixels": fp,
        "fn_pixels": fn,
        "tn_pixels": tn,
        "total_evaluated": valid_count,
        "nodata_excluded": nodata_count
    }


def derive_binary_metrics(
    tp: int,
    fp: int,
    tn: int,
    fn: int,
    decimals: int = 4
) -> Dict[str, Optional[float]]:
    """
    Computes standard remote-sensing accuracy indicators from confusion matrix counts.
    Handles zero denominators safely without division-by-zero crashes.
    """
    total = tp + fp + tn + fn

    if total == 0:
        return {
            "precision_user_accuracy": None,
            "recall_producer_accuracy": None,
            "f1_score_dice_coefficient": None,
            "iou_jaccard_index": None,
            "overall_accuracy": None,
            "cohens_kappa": None,
            "commission_error_rate": None,
            "omission_error_rate": None
        }

    pred_pos = tp + fp
    precision = (tp / pred_pos) if pred_pos > 0 else 0.0

    actual_pos = tp + fn
    recall = (tp / actual_pos) if actual_pos > 0 else 0.0

    f1_denom = (2 * tp + fp + fn)
    f1_score = (2.0 * tp / f1_denom) if f1_denom > 0 else 0.0

    union = tp + fp + fn
    iou = (tp / union) if union > 0 else 0.0

    overall_accuracy = (tp + tn) / total
    commission_error = (fp / pred_pos) if pred_pos > 0 else 0.0
    omission_error = (fn / actual_pos) if actual_pos > 0 else 0.0

    # Cohen's Kappa Coefficient
    p_obs = overall_accuracy
    p_chance = float(
        ((pred_pos * actual_pos) + ((fn + tn) * (fp + tn))) / (total ** 2)
    )

    if (1.0 - p_chance) != 0:
        kappa = (p_obs - p_chance) / (1.0 - p_chance)
        kappa = max(-1.0, min(1.0, kappa))
    else:
        kappa = 1.0 if p_obs == 1.0 else 0.0

    return {
        "precision_user_accuracy": round(precision, decimals),
        "recall_producer_accuracy": round(recall, decimals),
        "f1_score_dice_coefficient": round(f1_score, decimals),
        "iou_jaccard_index": round(iou, decimals),
        "overall_accuracy": round(overall_accuracy, decimals),
        "cohens_kappa": round(kappa, decimals),
        "commission_error_rate": round(commission_error, decimals),
        "omission_error_rate": round(omission_error, decimals)
    }


# ---------------------------------------------------------------------------
# FULL SCIENTIFIC ACCURACY EVALUATION (ISO 19157)
# ---------------------------------------------------------------------------
def evaluate_flood_detection_accuracy(
    pred_mask: Optional[Union[np.ndarray, str, Path]] = None,
    ref_mask: Optional[Union[np.ndarray, str, Path]] = None,
    valid_mask: Optional[np.ndarray] = None,
    nodata_values: Optional[Set[Union[int, float]]] = None,
    pixel_size_m: Optional[float] = None,
    reference_provenance: Optional[Union[str, Dict[str, Any]]] = None,
    reference_evidence: Optional[Dict[str, Any]] = None,
    is_test_fixture: bool = False
) -> Dict[str, Any]:
    """
    Conducts scientific flood detection evaluation between prediction and independent reference.

    Guarantees:
      - Returns NOT_VALIDATED if reference data is missing.
      - Returns CIRCULAR_REFERENCE_REJECTED if prediction is compared against itself.
      - Derives cell resolution and area directly from raster georeferencing affine transform.
      - Reprojects reference data using nearest-neighbor resampling and explicitly marks
        uncovered/out-of-bounds pixels as NoData (excluding them from evaluation).
      - Returns TEST_FIXTURE_VERIFIED for automated test fixtures (never empirical ground truth).
      - Returns UNVERIFIED if reference data lacks documented independent evidence.
        A recognized label alone (e.g. "COPERNICUS_EMS_VERIFIED") does NOT establish validation.
      - Returns VALIDATED ONLY when documented reference evidence is provided and confirmed.
    """
    # 1. Missing Reference Safety Check
    if ref_mask is None:
        return {
            "validation_status": ValidationStatus.NOT_VALIDATED.value,
            "summary": "Independent reference flood ground-truth data is not available. Accuracy metrics cannot be scientifically claimed.",
            "missing_evidence": [
                "Independent authoritative reference flood mask (e.g. Copernicus EMS rapid mapping, field survey extents, or calibrated aerial survey) was not supplied.",
                "Radar-optical cross-sensor comparison alone cannot substitute for independent ground truth."
            ],
            "confusion_matrix_pixels": None,
            "confusion_matrix_area_km2": None,
            "detection_performance_indicators": None,
            "reference_provenance": "NONE_AVAILABLE",
            "scientific_limitation": "Without validated independent ground-truth data, precision, recall, and IoU figures cannot be verified."
        }

    # 2. Circular Validation Check
    if isinstance(pred_mask, (str, Path)) and isinstance(ref_mask, (str, Path)):
        if Path(pred_mask).resolve() == Path(ref_mask).resolve():
            return {
                "validation_status": ValidationStatus.CIRCULAR_REFERENCE_REJECTED.value,
                "summary": "Circular validation rejected: prediction mask and reference mask point to the identical file path.",
                "error": "A model cannot be validated against its own output.",
                "confusion_matrix_pixels": None,
                "detection_performance_indicators": None
            }

    # 3. Load Arrays & Georeferencing
    p_arr: Optional[np.ndarray] = None
    r_arr: Optional[np.ndarray] = None
    alignment_info: Dict[str, Any] = {
        "resampling_method": "nearest_neighbor"
    }

    derived_pixel_area_m2: Optional[float] = None
    active_nodata_set = set(nodata_values) if nodata_values else {255, -9999, -32768}

    if isinstance(pred_mask, (str, Path)) or isinstance(ref_mask, (str, Path)):
        if not HAS_RASTERIO:
            raise RuntimeError("rasterio library is required to read raster files from disk.")

        p_transform = None
        p_crs = None
        p_bounds = None

        if isinstance(pred_mask, (str, Path)):
            with rasterio.open(pred_mask) as src_p:
                p_arr = src_p.read(1)
                p_crs = src_p.crs
                p_transform = src_p.transform
                p_bounds = src_p.bounds
                alignment_info["pred_crs"] = str(p_crs)
                alignment_info["pred_shape"] = p_arr.shape
                if src_p.nodata is not None:
                    active_nodata_set.add(src_p.nodata)

                # Derive pixel area from raster georeferencing affine transform
                if p_crs and p_crs.is_projected:
                    dx_m = abs(p_transform.a)
                    dy_m = abs(p_transform.e)
                    derived_pixel_area_m2 = dx_m * dy_m
                    alignment_info["pixel_width_m"] = round(dx_m, 2)
                    alignment_info["pixel_height_m"] = round(dy_m, 2)
                    alignment_info["pixel_area_source"] = "projected_raster_affine_transform"
                elif p_bounds:
                    center_lat = (p_bounds.top + p_bounds.bottom) / 2.0
                    m_per_deg_lat = 111139.0
                    m_per_deg_lon = 111139.0 * math.cos(math.radians(center_lat))
                    dx_m = abs(p_transform.a) * m_per_deg_lon
                    dy_m = abs(p_transform.e) * m_per_deg_lat
                    derived_pixel_area_m2 = dx_m * dy_m
                    alignment_info["pixel_width_m"] = round(dx_m, 2)
                    alignment_info["pixel_height_m"] = round(dy_m, 2)
                    alignment_info["pixel_area_source"] = "geographic_raster_geodesic_scaled"

        if isinstance(ref_mask, (str, Path)):
            with rasterio.open(ref_mask) as src_r:
                r_arr = src_r.read(1)
                r_crs = src_r.crs
                r_transform = src_r.transform
                r_bounds = src_r.bounds
                alignment_info["ref_crs"] = str(r_crs)
                alignment_info["ref_shape"] = r_arr.shape
                ref_nodata = src_r.nodata if src_r.nodata is not None else 255
                active_nodata_set.add(ref_nodata)

                # Reproject and align reference raster to prediction grid
                if isinstance(pred_mask, (str, Path)):
                    if p_crs != r_crs or p_arr.shape != r_arr.shape or p_transform != r_transform:
                        # CRITICAL: Initialize aligned array with ref_nodata so that ANY pixel
                        # outside the reference coverage is marked NoData, NOT false dry land (0).
                        r_aligned = np.full(p_arr.shape, fill_value=ref_nodata, dtype=r_arr.dtype)
                        reproject(
                            source=r_arr,
                            destination=r_aligned,
                            src_transform=r_transform,
                            src_crs=r_crs,
                            dst_transform=p_transform,
                            dst_crs=p_crs,
                            src_nodata=src_r.nodata,
                            dst_nodata=ref_nodata,
                            resampling=Resampling.nearest
                        )
                        r_arr = r_aligned
                        alignment_info["resampled"] = True
                        alignment_info["aligned_to"] = "prediction_grid"
                        alignment_info["uncovered_pixels_fill_nodata"] = ref_nodata
    else:
        p_arr = np.asarray(pred_mask)
        r_arr = np.asarray(ref_mask)

    if p_arr.shape != r_arr.shape:
        raise ValueError(f"Array shape mismatch: {p_arr.shape} vs {r_arr.shape}")

    # Fallback pixel area if in-memory array provided
    if derived_pixel_area_m2 is None:
        p_size = pixel_size_m if pixel_size_m is not None else 10.0
        derived_pixel_area_m2 = float(p_size * p_size)
        alignment_info["pixel_width_m"] = p_size
        alignment_info["pixel_height_m"] = p_size
        alignment_info["pixel_area_source"] = "user_supplied_or_default_size"

    alignment_info["pixel_area_m2"] = round(derived_pixel_area_m2, 4)

    # 4. Programmatic Confusion Matrix Computation
    cm = calculate_confusion_matrix(
        pred_mask=p_arr,
        ref_mask=r_arr,
        valid_mask=valid_mask,
        nodata_values=active_nodata_set
    )

    pixel_area_km2 = derived_pixel_area_m2 / 1e6
    cm_area_km2 = {
        "true_positive_km2": round(cm["tp_pixels"] * pixel_area_km2, 4),
        "false_positive_km2": round(cm["fp_pixels"] * pixel_area_km2, 4),
        "false_negative_km2": round(cm["fn_pixels"] * pixel_area_km2, 4),
        "true_negative_km2": round(cm["tn_pixels"] * pixel_area_km2, 4),
        "total_evaluated_km2": round(cm["total_evaluated"] * pixel_area_km2, 4)
    }

    # 5. Derive Performance Metrics
    metrics = derive_binary_metrics(
        tp=cm["tp_pixels"],
        fp=cm["fp_pixels"],
        tn=cm["tn_pixels"],
        fn=cm["fn_pixels"]
    )

    # 6. Determine Scientific Validation Status & Provenance Evidence
    # Require verifiable reference evidence: label strings alone NEVER establish validation
    evidence_dict: Optional[Dict[str, Any]] = None
    if isinstance(reference_evidence, dict):
        evidence_dict = reference_evidence
    elif isinstance(reference_provenance, dict):
        evidence_dict = reference_provenance

    prov_str = str(reference_provenance or "").strip().upper() if isinstance(reference_provenance, str) else ""
    is_fixture = is_test_fixture or prov_str.startswith("TEST_") or prov_str == "FIXTURE"

    if is_fixture:
        status = ValidationStatus.TEST_FIXTURE_VERIFIED.value
        status_note = (
            "Evaluation performed against verified test fixture. Validates algorithm correctness; "
            "never qualifies as empirical ground-truth validation."
        )
        prov_recorded = reference_provenance if isinstance(reference_provenance, str) else "TEST_FIXTURE"
        evidence_summary = None
    elif evidence_dict is not None:
        missing_fields = [
            f for f in REQUIRED_EVIDENCE_FIELDS
            if not evidence_dict.get(f) or (isinstance(evidence_dict.get(f), str) and not evidence_dict.get(f).strip())
        ]
        ver_decision = evidence_dict.get("independent_verification_decision")
        decision_valid = False
        if isinstance(ver_decision, bool) and ver_decision is True:
            decision_valid = True
        elif isinstance(ver_decision, str) and ver_decision.strip().upper() in {"VERIFIED", "APPROVED", "AUTHENTICATED", "CONFIRMED"}:
            decision_valid = True

        if missing_fields or not decision_valid:
            status = ValidationStatus.UNVERIFIED.value
            status_note = (
                f"Reference evidence is incomplete or unverified. Missing or invalid required fields: "
                f"{missing_fields or ['independent_verification_decision']}. "
                "In accordance with ISO 19157 standards, status is UNVERIFIED."
            )
            prov_recorded = str(evidence_dict.get("source_product", "INCOMPLETE_EVIDENCE"))
            evidence_summary = evidence_dict
        else:
            status = ValidationStatus.VALIDATED.value
            status_note = (
                f"Empirical validation confirmed against independently authenticated reference evidence: "
                f"{evidence_dict['source_product']} ({evidence_dict['source_uri_or_id']}), "
                f"acquired {evidence_dict['acquisition_date']}, "
                f"method: {evidence_dict['reference_methodology']}, "
                f"checksum: {str(evidence_dict['checksum'])[:16]}..."
            )
            prov_recorded = str(evidence_dict["source_product"])
            evidence_summary = evidence_dict
    else:
        # A string label alone (even "COPERNICUS_EMS_VERIFIED") is NOT verified evidence
        status = ValidationStatus.UNVERIFIED.value
        status_note = (
            "A recognized label or authoritative-sounding identifier alone does not establish independent scientific validation. "
            "Empirical ground-truth validation strictly requires documented evidence: source_product, acquisition_date, "
            "source_uri_or_id, checksum, reference_methodology, and independent_verification_decision. Status is UNVERIFIED."
        )
        prov_recorded = prov_str or "UNVERIFIED_SOURCE"
        evidence_summary = None

    return {
        "validation_status": status,
        "status_explanation": status_note,
        "reference_provenance": prov_recorded,
        "reference_evidence": evidence_summary,
        "alignment_metadata": alignment_info,
        "confusion_matrix_pixels": cm,
        "confusion_matrix_area_km2": cm_area_km2,
        "detection_performance_indicators": metrics,
        "evaluation_standard": "ISO 19157 Geographic Information — Data Quality"
    }


# ---------------------------------------------------------------------------
# VECTOR MULTI-MODAL CROSS-SENSOR COMPARISON
# ---------------------------------------------------------------------------
def compute_vector_cross_sensor_agreement(
    optical_geojson: Union[str, Path, Dict[str, Any]],
    radar_geojson: Union[str, Path, Dict[str, Any]],
    koshi_basin_filter: bool = False,
    is_test_fixture: bool = False
) -> Dict[str, Any]:
    """
    Computes rigorous multi-sensor spatial comparison between Sentinel-2 optical
    and Sentinel-1 SAR radar flood polygons.

    Methodology:
      1. Loads vector features and computes their geographic footprints (bounding boxes).
      2. Informs that bounds are inferred from detected flood polygons, not raw satellite swath footprints.
      3. Determines the common spatial intersection of the inferred footprints.
      4. If scenes are disjoint or non-coextensive, returns status="UNVERIFIED" with reason="NON_COEXTENSIVE_SCENE_COVERAGE".
      5. Explicitly clips each geometry to the common comparison footprint before projection, union, and IoU.
      6. Projects clipped features into metric UTM Zone 45N (EPSG:32645).
      7. Calculates exact geometric optical area, radar area, intersection, union, and IoU.
    """
    if not HAS_SHAPELY:
        raise RuntimeError("Shapely is required for vector cross-sensor geometric evaluation.")

    # Load optical features
    if isinstance(optical_geojson, (str, Path)):
        with open(optical_geojson, "r", encoding="utf-8") as f:
            opt_data = json.load(f)
    else:
        opt_data = optical_geojson

    # Load radar features
    if isinstance(radar_geojson, (str, Path)):
        with open(radar_geojson, "r", encoding="utf-8") as f:
            rad_data = json.load(f)
    else:
        rad_data = radar_geojson

    opt_features = opt_data.get("features", [])
    rad_features = rad_data.get("features", [])

    if koshi_basin_filter:
        rad_features_eval = [
            f for f in rad_features
            if f.get("properties", {}).get("in_koshi_study_basin", True)
        ]
    else:
        rad_features_eval = rad_features

    opt_geoms = [shape(f["geometry"]) for f in opt_features if f.get("geometry")]
    rad_geoms = [shape(f["geometry"]) for f in rad_features_eval if f.get("geometry")]

    if not opt_geoms or not rad_geoms:
        return {
            "comparison_type": "VECTOR_CROSS_SENSOR_AGREEMENT",
            "cross_sensor_status": ValidationStatus.UNVERIFIED.value,
            "reason": "EMPTY_FEATURE_COLLECTION",
            "footprint_type": "INFERRED_FROM_DETECTED_POLYGONS",
            "optical_total_extent_km2": 0.0,
            "radar_total_extent_km2": 0.0,
            "common_footprint_intersection_km2": 0.0,
            "common_footprint_union_km2": 0.0,
            "common_footprint_iou": 0.0,
            "scientific_limitation": "One or both feature collections contain zero valid geometries."
        }

    # Total area reported from properties (or fallback to projected area)
    opt_total_area_km2 = sum(
        f.get("properties", {}).get("area_m2", 0.0) or f.get("properties", {}).get("area_sqm", 0.0)
        for f in opt_features
    ) / 1e6

    rad_total_area_km2 = sum(
        f.get("properties", {}).get("area_sqm", 0.0) or f.get("properties", {}).get("area_m2", 0.0)
        for f in rad_features_eval
    ) / 1e6

    # Determine bounding boxes inferred from detected polygons
    opt_minx = min(g.bounds[0] for g in opt_geoms)
    opt_miny = min(g.bounds[1] for g in opt_geoms)
    opt_maxx = max(g.bounds[2] for g in opt_geoms)
    opt_maxy = max(g.bounds[3] for g in opt_geoms)

    rad_minx = min(g.bounds[0] for g in rad_geoms)
    rad_miny = min(g.bounds[1] for g in rad_geoms)
    rad_maxx = max(g.bounds[2] for g in rad_geoms)
    rad_maxy = max(g.bounds[3] for g in rad_geoms)

    # Compute common bounding box
    com_minx = max(opt_minx, rad_minx)
    com_miny = max(opt_miny, rad_miny)
    com_maxx = min(opt_maxx, rad_maxx)
    com_maxy = min(opt_maxy, rad_maxy)

    is_disjoint = (com_minx >= com_maxx) or (com_miny >= com_maxy)

    footprint_notice = (
        "The comparison footprint is inferred strictly from the bounding envelopes of detected flood polygons. "
        "Verified raw satellite swath acquisition footprints are not bundled in repository assets; "
        "inferred bounds indicate detected feature overlap, not full sensor swath coverage."
    )

    if is_disjoint:
        return {
            "comparison_type": "VECTOR_CROSS_SENSOR_AGREEMENT",
            "cross_sensor_status": ValidationStatus.UNVERIFIED.value,
            "reason": "COMPLETELY_DISJOINT_SCENE_COVERAGE",
            "footprint_type": "INFERRED_FROM_DETECTED_POLYGONS",
            "sensor_coverage_notice": footprint_notice,
            "inferred_optical_envelope": [round(opt_minx, 4), round(opt_miny, 4), round(opt_maxx, 4), round(opt_maxy, 4)],
            "inferred_radar_envelope": [round(rad_minx, 4), round(rad_miny, 4), round(rad_maxx, 4), round(rad_maxy, 4)],
            "common_footprint_bounds": None,
            "optical_total_extent_km2": round(opt_total_area_km2, 3),
            "radar_total_extent_km2": round(rad_total_area_km2, 3),
            "common_footprint_optical_km2": 0.0,
            "common_footprint_radar_km2": 0.0,
            "common_footprint_intersection_km2": 0.0,
            "common_footprint_union_km2": 0.0,
            "common_footprint_iou": 0.0,
            "scientific_limitation": "The optical and radar acquisitions are geographically disjoint; no spatial intersection exists."
        }

    common_bbox_geom = box(com_minx, com_miny, com_maxx, com_maxy)

    # CRITICAL: Explicitly clip each geometry to the common comparison footprint
    # Selecting by intersects alone leaks exterior polygon areas outside the boundary box.
    opt_clipped = []
    for g in opt_geoms:
        if g.intersects(common_bbox_geom):
            clipped = g.intersection(common_bbox_geom)
            if not clipped.is_empty and clipped.area > 0:
                opt_clipped.append(clipped)

    rad_clipped = []
    for g in rad_geoms:
        if g.intersects(common_bbox_geom):
            clipped = g.intersection(common_bbox_geom)
            if not clipped.is_empty and clipped.area > 0:
                rad_clipped.append(clipped)

    if not opt_clipped or not rad_clipped:
        return {
            "comparison_type": "VECTOR_CROSS_SENSOR_AGREEMENT",
            "cross_sensor_status": ValidationStatus.UNVERIFIED.value,
            "reason": "NO_FEATURES_IN_COMMON_FOOTPRINT",
            "footprint_type": "INFERRED_FROM_DETECTED_POLYGONS",
            "sensor_coverage_notice": footprint_notice,
            "inferred_optical_envelope": [round(opt_minx, 4), round(opt_miny, 4), round(opt_maxx, 4), round(opt_maxy, 4)],
            "inferred_radar_envelope": [round(rad_minx, 4), round(rad_miny, 4), round(rad_maxx, 4), round(rad_maxy, 4)],
            "optical_total_extent_km2": round(opt_total_area_km2, 3),
            "radar_total_extent_km2": round(rad_total_area_km2, 3),
            "common_footprint_bounds": [round(com_minx, 4), round(com_miny, 4), round(com_maxx, 4), round(com_maxy, 4)],
            "common_footprint_optical_km2": 0.0,
            "common_footprint_radar_km2": 0.0,
            "common_footprint_intersection_km2": 0.0,
            "common_footprint_union_km2": 0.0,
            "common_footprint_iou": 0.0,
            "scientific_limitation": "While scene bounding envelopes intersect, no detected flood polygons exist within the shared footprint."
        }

    # Project strictly clipped geometries to metric UTM Zone 45N
    opt_common_union = unary_union(opt_clipped)
    rad_common_union = unary_union(rad_clipped)

    opt_utm = transform_geom_to_utm45n(opt_common_union)
    rad_utm = transform_geom_to_utm45n(rad_common_union)

    inter_utm = opt_utm.intersection(rad_utm)

    opt_com_area_km2 = opt_utm.area / 1e6
    rad_com_area_km2 = rad_utm.area / 1e6
    inter_area_km2 = inter_utm.area / 1e6
    union_area_km2 = opt_com_area_km2 + rad_com_area_km2 - inter_area_km2
    common_iou = (inter_area_km2 / union_area_km2) if union_area_km2 > 0 else 0.0

    # Co-extensiveness test: Check what fraction of each scene lies in common footprint
    opt_coverage_ratio = (opt_com_area_km2 / opt_total_area_km2) if opt_total_area_km2 > 0 else 0.0
    rad_coverage_ratio = (rad_com_area_km2 / rad_total_area_km2) if rad_total_area_km2 > 0 else 0.0

    # If < 50% of either acquisition scene lies in common footprint, they are non-coextensive
    is_non_coextensive = (opt_coverage_ratio < 0.50) or (rad_coverage_ratio < 0.50)

    if is_test_fixture:
        status = ValidationStatus.TEST_FIXTURE_VERIFIED.value
        limitation = "Calculated from test fixture vector geometries."
    elif is_non_coextensive:
        status = ValidationStatus.UNVERIFIED.value
        limitation = (
            f"The optical Sentinel-2 scene and Sentinel-1 SAR acquisition share only an incidental border strip "
            f"({round(com_maxx - com_minx, 2)}° lon inferred from detected polygons). Because {round((1.0 - opt_coverage_ratio) * 100, 1)}% of the "
            f"optical flood detection and {round((1.0 - rad_coverage_ratio) * 100, 1)}% of the radar flood detection "
            f"lie outside the shared boundary, cross-sensor agreement across the flood event is UNVERIFIED."
        )
    else:
        status = "VERIFIED_INTER_SENSOR_AGREEMENT"
        limitation = "Acquisitions are spatially co-extensive over the evaluation footprint."

    return {
        "comparison_type": "VECTOR_CROSS_SENSOR_AGREEMENT",
        "cross_sensor_status": status,
        "is_coextensive_coverage": not is_non_coextensive,
        "footprint_type": "INFERRED_FROM_DETECTED_POLYGONS",
        "sensor_coverage_notice": footprint_notice,
        "inferred_optical_envelope": [round(opt_minx, 4), round(opt_miny, 4), round(opt_maxx, 4), round(opt_maxy, 4)],
        "inferred_radar_envelope": [round(rad_minx, 4), round(rad_miny, 4), round(rad_maxx, 4), round(rad_maxy, 4)],
        "common_footprint_bounds": [round(com_minx, 4), round(com_miny, 4), round(com_maxx, 4), round(com_maxy, 4)],
        "optical_total_extent_km2": round(opt_total_area_km2, 3),
        "radar_total_extent_km2": round(rad_total_area_km2, 3),
        "common_footprint_optical_km2": round(opt_com_area_km2, 3),
        "common_footprint_radar_km2": round(rad_com_area_km2, 3),
        "common_footprint_intersection_km2": round(inter_area_km2, 3),
        "common_footprint_union_km2": round(union_area_km2, 3),
        "common_footprint_iou": round(common_iou, 4),
        "optical_common_coverage_ratio": round(opt_coverage_ratio, 4),
        "radar_common_coverage_ratio": round(rad_coverage_ratio, 4),
        "scientific_limitation": limitation
    }


def compute_cross_sensor_agreement(
    optical_extent_km2: float,
    radar_extent_km2: float,
    consensus_core_km2: float,
    common_footprint_km2: Optional[float] = None,
    is_test_fixture: bool = False
) -> Dict[str, Any]:
    """
    Computes summary multi-modal satellite inter-comparison across reported area extents.
    Maintains neutral spatial metric definitions without speculative narratives.
    """
    radar_unique_km2 = max(0.0, round(radar_extent_km2 - consensus_core_km2, 3))
    optical_unique_km2 = max(0.0, round(optical_extent_km2 - consensus_core_km2, 3))
    union_km2 = optical_extent_km2 + radar_extent_km2 - consensus_core_km2

    cross_sensor_iou = (consensus_core_km2 / union_km2) if union_km2 > 0 else 0.0

    return {
        "comparison_type": "CROSS_SENSOR_MULTI_MODAL_SUMMARY",
        "cross_sensor_status": ValidationStatus.TEST_FIXTURE_VERIFIED.value if is_test_fixture else ValidationStatus.UNVERIFIED.value,
        "optical_extent_km2": round(optical_extent_km2, 3),
        "radar_extent_km2": round(radar_extent_km2, 3),
        "consensus_intersection_km2": round(consensus_core_km2, 3),
        "optical_unique_km2": optical_unique_km2,
        "radar_unique_km2": radar_unique_km2,
        "cross_sensor_union_km2": round(union_km2, 3),
        "cross_sensor_jaccard_index": round(cross_sensor_iou, 4),
        "boundary_notice": "Inter-sensor concordance measures multi-satellite spatial agreement, NOT independent ground-truth accuracy."
    }
