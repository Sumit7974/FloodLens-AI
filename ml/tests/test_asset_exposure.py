"""Unit and integration tests for asset exposure join pipeline."""
import json
import pytest
from pathlib import Path

from ml.src.asset_exposure import (
    AssetRecord,
    MatchedAssetExposure,
    AssetExposureSummary,
    generate_koshi_terai_sample_assets,
    join_risk_with_assets,
    load_asset_inventory,
)


@pytest.fixture
def sample_risk_forecast() -> dict:
    return {
        "forecast_id": "fc_test_001",
        "location_id": "loc_barahachhetra_w2",
        "issued_at": "2026-10-19T12:00:00Z",
        "mode": "historical_demo",
        "model_version": "era5-v1",
        "data_quality": "FULL",
        "horizons": [
            {"hours": 1, "risk_level": "moderate", "calibrated_probability": 0.55},
            {"hours": 3, "risk_level": "high", "calibrated_probability": 0.82},
            {"hours": 6, "risk_level": "critical", "calibrated_probability": 0.94},
        ],
    }


@pytest.fixture
def sample_location_zones() -> dict:
    return {
        "loc_barahachhetra_w2": {
            "type": "Polygon",
            "coordinates": [
                [
                    [87.12, 26.82],
                    [87.18, 26.82],
                    [87.18, 26.88],
                    [87.12, 26.88],
                    [87.12, 26.82],
                ]
            ],
        },
        "loc_safe_sunsari_dharan": {
            "type": "Polygon",
            "coordinates": [
                [
                    [87.25, 26.80],
                    [87.30, 26.80],
                    [87.30, 26.85],
                    [87.25, 26.85],
                    [87.25, 26.80],
                ]
            ],
        },
    }


def test_load_sample_assets_integrity():
    assets = generate_koshi_terai_sample_assets()
    assert len(assets) == 6
    asset_types = {a.asset_type for a in assets}
    assert "health_post" in asset_types
    assert "school" in asset_types
    assert "bridge" in asset_types
    assert "road" in asset_types
    assert "farmland" in asset_types


def test_load_asset_inventory_geojson(tmp_path: Path):
    geojson_path = tmp_path / "test_assets.geojson"
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ast_01",
                "properties": {"name": "Test Hospital", "asset_type": "hospital", "location_id": "loc_1"},
                "geometry": {"type": "Point", "coordinates": [87.15, 26.85]},
            },
            {
                "type": "Feature",
                "id": "ast_02",
                "properties": {"name": "Test School", "asset_type": "school"},
                "geometry": {"type": "Point", "coordinates": [87.16, 26.86]},
            },
        ],
    }
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    loaded = load_asset_inventory(geojson_path)
    assert len(loaded) == 2
    assert loaded[0].asset_id == "ast_01"
    assert loaded[0].asset_type == "hospital"
    assert loaded[0].coordinates == (87.15, 26.85)


def test_duplicate_asset_ids_handled_without_duplication(tmp_path: Path):
    geojson_path = tmp_path / "dup_assets.geojson"
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "ast_duplicate",
                "properties": {"name": "First Entry", "asset_type": "school"},
                "geometry": {"type": "Point", "coordinates": [87.15, 26.85]},
            },
            {
                "type": "Feature",
                "id": "ast_duplicate",
                "properties": {"name": "Second Entry (Duplicate)", "asset_type": "school"},
                "geometry": {"type": "Point", "coordinates": [87.15, 26.85]},
            },
        ],
    }
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    loaded = load_asset_inventory(geojson_path)
    assert len(loaded) == 1, "Duplicate asset IDs must be deduplicated."


def test_spatial_join_with_risk_zones(sample_risk_forecast, sample_location_zones):
    assets = generate_koshi_terai_sample_assets()
    matched, summary = join_risk_with_assets(
        assets=assets,
        risk_predictions=sample_risk_forecast,
        location_geometries=sample_location_zones,
        horizon_hours=3,
    )

    assert len(matched) == len(assets)
    # Assets inside Barahachhetra Ward 2 must be matched to high risk
    chatara_health = next(m for m in matched if m.asset_id == "ast_chatara_health_post_01")
    assert chatara_health.location_id == "loc_barahachhetra_w2"
    assert chatara_health.risk_category == "high"
    assert chatara_health.predicted_risk_score == 0.82
    assert chatara_health.exposure_status == "potential_risk_exposure"

    # Confirmed damage must be None: risk exposure != confirmed damage
    assert chatara_health.confirmed_damage is None


def test_location_key_fallback_when_geometry_absent(sample_risk_forecast):
    asset_no_geom = [
        AssetRecord(
            asset_id="ast_no_geom_01",
            asset_type="school",
            name="Rural School without GPS",
            location_id="loc_barahachhetra_w2",
            coordinates=None,
            geometry=None,
        )
    ]

    matched, summary = join_risk_with_assets(
        assets=asset_no_geom,
        risk_predictions=sample_risk_forecast,
        location_geometries=None,
        horizon_hours=3,
    )

    assert len(matched) == 1
    assert matched[0].location_id == "loc_barahachhetra_w2"
    assert matched[0].risk_category == "high"
    assert matched[0].exposure_status == "potential_risk_exposure"
    assert any("Matched via location identifier key" in n for n in matched[0].notes)


def test_unmatched_asset_outside_any_zone(sample_risk_forecast, sample_location_zones):
    far_away_asset = [
        AssetRecord(
            asset_id="ast_far_away",
            asset_type="building",
            name="Far Mountain Hut",
            location_id=None,
            coordinates=(84.00, 28.50),  # Far in Western Himalayas
            geometry={"type": "Point", "coordinates": [84.00, 28.50]},
        )
    ]

    matched, summary = join_risk_with_assets(
        assets=far_away_asset,
        risk_predictions=sample_risk_forecast,
        location_geometries=sample_location_zones,
        horizon_hours=3,
    )

    assert len(matched) == 1
    assert matched[0].exposure_status == "unmatched"
    assert matched[0].risk_category == "unknown"
    assert matched[0].predicted_risk_score is None
    assert summary.unmatched_assets_count == 1


def test_no_double_counting_in_overlapping_zones(sample_risk_forecast):
    # Two overlapping zones
    overlapping_zones = {
        "loc_zone_a": {
            "type": "Polygon",
            "coordinates": [[[87.10, 26.80], [87.20, 26.80], [87.20, 26.90], [87.10, 26.90], [87.10, 26.80]]],
        },
        "loc_zone_b": {
            "type": "Polygon",
            "coordinates": [[[87.15, 26.85], [87.25, 26.85], [87.25, 26.95], [87.15, 26.95], [87.15, 26.85]]],
        },
    }
    two_preds = [
        {
            "location_id": "loc_zone_a",
            "horizons": [{"hours": 1, "risk_level": "moderate", "calibrated_probability": 0.4}],
        },
        {
            "location_id": "loc_zone_b",
            "horizons": [{"hours": 1, "risk_level": "critical", "calibrated_probability": 0.9}],
        },
    ]

    single_asset = [
        AssetRecord(
            asset_id="ast_in_overlap",
            asset_type="hospital",
            name="Hospital in Overlap Zone",
            coordinates=(87.17, 26.87),  # inside both zone A and zone B
        )
    ]

    matched, summary = join_risk_with_assets(
        assets=single_asset,
        risk_predictions=two_preds,
        location_geometries=overlapping_zones,
        horizon_hours=1,
    )

    # Must be matched exactly once, assigned to the higher severity zone (zone_b: critical)
    assert len(matched) == 1
    assert matched[0].location_id == "loc_zone_b"
    assert matched[0].risk_category == "critical"
    assert summary.total_assets_evaluated == 1
    assert summary.total_assets_exposed == 1


def test_summary_infrastructure_metrics_calculation(sample_risk_forecast, sample_location_zones):
    assets = generate_koshi_terai_sample_assets()
    _, summary = join_risk_with_assets(
        assets=assets,
        risk_predictions=sample_risk_forecast,
        location_geometries=sample_location_zones,
        horizon_hours=3,
    )

    assert summary.total_assets_evaluated == 6
    assert summary.total_assets_exposed >= 4
    assert summary.by_risk_category["high"] >= 4
    # Check infrastructure metrics
    assert summary.infrastructure_metrics["roads_exposed_km"] > 0.0
    assert summary.infrastructure_metrics["farmland_exposed_ha"] > 0.0
    assert summary.infrastructure_metrics["critical_facilities_exposed_count"] >= 2
