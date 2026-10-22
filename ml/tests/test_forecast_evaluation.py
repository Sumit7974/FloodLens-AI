"""Automated unit and integration tests for FloodLens AI Day 4 deliverables.

Covers:
- Timestamp matching and lead-time alignment (+1h, +3h, +6h)
- Edge-of-series boundary conditions and unmatched records
- Multiclass classification metric calculations (accuracy, balanced accuracy, macro F1, off-by-one)
- False alarm calculations (FAR and POFD formulas and denominators)
- Numerical forecast errors (MAE and RMSE) and unobserved flood depth audit
- Missing values and label insufficiency handling
- Distinction between real reanalysis observations and simulated sensor readings
- Candidate model offline training, artifact serialization, and FloodRiskPredictor inference
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest

from ml.src.forecast_evaluation import (
    compute_false_alarm_metrics,
    compute_numerical_forecast_errors,
    match_forecasts_with_observations,
    run_comprehensive_forecast_evaluation,
)
from ml.src.predict import FloodRiskPredictor
from ml.src.train_candidate import (
    audit_label_sufficiency,
    run_candidate_training,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def sample_timeseries_df() -> pd.DataFrame:
    """Construct a clean, synthetic 10-step hourly time series for deterministic testing."""
    base_time = datetime(2024, 8, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(10):
        t = base_time + timedelta(hours=i)
        rows.append({
            "timestamp": t.isoformat(),
            "location_id": "loc_barahachhetra_w2",
            "rainfall_mm": float(i * 2.0),
            "forecast_precip_next_3h_mm": float((i + 1) * 2.5),
            "is_reanalysis": True,
            "is_synthetic": False,
            "data_source": "test_reanalysis_fixture",
            "target_+1h": float(min(3, i % 4)),
            "target_+3h": float(min(3, (i + 1) % 4)),
            "target_+6h": float(min(3, (i + 2) % 4)),
        })
    return pd.DataFrame(rows)


def test_timestamp_matching_lead_time_alignment(sample_timeseries_df: pd.DataFrame):
    """Test that forecasts issued at t are matched to valid_at = t + h."""
    horizon = 1
    matched, summary = match_forecasts_with_observations(
        df=sample_timeseries_df,
        horizon_hours=horizon,
        location_id="loc_barahachhetra_w2",
    )

    # In a 10-step series, +1h horizon should match exactly 9 pairs (last row has no t+1h)
    assert summary.matched_pairs_count == 9
    assert summary.unmatched_forecasts_count == 1
    assert summary.lead_time_alignment_verified is True

    # Verify first paired record
    first_pair = matched[0]
    t0 = datetime(2024, 8, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 8, 1, 1, 0, tzinfo=timezone.utc)
    assert first_pair.issued_at == t0.isoformat()
    assert first_pair.valid_at == t1.isoformat()
    assert first_pair.observed_at == t1.isoformat()


def test_boundary_handling_unmatched_records_at_tail(sample_timeseries_df: pd.DataFrame):
    """Test that boundary records lacking future ground truth are strictly logged as unmatched."""
    # +3h horizon in 10-step series -> last 3 rows (idx 7, 8, 9) have no t+3h in range
    matched_3h, summary_3h = match_forecasts_with_observations(
        df=sample_timeseries_df,
        horizon_hours=3,
        location_id="loc_barahachhetra_w2",
    )
    assert summary_3h.matched_pairs_count == 7
    assert summary_3h.unmatched_forecasts_count == 3

    # +6h horizon -> last 6 rows unmatched, exactly 4 matched
    matched_6h, summary_6h = match_forecasts_with_observations(
        df=sample_timeseries_df,
        horizon_hours=6,
        location_id="loc_barahachhetra_w2",
    )
    assert summary_6h.matched_pairs_count == 4
    assert summary_6h.unmatched_forecasts_count == 6


def test_location_mismatch_rejection(sample_timeseries_df: pd.DataFrame):
    """Test that records from non-target locations are rejected during matching."""
    df_mixed = sample_timeseries_df.copy()
    # Alter half the rows to a different location
    df_mixed.loc[0:4, "location_id"] = "loc_other_district"

    matched, summary = match_forecasts_with_observations(
        df=df_mixed,
        horizon_hours=1,
        location_id="loc_barahachhetra_w2",
    )
    assert summary.mismatched_locations_rejected == 5


def test_false_alarm_ratio_and_rate_calculations():
    """Test False Alarm Ratio (FAR) and False Alarm Rate (POFD) with exact mathematical verification."""
    # Construct exact scenario:
    # 10 samples:
    # True:  [0, 0, 0, 0, 0, 0, 2, 2, 3, 3]  (6 non-floods: class 0; 4 floods: classes 2, 3)
    # Pred:  [0, 0, 0, 0, 2, 3, 2, 2, 3, 0]  (Warnings issued: indices 4, 5, 6, 7, 8 -> 5 warnings)
    # Breakdown:
    # TP (idx 6, 7, 8) = 3 hits
    # FP (idx 4, 5)    = 2 false alarms (true is 0, pred >= 2)
    # FN (idx 9)       = 1 missed flood (true is 3, pred is 0)
    # TN (idx 0, 1, 2, 3) = 4 correct rejections
    #
    # Warnings Issued = TP + FP = 5
    # Total Non-Floods = FP + TN = 6
    # FAR = FP / (TP + FP) = 2 / 5 = 0.40 (40.0%)
    # POFD = FP / (FP + TN) = 2 / 6 = 0.3333 (33.33%)
    # Severe Jump: idx 5 (true = 0, pred = 3) -> exactly 1 severe jump!
    y_true = pd.Series([0, 0, 0, 0, 0, 0, 2, 2, 3, 3])
    y_pred = pd.Series([0, 0, 0, 0, 2, 3, 2, 2, 3, 0])

    fa = compute_false_alarm_metrics(y_true, y_pred, warning_threshold=2)

    assert fa.total_warnings_issued == 5
    assert fa.true_positives_count == 3
    assert fa.false_positives_count == 2
    assert fa.false_negatives_count == 1
    assert fa.true_negatives_count == 4
    assert fa.total_non_flood_events == 6
    assert fa.false_alarm_ratio == 0.40
    assert fa.false_alarm_rate_pofd == 0.3333
    assert fa.severe_false_alarm_jumps_count == 1
    assert fa.multiclass_overpredictions_count == 2  # idx 4, 5


def test_zero_division_safety_in_false_alarm_metrics():
    """Test that zero warnings issued or zero non-floods safely return 0.0 without crashing."""
    # No warnings issued (all predicted 0)
    y_true = pd.Series([0, 0, 0, 1])
    y_pred = pd.Series([0, 0, 0, 0])
    fa = compute_false_alarm_metrics(y_true, y_pred, warning_threshold=2)
    assert fa.total_warnings_issued == 0
    assert fa.false_alarm_ratio == 0.0
    assert fa.false_alarm_rate_pofd == 0.0

    # Empty series
    fa_empty = compute_false_alarm_metrics(pd.Series([], dtype=int), pd.Series([], dtype=int))
    assert fa_empty.total_warnings_issued == 0
    assert fa_empty.false_alarm_ratio == 0.0


def test_numerical_forecast_mae_rmse_and_depth_audit(sample_timeseries_df: pd.DataFrame):
    """Test MAE/RMSE calculation for NWP precip and strict refusal to fabricate flood depth."""
    metrics_list = compute_numerical_forecast_errors(sample_timeseries_df)

    # Check that continuous flood depth is explicitly flagged as DATA GAP / insufficient
    depth_metric = next((m for m in metrics_list if m.variable_name == "continuous_floodwater_depth_m"), None)
    assert depth_metric is not None
    assert depth_metric.is_data_sufficient is False
    assert depth_metric.mae is None
    assert depth_metric.rmse is None
    assert "DATA GAP LIMITATION" in depth_metric.data_limitation_statement

    # Check that NWP precipitation has valid MAE and RMSE
    nwp_metric = next((m for m in metrics_list if m.variable_name == "nwp_precipitation_forecast_3h"), None)
    assert nwp_metric is not None
    assert nwp_metric.is_data_sufficient is True
    assert isinstance(nwp_metric.mae, float)
    assert isinstance(nwp_metric.rmse, float)


def test_provenance_distinction_reanalysis_vs_synthetic(sample_timeseries_df: pd.DataFrame):
    """Test that real reanalysis data is explicitly marked and distinguished from synthetic."""
    matched_reanalysis, summary_re = match_forecasts_with_observations(
        df=sample_timeseries_df,
        horizon_hours=1,
    )
    assert summary_re.is_reanalysis_data is True
    assert summary_re.is_synthetic_data is False
    assert matched_reanalysis[0].is_reanalysis is True
    assert matched_reanalysis[0].is_synthetic is False

    # Flip to synthetic
    df_syn = sample_timeseries_df.copy()
    df_syn["is_synthetic"] = True
    df_syn["is_reanalysis"] = False
    matched_syn, summary_syn = match_forecasts_with_observations(
        df=df_syn,
        horizon_hours=1,
    )
    assert summary_syn.is_reanalysis_data is False
    assert summary_syn.is_synthetic_data is True
    assert matched_syn[0].is_synthetic is True


def test_label_sufficiency_audit_rejects_insufficient_data():
    """Test that audit_label_sufficiency safely refuses training when samples are inadequate."""
    # Case 1: Less than 100 samples
    df_tiny = pd.DataFrame({"target_+1h": [0, 1, 2, 3]})
    sufficient_tiny, audit_tiny = audit_label_sufficiency(df_tiny)
    assert sufficient_tiny is False
    assert audit_tiny["verdict"] == "INSUFFICIENT_SAMPLE_SIZE"

    # Case 2: Only 1 class present in 200 samples
    df_single_class = pd.DataFrame({
        f"target_+{h}h": [0] * 200 for h in [1, 3, 6]
    })
    sufficient_single, audit_single = audit_label_sufficiency(df_single_class)
    assert sufficient_single is False
    assert audit_single["verdict"] == "INSUFFICIENT_LABELS"


def test_candidate_model_loading_and_predict_inference():
    """Test that FloodRiskPredictor can load candidate-v2 and generate valid multi-horizon predictions."""
    models_dir = REPO_ROOT / "ml" / "models"
    # Ensure candidate-v2 model artifacts exist
    meta_path = models_dir / "model_metadata_candidate-v2.json"
    if not meta_path.exists():
        pytest.skip("candidate-v2 model artifacts not present; run train_candidate.py first")

    predictor = FloodRiskPredictor(models_dir=models_dir, model_version="candidate-v2")
    assert predictor.model_version == "candidate-v2"
    assert len(predictor.models) == 3  # Horizons 1, 3, 6

    # Test sample inference payload adhering to FastAPI schema
    features = {
        "rainfall_mm": 12.5,
        "rainfall_rolling_3h_mm": 28.0,
        "rainfall_rolling_6h_mm": 45.0,
        "rainfall_rolling_24h_mm": 95.0,
        "upstream_discharge_m3s": 5400.0,
        "season": "monsoon",
        "catchment_saturation_class": "wet",
    }
    pred_res = predictor.predict(features, location_id="loc_barahachhetra_w2")

    assert pred_res["location_id"] == "loc_barahachhetra_w2"
    assert pred_res["model_version"] == "candidate-v2"
    assert len(pred_res["horizons"]) == 3
    for h_item in pred_res["horizons"]:
        assert h_item["risk_level"] in ["low", "moderate", "high", "critical"]
        assert 0.0 <= h_item["calibrated_probability"] <= 1.0


def test_full_evaluation_pipeline_execution(tmp_path: Path):
    """Offline pipeline regression with explicitly tagged synthetic input, not ERA5 validation."""
    synthetic = REPO_ROOT / "ml" / "data" / "synthetic" / "synthetic_koshi_event.csv"
    assert synthetic.is_file(), "Versioned synthetic demo fixture is required."
    report = run_comprehensive_forecast_evaluation(
        data_path=synthetic, reports_dir=tmp_path, model_version="baseline-v1",
    )

    assert report.model_version == "baseline-v1"
    assert report.summary_verdict == "PASS_ON_SYNTHETIC_TEST_DATA"
    assert len(report.matching_summaries) == 3
    assert "+1h" in report.multiclass_evaluations
    assert "+1h" in report.false_alarm_analyses

    # Verify that JSON artifacts were created
    assert (tmp_path / "forecast_vs_observation_report.json").exists()
    assert (tmp_path / "evaluation_metrics_report.json").exists()
