"""
test_gis_detection_metrics.py
=============================
Regression and unit tests for scientific GIS flood detection accuracy validation.

Tests:
1. Perfect mask agreement (Precision=1.0, Recall=1.0, F1=1.0, IoU=1.0, Kappa=1.0)
2. Partial mask overlap (Exact hand-calculated confusion matrix and metrics)
3. No mask overlap (TP=0, IoU=0, Precision=0, Recall=0, F1=0, Kappa <= 0)
4. NoData pixel exclusion (255, -9999, NaN, masked arrays excluded from denominator)
5. Missing reference mask handling (Returns NOT_VALIDATED, avoids fabricated metrics)
6. Circular validation rejection (Refuses to evaluate prediction against itself)
7. Different raster CRS and resolution alignment with nearest-neighbor resampling
8. Incomplete spatial overlap (Uncovered regions outside reference coverage excluded as NoData, NOT counted as dry land)
9. Completely disjoint raster coverage (100% excluded as NoData, 0 evaluated pixels)
10. Unsupported reference provenance handling (Returns UNVERIFIED; does not assign VALIDATED without authoritative standard)
11. Authoritative reference provenance validation (Returns VALIDATED for recognized standards)
12. Pixel area derivation directly from raster georeferencing affine transform
13. Vector cross-sensor geometric overlap on non-coextensive real layers (Returns UNVERIFIED with exact geometric figures)
14. Vector cross-sensor geometric overlap on co-extensive test fixture
15. Vector cross-sensor geometric overlap on completely disjoint geometries
16. Invalid input masks (Empty arrays, mismatched dimensions)
17. Integration with day5_validation_report.compute_detection_metrics()
"""

from pathlib import Path
import numpy as np
import pytest

from ml.gis_processing.detection_metrics import (
    calculate_confusion_matrix,
    derive_binary_metrics,
    evaluate_flood_detection_accuracy,
    compute_cross_sensor_agreement,
    compute_vector_cross_sensor_agreement,
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
    assert metrics["iou_jaccard_index"] == pytest.approx(0.3333, abs=1e-3)
    assert metrics["overall_accuracy"] == 0.75
    assert metrics["commission_error_rate"] == 0.50
    assert metrics["omission_error_rate"] == 0.50
    # Kappa: p_obs=0.75, p_chance=((4*4)+(12*12))/256 = (16+144)/256 = 160/256 = 0.625
    # kappa = (0.75 - 0.625) / (1 - 0.625) = 0.125 / 0.375 = 0.3333
    assert metrics["cohens_kappa"] == pytest.approx(0.3333, abs=1e-3)


def test_confusion_matrix_no_overlap():
    """Test 3: Completely disjoint predictions yield zero TP and zero IoU."""
    pred = np.zeros((5, 5), dtype=np.int32)
    ref = np.zeros((5, 5), dtype=np.int32)

    pred[:2, :] = 1  # 10 flooded pixels
    ref[3:, :] = 1   # 10 flooded pixels in different rows

    cm = calculate_confusion_matrix(pred, ref)
    assert cm["tp_pixels"] == 0
    assert cm["fp_pixels"] == 10
    assert cm["fn_pixels"] == 10
    assert cm["tn_pixels"] == 5

    metrics = derive_binary_metrics(cm["tp_pixels"], cm["fp_pixels"], cm["tn_pixels"], cm["fn_pixels"])
    assert metrics["precision_user_accuracy"] == 0.0
    assert metrics["recall_producer_accuracy"] == 0.0
    assert metrics["f1_score_dice_coefficient"] == 0.0
    assert metrics["iou_jaccard_index"] == 0.0
    assert metrics["commission_error_rate"] == 1.0
    assert metrics["omission_error_rate"] == 1.0
    assert metrics["cohens_kappa"] < 0.0


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
    assert report["confusion_matrix_area_km2"] is None
    assert report["detection_performance_indicators"] is None
    assert "Independent authoritative reference flood mask" in report["missing_evidence"][0]


def test_circular_validation_rejected(tmp_path):
    """Test 6: Comparing a model against its own prediction output is rejected."""
    mask_file = tmp_path / "self_predicted_mask.tif"
    mask_file.write_text("dummy", encoding="utf-8")

    report = evaluate_flood_detection_accuracy(pred_mask=mask_file, ref_mask=mask_file)
    assert report["validation_status"] == ValidationStatus.CIRCULAR_REFERENCE_REJECTED.value
    assert "Circular validation rejected" in report["summary"]
    assert report["confusion_matrix_pixels"] is None


def test_different_raster_crs_and_resolutions(tmp_path):
    """Test 7: Spatial alignment across differing CRS and resolutions using nearest-neighbor."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_utm.tif"
    ref_tif = tmp_path / "ref_wgs84.tif"

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

    r_data = np.zeros((1, 5, 5), dtype=np.uint8)
    r_data[0, :3, :3] = 1
    r_transform = from_origin(86.9995, 26.221, 0.0002, 0.0002)

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
        reference_provenance="TEST_MULTI_CRS_DATASET",
        is_test_fixture=True
    )

    assert report["validation_status"] == ValidationStatus.TEST_FIXTURE_VERIFIED.value
    assert report["alignment_metadata"]["resampling_method"] == "nearest_neighbor"
    assert report["alignment_metadata"]["resampled"] is True
    assert report["confusion_matrix_pixels"]["total_evaluated"] > 0
    assert report["detection_performance_indicators"]["overall_accuracy"] is not None


def test_incomplete_spatial_overlap_nodata_exclusion(tmp_path):
    """Test 8: Uncovered areas outside reference coverage are excluded as NoData, NOT counted as dry land."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_full.tif"
    ref_tif = tmp_path / "ref_partial.tif"

    # Prediction raster: 10x10 grid (100 pixels total) at origin (500000, 2900100)
    # Has flood pixels at top-left (0,0) and bottom-right (8,8)
    p_data = np.zeros((1, 10, 10), dtype=np.uint8)
    p_data[0, :3, :3] = 1   # 9 flood pixels in top-left
    p_data[0, 7:, 7:] = 1   # 9 flood pixels in bottom-right (outside reference coverage!)
    p_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)

    with rasterio.open(
        pred_tif, "w", driver="GTiff", height=10, width=10, count=1,
        dtype=np.uint8, crs="EPSG:32645", transform=p_transform, nodata=255
    ) as dst:
        dst.write(p_data)

    # Reference raster: only 5x5 grid (25 pixels), covering ONLY the top-left quadrant of prediction
    # Extent: Easting 500000 to 500050, Northing 2900050 to 2900100
    r_data = np.zeros((1, 5, 5), dtype=np.uint8)
    r_data[0, :3, :3] = 1   # Matches top-left 9 pixels
    r_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)

    with rasterio.open(
        ref_tif, "w", driver="GTiff", height=5, width=5, count=1,
        dtype=np.uint8, crs="EPSG:32645", transform=r_transform, nodata=255
    ) as dst:
        dst.write(r_data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="TEST_PARTIAL_OVERLAP",
        is_test_fixture=True
    )

    cm = report["confusion_matrix_pixels"]
    # Total evaluated pixels MUST be exactly 25 (the reference footprint)!
    # The remaining 75 pixels outside reference coverage MUST be excluded as NoData.
    assert cm["total_evaluated"] == 25
    assert cm["nodata_excluded"] == 75
    # The 9 flood pixels in bottom-right MUST NOT be counted as False Positives against unmapped reference!
    assert cm["tp_pixels"] == 9
    assert cm["fp_pixels"] == 0
    assert cm["fn_pixels"] == 0
    assert cm["tn_pixels"] == 16


def test_completely_disjoint_raster_coverage(tmp_path):
    """Test 9: Completely disjoint raster footprints result in 100% NoData exclusion and 0 evaluated pixels."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_scene_a.tif"
    ref_tif = tmp_path / "ref_scene_b.tif"

    # Prediction at UTM 500000, 2900000
    p_data = np.ones((1, 10, 10), dtype=np.uint8)
    p_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)
    with rasterio.open(pred_tif, "w", driver="GTiff", height=10, width=10, count=1, dtype=np.uint8, crs="EPSG:32645", transform=p_transform, nodata=255) as d:
        d.write(p_data)

    # Reference at UTM 700000, 3100000 (200 km away!)
    r_data = np.ones((1, 10, 10), dtype=np.uint8)
    r_transform = from_origin(700000.0, 3100100.0, 10.0, 10.0)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=10, width=10, count=1, dtype=np.uint8, crs="EPSG:32645", transform=r_transform, nodata=255) as d:
        d.write(r_data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="TEST_DISJOINT",
        is_test_fixture=True
    )

    cm = report["confusion_matrix_pixels"]
    assert cm["total_evaluated"] == 0
    assert cm["nodata_excluded"] == 100
    assert cm["tp_pixels"] == 0
    assert cm["fp_pixels"] == 0
    assert cm["fn_pixels"] == 0
    assert cm["tn_pixels"] == 0


def test_unsupported_reference_provenance(tmp_path):
    """Test 10: Reference mask with unverified provenance returns UNVERIFIED, not scientific VALIDATED."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred.tif"
    ref_tif = tmp_path / "ref.tif"
    data = np.zeros((1, 5, 5), dtype=np.uint8)
    tr = from_origin(500000.0, 2900050.0, 10.0, 10.0)

    with rasterio.open(pred_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)

    # Passing user-supplied string without authoritative credential
    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="user_downloaded_flood_map",
        is_test_fixture=False
    )
    assert report["validation_status"] == ValidationStatus.UNVERIFIED.value
    assert "lacks independent, documented third-party verification" in report["status_explanation"]


def test_authoritative_reference_provenance_validation(tmp_path):
    """Test 11: Authoritative third-party reference provenance assigns VALIDATED status."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_auth.tif"
    ref_tif = tmp_path / "ref_auth.tif"
    data = np.zeros((1, 5, 5), dtype=np.uint8)
    data[0, :2, :2] = 1
    tr = from_origin(500000.0, 2900050.0, 10.0, 10.0)

    with rasterio.open(pred_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="COPERNICUS_EMS_VERIFIED",
        is_test_fixture=False
    )
    assert report["validation_status"] == ValidationStatus.VALIDATED.value
    assert "COPERNICUS_EMS_VERIFIED" in report["status_explanation"]


def test_raster_pixel_area_derived_from_georeferencing(tmp_path):
    """Test 12: Pixel area is derived from raster georeferencing transform, not a fixed 10m assumption."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_20m.tif"
    ref_tif = tmp_path / "ref_20m.tif"
    # 20m x 20m pixel resolution
    tr = from_origin(500000.0, 2900100.0, 20.0, 20.0)
    data = np.zeros((1, 5, 5), dtype=np.uint8)
    data[0, :2, :2] = 1  # 4 flooded pixels

    with rasterio.open(pred_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="TEST_PIXEL_AREA",
        is_test_fixture=True
    )

    meta = report["alignment_metadata"]
    assert meta["pixel_width_m"] == 20.0
    assert meta["pixel_height_m"] == 20.0
    assert meta["pixel_area_m2"] == 400.0
    assert meta["pixel_area_source"] == "projected_raster_affine_transform"

    # 4 pixels * 400 m2 = 1,600 m2 = 0.0016 km2
    assert report["confusion_matrix_area_km2"]["true_positive_km2"] == 0.0016


def test_vector_cross_sensor_geometric_overlap_on_real_layers():
    """Test 13: Vector cross-sensor evaluation on repository GeoJSONs computes real figures and returns UNVERIFIED."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    opt_path = repo_root / "flood_polygons.geojson"
    rad_path = repo_root / "radar_flood_polygons.geojson"

    if not opt_path.exists() or not rad_path.exists():
        pytest.skip("Repository GeoJSON layers not found on local path.")

    agreement = compute_vector_cross_sensor_agreement(
        optical_geojson=opt_path,
        radar_geojson=rad_path,
        koshi_basin_filter=False
    )

    assert agreement["comparison_type"] == "VECTOR_CROSS_SENSOR_AGREEMENT"
    assert agreement["cross_sensor_status"] == ValidationStatus.UNVERIFIED.value
    # Full scene optical: ~48.01 km2
    assert agreement["optical_total_extent_km2"] == pytest.approx(48.006, abs=1e-2)
    # Common footprint is narrow strip [87.45, 26.13, 87.61, 26.66]
    assert agreement["common_footprint_bounds"] is not None
    assert agreement["common_footprint_optical_km2"] == pytest.approx(7.071, abs=0.1)
    assert agreement["common_footprint_radar_km2"] == pytest.approx(49.401, abs=0.1)
    assert agreement["common_footprint_intersection_km2"] == pytest.approx(0.252, abs=0.05)
    assert agreement["common_footprint_iou"] == pytest.approx(0.0045, abs=1e-3)
    assert "narrow border strip" in agreement["scientific_limitation"]


def test_vector_cross_sensor_coextensive_test_fixture():
    """Test 14: Synthetic co-extensive vector layers in test fixture produce TEST_FIXTURE_VERIFIED and valid IoU."""
    # Synthetic optical: two 0.1 deg squares in WGS84
    opt_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[87.0, 26.0], [87.1, 26.0], [87.1, 26.1], [87.0, 26.1], [87.0, 26.0]]]
                },
                "properties": {"area_m2": 110780000.0}
            }
        ]
    }

    # Synthetic radar: overlapping 0.1 deg square shifted by 0.05 deg
    rad_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[87.05, 26.0], [87.15, 26.0], [87.15, 26.1], [87.05, 26.1], [87.05, 26.0]]]
                },
                "properties": {"area_sqm": 110780000.0}
            }
        ]
    }

    agreement = compute_vector_cross_sensor_agreement(
        optical_geojson=opt_geojson,
        radar_geojson=rad_geojson,
        is_test_fixture=True
    )

    assert agreement["cross_sensor_status"] == ValidationStatus.TEST_FIXTURE_VERIFIED.value
    assert agreement["common_footprint_intersection_km2"] > 0.0
    # Overlap is half the polygon (~50% intersection)
    assert agreement["common_footprint_iou"] == pytest.approx(0.3333, abs=0.05)


def test_vector_cross_sensor_disjoint_geometries():
    """Test 15: Completely disjoint vector layers return UNVERIFIED with COMPLETELY_DISJOINT_SCENE_COVERAGE."""
    opt_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[85.0, 25.0], [85.1, 25.0], [85.1, 25.1], [85.0, 25.1], [85.0, 25.0]]]},
                "properties": {"area_m2": 100000.0}
            }
        ]
    }
    rad_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[88.0, 27.0], [88.1, 27.0], [88.1, 27.1], [88.0, 27.1], [88.0, 27.0]]]},
                "properties": {"area_sqm": 100000.0}
            }
        ]
    }

    agreement = compute_vector_cross_sensor_agreement(
        optical_geojson=opt_geojson,
        radar_geojson=rad_geojson,
        is_test_fixture=False
    )
    assert agreement["cross_sensor_status"] == ValidationStatus.UNVERIFIED.value
    assert agreement["reason"] == "COMPLETELY_DISJOINT_SCENE_COVERAGE"
    assert agreement["common_footprint_intersection_km2"] == 0.0
    assert agreement["common_footprint_iou"] == 0.0


def test_invalid_input_masks():
    """Test 16: Error handling for invalid shapes and empty arrays."""
    with pytest.raises(ValueError, match="zero pixels"):
        calculate_confusion_matrix(np.array([]), np.array([]))

    with pytest.raises(ValueError, match="Shape mismatch"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((4, 4)))

    with pytest.raises(ValueError, match="valid_mask shape"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((3, 3)), valid_mask=np.zeros((4, 4)))


def test_day5_validation_report_integration(tmp_path):
    """Test 17: Integration with day5_validation_report.compute_detection_metrics()."""
    res_no_ref = compute_detection_metrics()
    assert res_no_ref["validation_status"] == ValidationStatus.NOT_VALIDATED.value
    assert res_no_ref["confusion_matrix_pixels"] is None
    assert "cross_sensor_agreement" in res_no_ref
    # Status of cross-sensor comparison on real repo layers is UNVERIFIED due to non-coextensive swaths
    cs = res_no_ref["cross_sensor_agreement"]
    assert cs["cross_sensor_status"] == ValidationStatus.UNVERIFIED.value
    assert cs["common_footprint_iou"] == pytest.approx(0.0045, abs=1e-3)
