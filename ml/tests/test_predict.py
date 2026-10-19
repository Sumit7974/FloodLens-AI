"""Tests for prediction interface, schema contract validation, and missing feed safety."""
from pathlib import Path
import pytest

from ml.src.label_builder import generate_synthetic_koshi_event
from ml.src.predict import FloodRiskPredictor
from ml.src.train_baseline import train_baseline_pipeline


@pytest.fixture(scope="module")
def trained_predictor(tmp_path_factory) -> FloodRiskPredictor:
    tmp_p = tmp_path_factory.mktemp("pred_test")
    data_csv = tmp_p / "synthetic_koshi.csv"
    df = generate_synthetic_koshi_event(n_hours=150, random_state=42)
    df.to_csv(data_csv, index=False)

    train_baseline_pipeline(
        data_path=data_csv,
        output_dir=tmp_p / "models",
        reports_dir=tmp_p / "reports",
        model_version="pred-test-v1",
    )
    return FloodRiskPredictor(models_dir=tmp_p / "models", model_version="pred-test-v1")


def test_prediction_output_schema_contract(trained_predictor: FloodRiskPredictor):
    sample_features = {
        "rainfall_mm": 35.0,
        "rainfall_rolling_3h_mm": 80.0,
        "rainfall_rolling_6h_mm": 120.0,
        "rainfall_rolling_24h_mm": 175.0,
        "river_stage_m": 7.2,
        "river_stage_rate_of_rise_m_per_h": 0.45,
        "upstream_discharge_m3s": 9500.0,
        "forecast_precip_next_3h_mm": 40.0,
        "temperature_c": 23.0,
        "relative_humidity_pct": 98.0,
        "season": "monsoon",
        "catchment_saturation_class": "saturated",
    }

    result = trained_predictor.predict(
        features=sample_features,
        location_id="loc_barahachhetra_w2",
        event_id="evt_nepal_terai_koshi",
    )

    # Check required fields matching backend contract
    assert "forecast_id" in result
    assert result["location_id"] == "loc_barahachhetra_w2"
    assert result["event_id"] == "evt_nepal_terai_koshi"
    assert "issued_at" in result
    assert result["mode"] == "historical_demo"
    assert result["model_version"] == "pred-test-v1"
    assert result["data_quality"] in ["FULL", "PARTIAL", "DEGRADED", "UNAVAILABLE"]
    assert isinstance(result["horizons"], list)
    assert len(result["horizons"]) == 3

    for h_item in result["horizons"]:
        assert h_item["hours"] in [1, 3, 6]
        assert h_item["risk_level"] in ["low", "moderate", "high", "critical", "unknown"]
        assert h_item["calibrated_probability"] is None or (0.0 <= h_item["calibrated_probability"] <= 1.0)


def test_missing_critical_feeds_prevents_false_low_risk(trained_predictor: FloodRiskPredictor):
    # Completely empty feature dictionary (simulating offline gauge and no telemetry)
    empty_features = {}

    result = trained_predictor.predict(features=empty_features)

    # Must NOT emit a false low-risk result!
    assert result["data_quality"] == "UNAVAILABLE"
    for h in result["horizons"]:
        assert h["risk_level"] != "low", "System must never emit false low-risk when essential inputs are missing!"
        assert h["risk_level"] == "unknown"

    assert any("critical hydrological feeds missing" in lim for lim in result["limitations"])


def test_partial_feed_handling_and_limitation_records(trained_predictor: FloodRiskPredictor):
    # Partial features: river stage present, but rolling rainfall missing
    partial_features = {
        "river_stage_m": 6.8,
        "rainfall_mm": 12.0,
        # missing rainfall_rolling_24h_mm
    }

    result = trained_predictor.predict(features=partial_features)
    assert result["data_quality"] == "PARTIAL"
    assert any("Critical feeds missing" in lim for lim in result["limitations"])


def test_synthetic_mode_labeling(trained_predictor: FloodRiskPredictor):
    features = {
        "river_stage_m": 4.0,
        "rainfall_mm": 5.0,
        "rainfall_rolling_24h_mm": 20.0,
    }
    result = trained_predictor.predict(features=features)
    assert result["mode"] == "historical_demo"
    assert any("Experimental pipeline test mode" in lim for lim in result["limitations"])


def test_era5_v1_prediction_and_reanalysis_disclaimer():
    """Verify era5-v1 artifact loads and produces contract-compliant predictions with reanalysis disclaimer."""
    models_path = Path("ml/models")
    if not (models_path / "model_metadata_era5-v1.json").exists():
        pytest.skip("era5-v1 artifacts not present")

    predictor = FloodRiskPredictor(models_dir=models_path, model_version="era5-v1")
    features = {
        "rainfall_mm": 20.0,
        "rainfall_rolling_3h_mm": 45.0,
        "rainfall_rolling_6h_mm": 70.0,
        "rainfall_rolling_24h_mm": 120.0,
        "river_stage_m": 5.0,
        "upstream_discharge_m3s": 5000.0,
        "forecast_precip_next_3h_mm": 25.0,
        "temperature_c": 26.0,
        "relative_humidity_pct": 88.0,
        "season": "monsoon",
        "catchment_saturation_class": "saturated",
    }
    result = predictor.predict(features)
    assert result["mode"] == "historical_demo"
    assert result["model_version"] == "era5-v1"
    assert any("RESEARCH PROTOTYPE" in lim for lim in result["limitations"])
    assert len(result["horizons"]) == 3
    for h_item in result["horizons"]:
        assert h_item["risk_level"] in ["low", "moderate", "high", "critical"]
        assert 0.0 <= h_item["calibrated_probability"] <= 1.0


def test_prediction_backend_schema_validation(trained_predictor: FloodRiskPredictor):
    """Verify predictor payload conforms to backend ForecastIngestRequest schema."""
    features = {
        "rainfall_mm": 10.0,
        "rainfall_rolling_3h_mm": 20.0,
        "rainfall_rolling_6h_mm": 35.0,
        "rainfall_rolling_24h_mm": 50.0,
        "river_stage_m": 5.5,
        "upstream_discharge_m3s": 3000.0,
        "forecast_precip_next_3h_mm": 15.0,
        "temperature_c": 25.0,
        "relative_humidity_pct": 85.0,
        "season": "monsoon",
        "catchment_saturation_class": "wet",
    }
    result = trained_predictor.predict(features)
    import sys
    sys.path.insert(0, "backend")
    from app.schemas.forecast import ForecastIngestRequest

    req = ForecastIngestRequest.model_validate(result)
    assert req.location_id == "loc_barahachhetra_w2"
    assert len(req.horizons) == 3
    assert req.mode.value == "historical_demo"

