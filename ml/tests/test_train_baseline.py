"""Tests for baseline model training, chronological splitting, leakage prevention, and reproducibility."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.src.label_builder import generate_synthetic_koshi_event
from ml.src.train_baseline import (
    DEFAULT_CATEGORICAL_FEATURES,
    DEFAULT_NUMERIC_FEATURES,
    build_preprocessor,
    train_baseline_pipeline,
    train_single_horizon,
)


@pytest.fixture
def synthetic_training_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "synthetic_koshi_test.csv"
    df = generate_synthetic_koshi_event(n_hours=180, random_state=42)
    df.to_csv(csv_path, index=False)
    return csv_path


def test_chronological_train_test_split(synthetic_training_csv: Path, tmp_path: Path):
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"

    report = train_baseline_pipeline(
        data_path=synthetic_training_csv,
        output_dir=models_dir,
        reports_dir=reports_dir,
        model_version="test-split-v1",
    )

    # Train timestamps must be strictly earlier than test timestamps
    train_end = pd.to_datetime(report.train_time_range["end"])
    test_start = pd.to_datetime(report.test_time_range["start"])
    assert train_end < test_start


def test_data_leakage_prevention(synthetic_training_csv: Path):
    df = pd.read_csv(synthetic_training_csv)
    numeric_cols = [c for c in DEFAULT_NUMERIC_FEATURES if c in df.columns]
    categorical_cols = [c for c in DEFAULT_CATEGORICAL_FEATURES if c in df.columns]

    split_idx = int(len(df) * 0.75)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    preprocessor = build_preprocessor(numeric_cols, categorical_cols)

    # Fit strictly on train_df
    preprocessor.fit(train_df[numeric_cols + categorical_cols])

    # Extract scaler mean from fitted transformer
    scaler = preprocessor.named_transformers_["num"].named_steps["scaler"]
    train_means = scaler.mean_

    # Verify that the scaler means match train_df means (ignoring median-imputed values)
    # and DO NOT match the full df or test_df means
    col_idx = numeric_cols.index("river_stage_m")
    expected_train_stage_mean = train_df["river_stage_m"].mean()
    full_stage_mean = df["river_stage_m"].mean()

    assert abs(train_means[col_idx] - expected_train_stage_mean) < 0.1
    # Test that preprocessor was not contaminated with test statistics
    if abs(expected_train_stage_mean - full_stage_mean) > 0.05:
        assert train_means[col_idx] != full_stage_mean


def test_baseline_training_and_dummy_comparison(synthetic_training_csv: Path, tmp_path: Path):
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"

    report = train_baseline_pipeline(
        data_path=synthetic_training_csv,
        output_dir=models_dir,
        reports_dir=reports_dir,
        model_version="test-baseline-v1",
    )

    assert len(report.horizons) == 3
    for h_metric in report.horizons:
        assert h_metric.horizon_hours in [1, 3, 6]
        assert h_metric.model_macro_f1 >= 0.0
        assert h_metric.dummy_macro_f1 >= 0.0
        assert len(h_metric.confusion_matrix) == 4
        # Serialized model file exists
        model_file = models_dir / f"baseline_rf_plus_{h_metric.horizon_hours}h_test-baseline-v1.joblib"
        assert model_file.exists()


def test_reproducibility(synthetic_training_csv: Path, tmp_path: Path):
    # Two runs with identical seed and data must yield identical metrics
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"

    rep1 = train_baseline_pipeline(
        data_path=synthetic_training_csv,
        output_dir=dir1 / "models",
        reports_dir=dir1 / "reports",
        model_version="v1",
    )
    rep2 = train_baseline_pipeline(
        data_path=synthetic_training_csv,
        output_dir=dir2 / "models",
        reports_dir=dir2 / "reports",
        model_version="v1",
    )

    for h1, h2 in zip(rep1.horizons, rep2.horizons):
        assert h1.model_macro_f1 == h2.model_macro_f1
        assert h1.confusion_matrix == h2.confusion_matrix


def test_synthetic_disclaimer_flag(synthetic_training_csv: Path, tmp_path: Path):
    report = train_baseline_pipeline(
        data_path=synthetic_training_csv,
        output_dir=tmp_path / "models",
        reports_dir=tmp_path / "reports",
        model_version="v1",
    )
    assert report.is_synthetic_data is True
    assert "PIPELINE TEST ONLY" in report.disclaimer
