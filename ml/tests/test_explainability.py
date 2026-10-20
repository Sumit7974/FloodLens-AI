"""Unit and integration tests for explainable AI (XAI) risk engine.

Verifies:
  - Global feature importance calculation (tree MDI normalization, ranking).
  - Local prediction explanation generation with physical benchmarks.
  - Dynamic, evidence-backed narrative generation (no hardcoded text).
  - Handling of missing input features and unobserved variables.
  - Integration with FloodRiskPredictor inference pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.src.explainability import (
    FeatureContribution,
    FloodRiskExplainer,
    GlobalFeatureImportance,
    LocalRiskExplanation,
    export_explainability_summary,
)
from ml.src.predict import FloodRiskPredictor


def test_explainer_initialization_and_global_importance():
    """Verify loading model artifact and computing normalized global feature importance."""
    explainer = FloodRiskExplainer(model_version="era5-v1")
    assert explainer.models is not None
    assert len(explainer.models) > 0
    assert explainer.metadata is not None

    global_imp_1h = explainer.compute_global_feature_importance(horizon_hours=1)
    assert isinstance(global_imp_1h, GlobalFeatureImportance)
    assert global_imp_1h.horizon_hours == 1
    assert "Mean Decrease in Impurity" in global_imp_1h.method

    # Verify importances sum to approximately 1.0
    total_imp = sum(global_imp_1h.feature_importances.values())
    assert pytest.approx(total_imp, rel=1e-2) == 1.0

    # Top drivers should include discharge, saturation, or rainfall
    top_features = global_imp_1h.top_risk_drivers[:3]
    assert any("discharge" in f or "rainfall" in f or "saturation" in f for f in top_features)


def test_local_explanation_high_risk_scenario():
    """Verify local explanation generates evidence-backed narrative for high-risk inputs."""
    explainer = FloodRiskExplainer(model_version="era5-v1")

    high_features = {
        "rainfall_mm": 22.0,
        "rainfall_rolling_3h_mm": 55.0,
        "rainfall_rolling_6h_mm": 90.0,
        "rainfall_rolling_24h_mm": 160.0,  # exceeds 150mm extreme threshold
        "river_stage_m": 7.2,              # exceeds 7.0m danger threshold
        "river_stage_rate_of_rise_m_per_h": 0.40,
        "upstream_discharge_m3s": 9500.0,
        "season": "monsoon",
        "catchment_saturation_class": "saturated",
    }

    explanation = explainer.explain_prediction(
        features=high_features,
        predicted_risk_level="high",
        calibrated_probability=0.91,
        horizon_hours=3,
        location_id="loc_chatara_bridge",
    )

    assert isinstance(explanation, LocalRiskExplanation)
    assert explanation.predicted_risk_level == "high"
    assert explanation.horizon_hours == 3
    assert "Risk classified as HIGH" in explanation.explanation_narrative
    assert "contributing evidence:" in explanation.explanation_narrative.lower()

    # Verify factors identify extreme rainfall and river stage
    assert len(explanation.contributing_factors) > 0
    top_contrib_labels = [c.display_label.lower() for c in explanation.contributing_factors]
    assert any("rainfall" in lbl or "stage" in lbl or "discharge" in lbl for lbl in top_contrib_labels)


def test_local_explanation_low_risk_scenario():
    """Verify local explanation for low-risk inputs with mitigating factors."""
    explainer = FloodRiskExplainer(model_version="era5-v1")

    low_features = {
        "rainfall_mm": 0.5,
        "rainfall_rolling_3h_mm": 1.2,
        "rainfall_rolling_6h_mm": 2.5,
        "rainfall_rolling_24h_mm": 8.0,
        "river_stage_m": 3.8,
        "river_stage_rate_of_rise_m_per_h": 0.01,
        "upstream_discharge_m3s": 950.0,
        "season": "monsoon",
        "catchment_saturation_class": "dry",
    }

    explanation = explainer.explain_prediction(
        features=low_features,
        predicted_risk_level="low",
        calibrated_probability=0.04,
        horizon_hours=1,
        location_id="loc_barahachhetra",
    )

    assert explanation.predicted_risk_level == "low"
    assert "Risk classified as LOW" in explanation.explanation_narrative
    assert len(explanation.mitigating_factors) > 0


def test_local_explanation_missing_features_transparency():
    """Verify that missing input features are transparently tracked."""
    explainer = FloodRiskExplainer(model_version="era5-v1")

    sparse_features = {
        "rainfall_mm": 15.0,
        # omitted rainfall rolling, river stage, discharge
    }

    explanation = explainer.explain_prediction(
        features=sparse_features,
        predicted_risk_level="moderate",
        calibrated_probability=0.52,
        horizon_hours=1,
    )

    assert len(explanation.missing_inputs) > 0
    assert "unavailable" in explanation.explanation_narrative.lower()


def test_export_explainability_summary(tmp_path: Path):
    """Verify export of explainability summary JSON."""
    out_file = tmp_path / "test_explainability_summary.json"
    summary = export_explainability_summary(output_path=out_file)

    assert out_file.exists()
    assert "global_importance" in summary
    assert "sample_local_explanations" in summary
    assert "+1h" in summary["global_importance"]
    assert "+3h" in summary["global_importance"]


def test_predict_pipeline_with_explanations():
    """Verify FloodRiskPredictor integration with include_explanations=True."""
    predictor = FloodRiskPredictor(model_version="era5-v1")

    test_input = {
        "location_id": "loc_test_w2",
        "timestamp": "2024-08-15T12:00:00Z",
        "rainfall_mm": 25.0,
        "rainfall_rolling_3h_mm": 60.0,
        "rainfall_rolling_6h_mm": 110.0,
        "rainfall_rolling_24h_mm": 175.0,
        "river_stage_m": 7.5,
        "river_stage_rate_of_rise_m_per_h": 0.45,
        "upstream_discharge_m3s": 8500.0,
        "season": "monsoon",
        "catchment_saturation_class": "saturated",
    }

    # Standard call (backward compatible: no explanations)
    res_standard = predictor.predict(test_input, include_explanations=False)
    assert "explanations" not in res_standard
    assert "horizons" in res_standard

    # Enhanced call (Day 3 feature: with explanations)
    res_explained = predictor.predict(test_input, include_explanations=True)
    assert "explanations" in res_explained
    assert "+1h" in res_explained["explanations"]
    assert "+3h" in res_explained["explanations"]
    assert "explanation_narrative" in res_explained["explanations"]["+1h"]
