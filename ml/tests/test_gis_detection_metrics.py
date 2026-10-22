"""
test_gis_detection_metrics.py
=============================
Regression and unit tests for scientific GIS flood detection accuracy validation.

Tests:
1. Perfect mask agreement (Precision=1.0, Recall=1.0, F1=1.0, IoU=1.0, Kappa=1.0)
2. Partial mask overlap (Exact hand-calculated confusion matrix and metrics)
3. No mask overlap (TP=0, IoU=0, Precision=0, Recall=0, F1=0, Kappa <= 0)
4. NoData pixel exclusion (255, -9999, NaN, masked arrays excluded from denominator)
5. Different raster CRS and resolution alignment with nearest-neighbor resampling
6. Missing reference mask handling (Returns NOT_VALIDATED, avoids fabricated metrics)
7. Circular validation rejection (Refuses to evaluate prediction against itself)
8. Invalid input masks (Empty arrays, mismatched dimensions, invalid shapes)
9. Cross-sensor multi-modal agreement calculation (Optical vs SAR inter-comparison)
10. Integration with day5_validation_report.compute_detection_metrics()
"""

from pathlib import Path
import numpy as np
import pytest

from ml.gis_processing.detection_metrics import (
    calculate_confusion_matrix,
    derive_binary_metrics,
    evaluate_flood_detection_accuracy,
    compute_cross_sensor_agreement,
    ValidationStatus,
)
from ml.gis_processing.day5_validation_report import compute_detection_metrics

# Optional rasterio check
try:
    import rasterio
    from rasterio.transform import from_origin
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False


def test_confusion_matrix_perfect_agreement():
    """Test 1: Identical prediction and reference masks yield 100% agreement."""
    # 10x10 grid with 30 flooded pixels and 70 dry pixels
    grid_shape = (10, 10)
    ref = np.zeros(grid_shape, dtype=np.int32)
    ref[:3, :] = 1  # 30 flooded pixels
    pred = ref.copy()

    cm = calculate_confusion_matrix(pred, ref)
    assert cm["tp_pixels"] == 30
    assert cm["fp_pixels"] == 0
    assert cm["fn_pixels"] == 0
    assert cm["tn_pixels"] == 70
    assert cm["total_evaluated"] == 100
    assert cm["nodata_excluded"] == 0

    metrics = derive_binary_metrics(cm["tp_pixels"], cm["fp_pixels"], cm["tn_pixels"], cm["fn_pixels"])
    assert metrics["precision_user_accuracy"] == 1.0
    assert metrics["recall_producer_accuracy"] == 1.0
    assert metrics["f1_score_dice_coefficient"] == 1.0
    assert metrics["iou_jaccard_index"] == 1.0
    assert metrics["overall_accuracy"] == 1.0
    assert metrics["cohens_kappa"] == 1.0
    assert metrics["commission_error_rate"] == 0.0
    assert metrics["omission_error_rate"] == 0.0


def test_confusion_matrix_partial_overlap():
    """Test 2: Known partial overlap reproduces hand-calculated metrics."""
    # 4x4 grid (16 pixels)
    # pred has flooded pixels at indices [0, 1, 2, 3] (flat)
    # ref has flooded pixels at indices [2, 3, 4, 5] (flat)
    # TP = indices [2, 3] (2 pixels)
    # FP = indices [0, 1] (2 pixels)
    # FN = indices [4, 5] (2 pixels)
    # TN = indices [6..15] (10 pixels)
    pred = np.zeros((4, 4), dtype=np.int32)
    ref = np.zeros((4, 4), dtype=np.int32)

    pred.ravel()[[0, 1, 2, 3]] = 1
    ref.ravel()[[2, 3, 4, 5]] = 1

    cm = calculate_confusion_matrix(pred, ref)
    assert cm["tp_pixels"] == 2
    assert cm["fp_pixels"] == 2
    assert cm["fn_pixels"] == 2
    assert cm["tn_pixels"] == 10
    assert cm["total_evaluated"] == 16

    metrics = derive_binary_metrics(cm["tp_pixels"], cm["fp_pixels"], cm["tn_pixels"], cm["fn_pixels"])
    assert metrics["precision_user_accuracy"] == 0.50
    assert metrics["recall_producer_accuracy"] == 0.50
    assert metrics["f1_score_dice_coefficient"] == 0.50
    # IoU: 2 / (2 + 2 + 2) = 2/6 = 0.3333
    assert metrics["iou_jaccard_index"] == pytest.approx(0.3333, abs=1e-3)
    # OA: (2 + 10) / 16 = 12 / 16 = 0.75
    assert metrics["overall_accuracy"] == 0.75
    assert metrics["commission_error_rate"] == 0.50
    assert metrics["omission_error_rate"] == 0.50
    # Kappa: p_obs=0.75, p_chance=((4*4)+(12*12))/256 = (16+144)/256 = 160/256 = 0.625
    # kappa = (0.75 - 0.625) / (1 - 0.625) = 0.125 / 0.375 = 0.3333
    assert metrics["cohens_kappa"] == pytest.approx(0.3333, abs=1e-3)


def test_confusion_matrix_no_overlap():
    """Test 3: Completely disjoint flood extents yield 0% precision, recall, and IoU."""
    pred = np.zeros((4, 4), dtype=np.int32)
    ref = np.zeros((4, 4), dtype=np.int32)

    # Pred top-left 2x2, Ref bottom-right 2x2
    pred[:2, :2] = 1
    ref[2:, 2:] = 1

    cm = calculate_confusion_matrix(pred, ref)
    assert cm["tp_pixels"] == 0
    assert cm["fp_pixels"] == 4
    assert cm["fn_pixels"] == 4
    assert cm["tn_pixels"] == 8

    metrics = derive_binary_metrics(cm["tp_pixels"], cm["fp_pixels"], cm["tn_pixels"], cm["fn_pixels"])
    assert metrics["precision_user_accuracy"] == 0.0
    assert metrics["recall_producer_accuracy"] == 0.0
    assert metrics["f1_score_dice_coefficient"] == 0.0
    assert metrics["iou_jaccard_index"] == 0.0
    assert metrics["overall_accuracy"] == 0.50
    assert metrics["commission_error_rate"] == 1.0
    assert metrics["omission_error_rate"] == 1.0
    assert metrics["cohens_kappa"] <= 0.0


def test_nodata_exclusion():
    """Test 4: NoData values (255, -9999, NaN) and cloud masks are excluded."""
    pred = np.array([
        [1, 0, 255],
        [0, 1, -9999],
        [np.nan, 0, 1]
    ], dtype=np.float32)

    ref = np.array([
        [1, 0, 0],
        [0, 1, 1],
        [0, 0, 255]
    ], dtype=np.float32)

    # Active valid pixels should exclude:
    # (0, 2) pred=255
    # (1, 2) pred=-9999
    # (2, 0) pred=NaN
    # (2, 2) ref=255
    # Remaining valid pixels: (0,0)->[1,1], (0,1)->[0,0], (1,0)->[0,0], (1,1)->[1,1], (2,1)->[0,0]
    # TP = 2 (0,0 and 1,1)
    # FP = 0
    # FN = 0
    # TN = 3 (0,1; 1,0; 2,1)
    cm = calculate_confusion_matrix(pred, ref)
    assert cm["tp_pixels"] == 2
    assert cm["fp_pixels"] == 0
    assert cm["fn_pixels"] == 0
    assert cm["tn_pixels"] == 3
    assert cm["total_evaluated"] == 5
    assert cm["nodata_excluded"] == 4


def test_missing_reference_mask_returns_not_validated():
    """Test 5: When reference mask is None, status is NOT_VALIDATED without fabricating numbers."""
    pred = np.zeros((10, 10), dtype=np.int32)
    pred[:5, :5] = 1

    report = evaluate_flood_detection_accuracy(pred_mask=pred, ref_mask=None)
    assert report["validation_status"] == ValidationStatus.NOT_VALIDATED.value
    assert report["confusion_matrix_pixels"] is None
    assert report["detection_performance_indicators"] is None
    assert len(report["missing_evidence"]) >= 1
    assert "not available" in report["summary"].lower()


def test_circular_validation_rejected(tmp_path):
    """Test 6: Reject evaluating a prediction raster against itself as reference."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    test_tif = tmp_path / "flood_pred.tif"
    data = np.ones((1, 5, 5), dtype=np.uint8)
    transform = from_origin(87.0, 27.0, 10.0, 10.0)

    with rasterio.open(
        test_tif, "w",
        driver="GTiff",
        height=5, width=5, count=1,
        dtype=np.uint8,
        crs="EPSG:4326",
        transform=transform
    ) as dst:
        dst.write(data)

    report = evaluate_flood_detection_accuracy(pred_mask=test_tif, ref_mask=test_tif)
    assert report["validation_status"] == ValidationStatus.CIRCULAR_REFERENCE_REJECTED.value
    assert report["confusion_matrix_pixels"] is None


def test_different_raster_crs_and_resolutions(tmp_path):
    """Test 7: Spatial alignment across differing CRS and resolutions using nearest-neighbor."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_utm.tif"
    ref_tif = tmp_path / "ref_wgs84.tif"

    # Prediction in UTM 45N (EPSG:32645): 10m pixel size, 10x10 grid
    # Extent: Easting 500000 to 500100, Northing 2900000 to 2900100
    p_data = np.zeros((1, 10, 10), dtype=np.uint8)
    p_data[0, :5, :5] = 1  # 25 flooded pixels
    p_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)

    with rasterio.open(
        pred_tif, "w",
        driver="GTiff",
        height=10, width=10, count=1,
        dtype=np.uint8,
        crs="EPSG:32645",
        transform=p_transform
    ) as dst:
        dst.write(p_data)

    # Reference in WGS 84 (EPSG:4326): approximate corresponding bounding box
    # 5x5 grid with coarser resolution
    r_data = np.zeros((1, 5, 5), dtype=np.uint8)
    r_data[0, :3, :3] = 1
    # 500000, 2900000 in UTM 45N is roughly 86.999 deg lon, 26.220 deg lat
    r_transform = from_origin(86.999, 26.221, 0.0002, 0.0002)

    with rasterio.open(
        ref_tif, "w",
        driver="GTiff",
        height=5, width=5, count=1,
        dtype=np.uint8,
        crs="EPSG:4326",
        transform=r_transform
    ) as dst:
        dst.write(r_data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="TEST_MULTI_CRS_DATASET"
    )

    assert report["validation_status"] == ValidationStatus.VALIDATED.value
    assert report["alignment_metadata"]["resampling_method"] == "nearest_neighbor"
    assert report["alignment_metadata"]["resampled"] is True
    assert report["confusion_matrix_pixels"]["total_evaluated"] > 0
    assert report["detection_performance_indicators"]["overall_accuracy"] is not None


def test_invalid_input_masks():
    """Test 8: Error handling for invalid shapes and empty arrays."""
    # Empty array
    with pytest.raises(ValueError, match="zero pixels"):
        calculate_confusion_matrix(np.array([]), np.array([]))

    # Shape mismatch
    with pytest.raises(ValueError, match="Shape mismatch"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((4, 4)))

    # Valid mask shape mismatch
    with pytest.raises(ValueError, match="valid_mask shape"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((3, 3)), valid_mask=np.zeros((4, 4)))


def test_cross_sensor_agreement_calculation():
    """Test 9: Cross-sensor inter-comparison calculation (Sentinel-2 vs Sentinel-1 SAR)."""
    agreement = compute_cross_sensor_agreement(
        optical_extent_km2=48.01,
        radar_extent_km2=72.35,
        consensus_core_km2=39.84
    )

    assert agreement["comparison_type"] == "CROSS_SENSOR_MULTI_MODAL_AGREEMENT"
    assert "NOT ground-truth validation" in agreement["boundary_notice"]
    assert agreement["optical_sentinel2_extent_km2"] == 48.01
    assert agreement["radar_sentinel1_extent_km2"] == 72.35
    assert agreement["dual_sensor_consensus_core_km2"] == 39.84
    # Radar only: 72.35 - 39.84 = 32.51
    assert agreement["radar_only_cloud_penetrated_km2"] == 32.51
    # Optical only: 48.01 - 39.84 = 8.17
    assert agreement["optical_only_shallow_ponding_km2"] == 8.17
    # Union: 48.01 + 72.35 - 39.84 = 80.52
    # IoU: 39.84 / 80.52 = 0.49478 -> 0.4948
    assert agreement["cross_sensor_jaccard_index"] == pytest.approx(0.4948, abs=1e-3)


def test_day5_validation_report_integration(tmp_path):
    """Test 10: Integration with day5_validation_report.compute_detection_metrics()."""
    # 1. Calling without reference returns NOT_VALIDATED
    res_no_ref = compute_detection_metrics()
    assert res_no_ref["validation_status"] == ValidationStatus.NOT_VALIDATED.value
    assert res_no_ref["confusion_matrix_pixels"] is None
    assert "cross_sensor_agreement" in res_no_ref
    assert res_no_ref["cross_sensor_agreement"]["cross_sensor_jaccard_index"] == pytest.approx(0.4948, abs=1e-3)

    # 2. Calling with a mock reference returns VALIDATED
    if HAS_RASTERIO:
        pred_tif = tmp_path / "mock_pred.tif"
        ref_tif = tmp_path / "mock_ref.tif"
        data = np.zeros((1, 8, 8), dtype=np.uint8)
        data[0, :4, :4] = 1
        transform = from_origin(87.0, 27.0, 10.0, 10.0)

        with rasterio.open(pred_tif, "w", driver="GTiff", height=8, width=8, count=1, dtype=np.uint8, crs="EPSG:4326", transform=transform) as d:
            d.write(data)
        with rasterio.open(ref_tif, "w", driver="GTiff", height=8, width=8, count=1, dtype=np.uint8, crs="EPSG:4326", transform=transform) as d:
            d.write(data)

        res_validated = compute_detection_metrics(
            pred_mask_path=pred_tif,
            ref_mask_path=ref_tif,
            reference_provenance="MOCK_INDEPENDENT_TEST_REFERENCE"
        )
        assert res_validated["validation_status"] == ValidationStatus.VALIDATED.value
        assert res_validated["confusion_matrix_pixels"]["tp_pixels"] == 16
        assert res_validated["detection_performance_indicators"]["precision_user_accuracy"] == 1.0
