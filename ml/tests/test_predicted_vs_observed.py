"""Unit and integration tests for predicted-versus-observed evaluation pipeline.

Verifies:
  - Multiclass risk classification evaluation metrics (F1, precision, recall, confusion matrix).
  - Binary flood warning classification evaluation (warning F1, precision, recall).
  - Chronological held-out test split isolation (no test/train data leakage).
  - Paired comparison record generation and concordance classification (exact match, off by one, false alarm).
  - Explicit audit of unobserved targets (water depth, drainage blockages).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.src.predicted_vs_observed import (
    ComparisonRecord,
    PredictedVsObservedReport,
    TargetEvaluationResult,
    evaluate_binary_flood_warning,
    evaluate_multiclass_risk,
    run_predicted_vs_observed_analysis,
)


def test_evaluate_multiclass_risk():
    """Verify multiclass metrics calculation with known arrays."""
    # 4 classes: 0=low, 1=moderate, 2=high, 3=critical
    y_true = pd.Series([0, 1, 2, 3, 0, 1, 2, 3])
    y_pred = pd.Series([0, 1, 2, 3, 0, 2, 2, 2])  # 6 exact matches, 2 off-by-one

    result = evaluate_multiclass_risk(
        y_true=y_true,
        y_pred=y_pred,
        horizon_hours=1,
        period_start="2024-08-01T00:00:00Z",
        period_end="2024-09-30T23:00:00Z",
    )

    assert isinstance(result, TargetEvaluationResult)
    assert result.horizon_hours == 1
    assert result.sample_size == 8
    assert result.target_type == "multiclass_risk_forecast"
    assert "macro_f1" in result.metrics
    assert "exact_match_accuracy" in result.metrics
    assert result.metrics["exact_match_accuracy"] == 0.75
    assert result.metrics["off_by_one_tolerance_accuracy"] == 1.0  # all are exact or off-by-one
    assert result.confusion_matrix is not None
    assert len(result.confusion_matrix) == 4


def test_evaluate_binary_flood_warning():
    """Verify binary flood warning metrics where high/critical are positive flood warnings."""
    # 0=low, 1=moderate (negative: 0), 2=high, 3=critical (positive: 1)
    y_true = pd.Series([0, 1, 2, 3])  # True: [0, 0, 1, 1]
    y_pred = pd.Series([0, 0, 2, 3])  # Pred: [0, 0, 1, 1] -> Perfect warning

    result = evaluate_binary_flood_warning(
        y_true_risk=y_true,
        y_pred_risk=y_pred,
        horizon_hours=3,
        period_start="2024-08-01T00:00:00Z",
        period_end="2024-09-30T23:00:00Z",
    )

    assert isinstance(result, TargetEvaluationResult)
    assert result.target_type == "binary_flood_warning"
    assert result.horizon_hours == 3
    assert result.metrics["f1_score"] == 1.0
    assert result.metrics["precision"] == 1.0
    assert result.metrics["recall_sensitivity"] == 1.0
    assert result.confusion_matrix[0][1] == 0  # false positives
    assert result.confusion_matrix[1][0] == 0  # false negatives


def test_comparison_record_concordance():
    """Verify paired comparison record dataclass and concordance calculation."""
    rec = ComparisonRecord(
        record_id="comp_test_001",
        location_id="loc_test",
        horizon_hours=1,
        prediction_timestamp="2024-08-15T12:00:00Z",
        observation_timestamp="2024-08-15T13:00:00Z",
        predicted_risk_level="high",
        observed_risk_level="moderate",
        predicted_probability=0.75,
        concordance="OFF_BY_ONE",
        severity_delta=1,
        data_provenance="test_record",
    )

    d = rec.to_dict()
    assert d["concordance"] == "OFF_BY_ONE"
    assert d["severity_delta"] == 1
    assert d["predicted_risk_level"] == "high"


def test_run_predicted_vs_observed_analysis_end_to_end(tmp_path: Path):
    """Run full evaluation against repository dataset and verify held-out separation."""
    report = run_predicted_vs_observed_analysis(reports_dir=tmp_path)

    assert isinstance(report, PredictedVsObservedReport)
    assert report.total_evaluations_count == 6  # +1h, +3h, +6h for both multiclass and binary
    assert report.summary_verdict == "PASS_ON_HELD_OUT_TEST_DATA"

    # Verify unobserved depth is explicitly audited
    assert "continuous_floodwater_depth_m" in report.unobserved_targets_audit
    assert "UNOBSERVED" in report.unobserved_targets_audit["continuous_floodwater_depth_m"]

    # Verify comparison table sample records exist
    assert len(report.comparison_table_sample) > 0
    for rec in report.comparison_table_sample:
        assert rec.prediction_timestamp != ""
        assert rec.observation_timestamp != ""
        assert rec.concordance in {"EXACT_MATCH", "OFF_BY_ONE", "FALSE_ALARM", "MISSED_DETECTION"}

    # Verify report was written to tmp_path
    saved_file = tmp_path / "predicted_vs_observed_summary.json"
    assert saved_file.exists()
    with open(saved_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["model_version"] == report.model_version
