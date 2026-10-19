"""Baseline ML model training pipeline for FloodLens AI.

Trains reproducible multi-horizon risk classifiers (+1h, +3h, +6h) on hydrological
time-series using a strict chronological train/test split, leakage-free preprocessing,
and transparent comparison against a DummyClassifier reference baseline.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_NUMERIC_FEATURES = [
    "rainfall_mm",
    "rainfall_rolling_3h_mm",
    "rainfall_rolling_6h_mm",
    "rainfall_rolling_24h_mm",
    "river_stage_m",
    "river_stage_rate_of_rise_m_per_h",
    "upstream_discharge_m3s",
    "forecast_precip_next_3h_mm",
    "temperature_c",
    "relative_humidity_pct",
]

DEFAULT_CATEGORICAL_FEATURES = [
    "season",
    "catchment_saturation_class",
]

RISK_CLASS_NAMES = ["low", "moderate", "high", "critical"]


@dataclass
class HorizonEvaluationMetrics:
    """Evaluation metrics for a specific forecast horizon."""
    horizon_hours: int
    target_name: str
    dummy_macro_f1: float
    dummy_balanced_accuracy: float
    model_macro_f1: float
    model_balanced_accuracy: float
    per_class_metrics: Dict[str, Dict[str, float]]
    confusion_matrix: List[List[int]]
    classes_present_in_test: List[str]
    train_samples_count: int
    test_samples_count: int
    class_distribution_train: Dict[str, int]
    class_distribution_test: Dict[str, int]


@dataclass
class TrainingRunReport:
    """Complete report for a baseline model training execution."""
    run_id: str
    timestamp: str
    data_source: str
    is_synthetic_data: bool
    disclaimer: str
    model_version: str
    model_type: str
    feature_list_numeric: List[str]
    feature_list_categorical: List[str]
    train_ratio: float
    train_time_range: Dict[str, str]
    test_time_range: Dict[str, str]
    is_reanalysis_data: bool = False
    horizons: List[HorizonEvaluationMetrics] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_preprocessor(
    numeric_features: List[str],
    categorical_features: List[str],
) -> ColumnTransformer:
    """Construct a scikit-learn preprocessing pipeline."""
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ],
        remainder="drop",
    )
    return preprocessor


def train_single_horizon(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    numeric_cols: List[str],
    categorical_cols: List[str],
    horizon_hours: int,
    random_state: int = 42,
    n_estimators: int = 100,
    max_depth: int = 6,
) -> Tuple[Pipeline, DummyClassifier, HorizonEvaluationMetrics]:
    """Train and evaluate baseline model for one prediction horizon."""
    # Build complete ML pipeline
    preprocessor = build_preprocessor(numeric_cols, categorical_cols)
    rf_clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        class_weight="balanced",
    )
    model_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", rf_clf),
        ]
    )

    # Reference baseline: DummyClassifier predicting most frequent class / prior
    dummy_clf = DummyClassifier(strategy="prior", random_state=random_state)

    # Fit models strictly on training split
    model_pipeline.fit(X_train, y_train)
    dummy_clf.fit(X_train, y_train)

    # Predictions on test split
    y_pred = model_pipeline.predict(X_test)
    y_dummy_pred = dummy_clf.predict(X_test)

    # Metrics computation
    model_macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    model_bal_acc = float(balanced_accuracy_score(y_test, y_pred))

    dummy_macro_f1 = float(f1_score(y_test, y_dummy_pred, average="macro", zero_division=0))
    dummy_bal_acc = float(balanced_accuracy_score(y_test, y_dummy_pred))

    # Confusion matrix and per-class reports
    # All possible class IDs: [0, 1, 2, 3]
    labels_all = [0, 1, 2, 3]
    cm = confusion_matrix(y_test, y_pred, labels=labels_all).tolist()

    report_dict = classification_report(
        y_test,
        y_pred,
        labels=labels_all,
        target_names=RISK_CLASS_NAMES,
        output_dict=True,
        zero_division=0,
    )

    per_class = {
        cls_name: {
            "precision": float(report_dict[cls_name]["precision"]),
            "recall": float(report_dict[cls_name]["recall"]),
            "f1-score": float(report_dict[cls_name]["f1-score"]),
            "support": int(report_dict[cls_name]["support"]),
        }
        for cls_name in RISK_CLASS_NAMES
        if cls_name in report_dict
    }

    # Distribution counts
    train_dist = {RISK_CLASS_NAMES[int(k)]: int(v) for k, v in y_train.value_counts().to_dict().items() if int(k) < 4}
    test_dist = {RISK_CLASS_NAMES[int(k)]: int(v) for k, v in y_test.value_counts().to_dict().items() if int(k) < 4}
    classes_present = [RISK_CLASS_NAMES[int(c)] for c in sorted(y_test.unique()) if int(c) < 4]

    metrics = HorizonEvaluationMetrics(
        horizon_hours=horizon_hours,
        target_name=f"risk_label_+{horizon_hours}h",
        dummy_macro_f1=round(dummy_macro_f1, 4),
        dummy_balanced_accuracy=round(dummy_bal_acc, 4),
        model_macro_f1=round(model_macro_f1, 4),
        model_balanced_accuracy=round(model_bal_acc, 4),
        per_class_metrics=per_class,
        confusion_matrix=cm,
        classes_present_in_test=classes_present,
        train_samples_count=len(y_train),
        test_samples_count=len(y_test),
        class_distribution_train=train_dist,
        class_distribution_test=test_dist,
    )

    return model_pipeline, dummy_clf, metrics


def train_baseline_pipeline(
    data_path: Path | str,
    output_dir: Path | str = "ml/models",
    reports_dir: Path | str = "ml/reports",
    config_path: Optional[Path | str] = "ml/configs/baseline_config.json",
    model_version: str = "baseline-v1",
) -> TrainingRunReport:
    """Execute complete chronological baseline model training for +1h, +3h, and +6h horizons."""
    data_p = Path(data_path)
    if not data_p.exists():
        raise FileNotFoundError(f"Training data not found at {data_p}")

    df = pd.read_csv(data_p)
    if df.empty:
        raise ValueError(f"Training dataset at {data_p} is empty.")

    # Load config if present
    cfg: Dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    numeric_cols = [c for c in cfg.get("features", {}).get("numeric", DEFAULT_NUMERIC_FEATURES) if c in df.columns]
    categorical_cols = [c for c in cfg.get("features", {}).get("categorical", DEFAULT_CATEGORICAL_FEATURES) if c in df.columns]
    horizons = cfg.get("horizons_hours", [1, 3, 6])
    train_ratio = cfg.get("training", {}).get("train_ratio", 0.75)
    random_state = cfg.get("training", {}).get("random_state", 42)
    n_estimators = cfg.get("training", {}).get("n_estimators", 100)
    max_depth = cfg.get("training", {}).get("max_depth", 6)

    # Check data provenance flags
    is_synthetic = bool(df.get("is_synthetic", pd.Series([False])).iloc[0])
    is_reanalysis = bool(df.get("is_reanalysis", pd.Series([False])).iloc[0])
    if is_synthetic:
        disclaimer = (
            "PIPELINE TEST ONLY: Model trained on synthetic demonstration data. "
            "Metrics reflect software pipeline functionality and code correctness, "
            "NOT real-world operational flood prediction accuracy. Do NOT use for real-world alerts."
        )
    elif is_reanalysis:
        disclaimer = (
            "RESEARCH PROTOTYPE: Model trained on open-access ERA5 reanalysis precipitation "
            "and GloFAS discharge proxy data (Open-Meteo). Not validated against in-situ Nepal DHM gauge "
            "observations (river stage data unavailable). Do NOT use for real-world operational flood warnings."
        )
    else:
        disclaimer = "Trained on verified historical observations."

    # Chronological sort
    timestamp_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], utc=True)
    df = df.sort_values(timestamp_col).reset_index(drop=True)

    # Chronological Train/Test Split (No Random Shuffling)
    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    train_time_range = {
        "start": str(train_df[timestamp_col].min()),
        "end": str(train_df[timestamp_col].max()),
    }
    test_time_range = {
        "start": str(test_df[timestamp_col].min()),
        "end": str(test_df[timestamp_col].max()),
    }

    logger.info(
        f"Chronological split: {len(train_df)} train samples ({train_time_range['start']} to {train_time_range['end']}), "
        f"{len(test_df)} test samples ({test_time_range['start']} to {test_time_range['end']})"
    )

    models_out = Path(output_dir)
    models_out.mkdir(parents=True, exist_ok=True)
    rep_out = Path(reports_dir)
    rep_out.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    report = TrainingRunReport(
        run_id=f"run_{now_utc.strftime('%Y%m%d_%H%M%S')}",
        timestamp=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        data_source=str(data_p),
        is_synthetic_data=is_synthetic,
        is_reanalysis_data=is_reanalysis,
        disclaimer=disclaimer,
        model_version=model_version,
        model_type="RandomForestClassifier",
        feature_list_numeric=numeric_cols,
        feature_list_categorical=categorical_cols,
        train_ratio=train_ratio,
        train_time_range=train_time_range,
        test_time_range=test_time_range,
    )

    # Train for each horizon
    for h in horizons:
        target_candidates = [f"target_+{h}h", f"target_plus_{h}h", f"target_{h}h"]
        target_col = next((c for c in target_candidates if c in df.columns), None)
        if target_col is None:
            logger.warning(f"Target column for horizon +{h}h not found in {list(df.columns)}. Skipping.")
            continue

        # Drop rows where target is NaN (e.g. trailing edge of time-series)
        valid_train = train_df.dropna(subset=[target_col])
        valid_test = test_df.dropna(subset=[target_col])

        if valid_train.empty or valid_test.empty:
            logger.warning(f"Insufficient non-null targets for horizon +{h}h.")
            continue

        X_tr = valid_train[numeric_cols + categorical_cols]
        y_tr = valid_train[target_col].astype(int)

        X_te = valid_test[numeric_cols + categorical_cols]
        y_te = valid_test[target_col].astype(int)

        pipeline, dummy, horizon_metrics = train_single_horizon(
            X_train=X_tr,
            y_train=y_tr,
            X_test=X_te,
            y_test=y_te,
            numeric_cols=numeric_cols,
            categorical_cols=categorical_cols,
            horizon_hours=h,
            random_state=random_state,
            n_estimators=n_estimators,
            max_depth=max_depth,
        )

        report.horizons.append(horizon_metrics)

        # Save fitted model pipeline
        model_filename = f"baseline_rf_plus_{h}h_{model_version}.joblib"
        joblib.dump(pipeline, models_out / model_filename)
        logger.info(
            f"Horizon +{h}h trained: Model Macro-F1 = {horizon_metrics.model_macro_f1:.4f} "
            f"(vs Dummy = {horizon_metrics.dummy_macro_f1:.4f}). Saved to {model_filename}"
        )

    # Save training report & feature list
    report_path = rep_out / f"training_report_{model_version}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)

    metadata_path = models_out / f"model_metadata_{model_version}.json"
    metadata = {
        "model_version": model_version,
        "created_at": report.timestamp,
        "is_synthetic_data": is_synthetic,
        "is_reanalysis_data": is_reanalysis,
        "disclaimer": disclaimer,
        "features": {
            "numeric": numeric_cols,
            "categorical": categorical_cols,
        },
        "horizons_hours": [h.horizon_hours for h in report.horizons],
        "training_samples": len(train_df),
        "test_samples": len(test_df),
        "target_mapping": {0: "low", 1: "moderate", 2: "high", 3: "critical"},
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Training run completed. Metrics report saved to {report_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train baseline flood risk models.")
    parser.add_argument("--data", type=str, default="ml/data/processed/koshi_event_cleaned.csv", help="Cleaned dataset path.")
    parser.add_argument("--output-dir", type=str, default="ml/models", help="Directory to save serialized models.")
    parser.add_argument("--reports-dir", type=str, default="ml/reports", help="Directory to save evaluation reports.")
    parser.add_argument("--config", type=str, default="ml/configs/baseline_config.json", help="Path to config file.")
    parser.add_argument("--model-version", type=str, default="baseline-v1", help="Model version identifier.")
    args = parser.parse_args()

    train_baseline_pipeline(
        data_path=args.data,
        output_dir=args.output_dir,
        reports_dir=args.reports_dir,
        config_path=args.config,
        model_version=args.model_version,
    )


if __name__ == "__main__":
    main()
