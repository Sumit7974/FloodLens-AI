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
10. Authoritative-looking string alone cannot produce VALIDATED (Returns UNVERIFIED)
11. Documented evidence with all required audit fields produces VALIDATED
12. Synthetic test fixtures never qualify as empirical ground-truth validation (Returns TEST_FIXTURE_VERIFIED)
13. Pixel area derivation directly from raster georeferencing affine transform
14. Vector cross-sensor evaluation with polygons crossing the comparison boundary (Strict clipping verification)
15. Vector cross-sensor geometric overlap on real repository layers (Strictly clipped figures, UNVERIFIED status)
16. Vector cross-sensor geometric overlap on co-extensive test fixture
17. Vector cross-sensor geometric overlap on completely disjoint geometries
18. Invalid input masks (Empty arrays, mismatched dimensions)
19. Integration with day5_validation_report.compute_detection_metrics()
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

    p_data = np.zeros((1, 10, 10), dtype=np.uint8)
    p_data[0, :3, :3] = 1   # 9 flood pixels in top-left
    p_data[0, 7:, 7:] = 1   # 9 flood pixels in bottom-right (outside reference coverage!)
    p_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)

    with rasterio.open(
        pred_tif, "w", driver="GTiff", height=10, width=10, count=1,
        dtype=np.uint8, crs="EPSG:32645", transform=p_transform, nodata=255
    ) as dst:
        dst.write(p_data)

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
    assert cm["total_evaluated"] == 25
    assert cm["nodata_excluded"] == 75
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

    p_data = np.ones((1, 10, 10), dtype=np.uint8)
    p_transform = from_origin(500000.0, 2900100.0, 10.0, 10.0)
    with rasterio.open(pred_tif, "w", driver="GTiff", height=10, width=10, count=1, dtype=np.uint8, crs="EPSG:32645", transform=p_transform, nodata=255) as d:
        d.write(p_data)

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


def test_authoritative_string_alone_rejected_as_unverified(tmp_path):
    """Test 10: An authoritative string label alone (e.g. COPERNICUS_EMS_VERIFIED) does NOT qualify for VALIDATED."""
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

    # Calling with recognized label string alone without evidence dictionary
    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_provenance="COPERNICUS_EMS_VERIFIED",
        is_test_fixture=False
    )
    assert report["validation_status"] == ValidationStatus.UNVERIFIED.value
    assert report["validation_status"] != ValidationStatus.VALIDATED.value
    assert "A recognized label or authoritative-sounding identifier alone does not establish" in report["status_explanation"]


def test_documented_evidence_validates_detection(tmp_path):
    """Test 11: Documented reference evidence with all required audit fields produces VALIDATED status."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_doc.tif"
    ref_tif = tmp_path / "ref_doc.tif"
    data = np.zeros((1, 5, 5), dtype=np.uint8)
    data[0, :2, :2] = 1
    tr = from_origin(500000.0, 2900050.0, 10.0, 10.0)

    with rasterio.open(pred_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)

    # Complete authenticated reference evidence
    evidence = {
        "source_product": "EMSR224_01BIRATNAGAR_DEL_v1",
        "acquisition_date": "2017-08-13T04:50:00Z",
        "source_uri_or_id": "https://emergency.copernicus.eu/mapping/list-of-activations-rapid/EMSR224",
        "checksum": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "reference_methodology": "in_situ_aerial_orthophoto_and_gauge_delineation",
        "independent_verification_decision": True
    }

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        reference_evidence=evidence,
        is_test_fixture=False
    )
    assert report["validation_status"] == ValidationStatus.VALIDATED.value
    assert "EMSR224_01BIRATNAGAR_DEL_v1" in report["status_explanation"]
    assert report["reference_evidence"]["checksum"] == evidence["checksum"]


def test_synthetic_fixture_never_claims_empirical_validation(tmp_path):
    """Test 12: Synthetic test fixtures return TEST_FIXTURE_VERIFIED and never qualify as VALIDATED."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_fix.tif"
    ref_tif = tmp_path / "ref_fix.tif"
    data = np.zeros((1, 5, 5), dtype=np.uint8)
    tr = from_origin(500000.0, 2900050.0, 10.0, 10.0)

    with rasterio.open(pred_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)
    with rasterio.open(ref_tif, "w", driver="GTiff", height=5, width=5, count=1, dtype=np.uint8, crs="EPSG:32645", transform=tr) as d:
        d.write(data)

    report = evaluate_flood_detection_accuracy(
        pred_mask=pred_tif,
        ref_mask=ref_tif,
        is_test_fixture=True
    )
    assert report["validation_status"] == ValidationStatus.TEST_FIXTURE_VERIFIED.value
    assert report["validation_status"] != ValidationStatus.VALIDATED.value
    assert "never qualifies as empirical ground-truth validation" in report["status_explanation"]


def test_raster_pixel_area_derived_from_georeferencing(tmp_path):
    """Test 13: Pixel area is derived from raster georeferencing transform, not a fixed 10m assumption."""
    if not HAS_RASTERIO:
        pytest.skip("rasterio not installed")

    pred_tif = tmp_path / "pred_20m.tif"
    ref_tif = tmp_path / "ref_20m.tif"
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
    assert report["confusion_matrix_area_km2"]["true_positive_km2"] == 0.0016


def test_vector_cross_sensor_polygon_crossing_boundary_is_strictly_clipped():
    """Test 14: Polygons crossing the comparison boundary are strictly clipped to the comparison footprint."""
    # Optical polygon extends from lon 87.0 to 87.2 (width 0.2 deg)
    opt_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[87.0, 26.0], [87.2, 26.0], [87.2, 26.1], [87.0, 26.1], [87.0, 26.0]]]
                },
                "properties": {"area_m2": 220000000.0}
            }
        ]
    }

    # Radar polygon extends from lon 87.05 to 87.1 (width 0.05 deg)
    # The common comparison box is strictly [87.05, 26.0] to [87.1, 26.1] (width 0.05 deg)
    rad_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[87.05, 26.0], [87.1, 26.0], [87.1, 26.1], [87.05, 26.1], [87.05, 26.0]]]
                },
                "properties": {"area_sqm": 55000000.0}
            }
        ]
    }

    agreement = compute_vector_cross_sensor_agreement(
        optical_geojson=opt_geojson,
        radar_geojson=rad_geojson,
        is_test_fixture=True
    )

    # In the common footprint [87.05, 87.1], optical is strictly clipped to [87.05, 87.1]
    # Because radar covers the identical clipped region, intersection == union -> IoU == 1.0!
    # If optical had NOT been clipped, optical area would be 4x radar area and IoU would be ~0.25.
    assert agreement["common_footprint_bounds"] == [87.05, 26.0, 87.1, 26.1]
    assert agreement["common_footprint_optical_km2"] == pytest.approx(agreement["common_footprint_radar_km2"], rel=1e-2)
    assert agreement["common_footprint_iou"] == pytest.approx(1.0, abs=1e-3)


def test_vector_cross_sensor_geometric_overlap_on_real_layers():
    """Test 15: Vector cross-sensor evaluation on repository GeoJSONs computes strictly clipped figures and returns UNVERIFIED."""
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
    assert agreement["footprint_type"] == "INFERRED_FROM_DETECTED_POLYGONS"
    assert "inferred bounds indicate detected feature overlap" in agreement["sensor_coverage_notice"]
    # Full scene optical: ~48.01 km2
    assert agreement["optical_total_extent_km2"] == pytest.approx(48.006, abs=1e-2)
    # Strictly clipped common footprint numbers
    assert agreement["common_footprint_bounds"] is not None
    assert agreement["common_footprint_optical_km2"] == pytest.approx(7.038, abs=0.05)
    assert agreement["common_footprint_radar_km2"] == pytest.approx(45.881, abs=0.1)
    assert agreement["common_footprint_intersection_km2"] == pytest.approx(0.252, abs=0.05)
    assert agreement["common_footprint_union_km2"] == pytest.approx(52.667, abs=0.1)
    assert agreement["common_footprint_iou"] == pytest.approx(0.0048, abs=1e-4)
    assert "incidental border strip" in agreement["scientific_limitation"]


def test_vector_cross_sensor_coextensive_test_fixture():
    """Test 16: Synthetic co-extensive vector layers in test fixture produce TEST_FIXTURE_VERIFIED and valid IoU."""
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
    assert agreement["common_footprint_iou"] == pytest.approx(1.0, abs=1e-3)


def test_vector_cross_sensor_disjoint_geometries():
    """Test 17: Completely disjoint vector layers return UNVERIFIED with COMPLETELY_DISJOINT_SCENE_COVERAGE."""
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
    """Test 18: Error handling for invalid shapes and empty arrays."""
    with pytest.raises(ValueError, match="zero pixels"):
        calculate_confusion_matrix(np.array([]), np.array([]))

    with pytest.raises(ValueError, match="Shape mismatch"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((4, 4)))

    with pytest.raises(ValueError, match="valid_mask shape"):
        calculate_confusion_matrix(np.zeros((3, 3)), np.zeros((3, 3)), valid_mask=np.zeros((4, 4)))


def test_day5_validation_report_integration(tmp_path):
    """Test 19: Integration with day5_validation_report.compute_detection_metrics()."""
    res_no_ref = compute_detection_metrics()
    assert res_no_ref["validation_status"] == ValidationStatus.NOT_VALIDATED.value
    assert res_no_ref["confusion_matrix_pixels"] is None
    assert "cross_sensor_agreement" in res_no_ref
    cs = res_no_ref["cross_sensor_agreement"]
    assert cs["cross_sensor_status"] == ValidationStatus.UNVERIFIED.value
    assert cs["common_footprint_iou"] == pytest.approx(0.0048, abs=1e-4)
    assert cs["footprint_type"] == "INFERRED_FROM_DETECTED_POLYGONS"
