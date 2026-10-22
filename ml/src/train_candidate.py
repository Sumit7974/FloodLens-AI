"""Candidate ML model offline training and benchmark pipeline for FloodLens AI.

Task 3 (Day 4):
- Inspects the existing dataset to verify label sufficiency before training.
- Trains candidate models locally (Gradient Boosting Decision Trees, candidate-v2)
  without external API calls or extra dependencies.
- Establishes a baseline (Random Forest baseline-v1 / era5-v1) and reference (DummyClassifier)
  and rigorously compares the candidate against them.
- Uses a strict chronological train/test split (75% / 25%, cutoff 2024-07-31) to prevent leakage.
- Applies consistent preprocessing across training and evaluation.
- Serializes model joblib artifacts and comprehensive evaluation report.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline

from ml.src.train_baseline import (
    DEFAULT_CATEGORICAL_FEATURES,
    DEFAULT_NUMERIC_FEATURES,
    RISK_CLASS_NAMES,
    build_preprocessor,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ModelComparisonMetrics:
    """Benchmark metrics comparing candidate model vs baseline vs dummy reference."""
    horizon_hours: int
    target_name: str
    train_samples_count: int
    test_samples_count: int
    dummy_macro_f1: float
    dummy_balanced_accuracy: float
    baseline_rf_macro_f1: float
    baseline_rf_balanced_accuracy: float
    baseline_rf_exact_accuracy: float
    candidate_gbdt_macro_f1: float
    candidate_gbdt_balanced_accuracy: float
    candidate_gbdt_exact_accuracy: float
    macro_f1_delta_vs_baseline: float
    per_class_candidate_metrics: Dict[str, Dict[str, float]]
    confusion_matrix_candidate: List[List[int]]
    confusion_matrix_baseline: List[List[int]]
    candidate_warning_precision: float
    candidate_warning_recall: float
    candidate_warning_f1: float
    candidate_false_alarm_ratio: float
    candidate_false_alarm_rate_pofd: float


@dataclass
class CandidateTrainingReport:
    """Complete report for candidate model training and benchmark execution."""
    run_id: str
    timestamp: str
    model_version: str
    model_type: str
    data_source: str
    is_reanalysis_data: bool
    is_synthetic_data: bool
    label_sufficiency_status: str
    label_audit: Dict[str, Any]
    train_time_range: Dict[str, str]
    test_time_range: Dict[str, str]
    feature_list_numeric: List[str]
    feature_list_categorical: List[str]
    horizons: List[ModelComparisonMetrics] = field(default_factory=list)
    verdict: str = "CANDIDATE_TRAINED_AND_BENCHMARKED"
    disclaimer: str = (
        "RESEARCH PROTOTYPE: Candidate model trained offline on ERA5/GloFAS proxy data. "
        "Not approved for live automated alert dispatch without authorized human review."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_label_sufficiency(df: pd.DataFrame, horizons: List[int] = [1, 3, 6]) -> Tuple[bool, Dict[str, Any]]:
    """Audit whether existing dataset contains sufficient reliable labels for training."""
    n_rows = len(df)
    audit: Dict[str, Any] = {
        "total_records": n_rows,
        "is_reanalysis": bool(df.get("is_reanalysis", pd.Series([False])).iloc[0]),
        "is_synthetic": bool(df.get("is_synthetic", pd.Series([False])).iloc[0]),
        "horizons_checked": {},
    }

    if n_rows < 100:
        audit["verdict"] = "INSUFFICIENT_SAMPLE_SIZE"
        audit["reason"] = f"Dataset has only {n_rows} rows (< 100 required for training)."
        return False, audit

    all_sufficient = True
    for h in horizons:
        col = f"target_+{h}h"
        if col not in df.columns:
            col = f"target_{h}h"
        if col not in df.columns:
            audit["horizons_checked"][f"+{h}h"] = {"status": "MISSING_COLUMN"}
            all_sufficient = False
            continue

        counts = df[col].value_counts().to_dict()
        n_valid = int(df[col].notna().sum())
        n_classes = len(counts)

        # Require at least 2 distinct classes and at least 50 valid observations
        is_h_sufficient = (n_classes >= 2) and (n_valid >= 100)
        audit["horizons_checked"][f"+{h}h"] = {
            "status": "SUFFICIENT" if is_h_sufficient else "INSUFFICIENT_CLASSES",
            "valid_samples": n_valid,
            "class_distribution": {str(k): int(v) for k, v in counts.items()},
            "num_classes_present": n_classes,
        }
        if not is_h_sufficient:
            all_sufficient = False

    audit["verdict"] = "SUFFICIENT_FOR_TRAINING" if all_sufficient else "INSUFFICIENT_LABELS"
    return all_sufficient, audit


def train_single_candidate_horizon(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    numeric_cols: List[str],
    categorical_cols: List[str],
    horizon_hours: int,
    random_state: int = 42,
    n_estimators_gb: int = 100,
    max_depth_gb: int = 4,
    learning_rate: float = 0.08,
    n_estimators_rf: int = 100,
    max_depth_rf: int = 6,
) -> Tuple[Pipeline, Pipeline, DummyClassifier, ModelComparisonMetrics]:
    """Train candidate GBDT model, baseline RF model, and Dummy reference for one horizon."""
    preprocessor = build_preprocessor(numeric_cols, categorical_cols)

    # Candidate Model: GradientBoostingClassifier
    gb_clf = GradientBoostingClassifier(
        n_estimators=n_estimators_gb,
        max_depth=max_depth_gb,
        learning_rate=learning_rate,
        subsample=0.9,
        random_state=random_state,
    )
    candidate_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", gb_clf),
        ]
    )

    # Baseline Model: RandomForestClassifier (from Day 2 baseline)
    rf_clf = RandomForestClassifier(
        n_estimators=n_estimators_rf,
        max_depth=max_depth_rf,
        random_state=random_state,
        class_weight="balanced",
    )
    baseline_pipeline = Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(numeric_cols, categorical_cols)),
            ("classifier", rf_clf),
        ]
    )

    # Reference baseline: DummyClassifier
    dummy_clf = DummyClassifier(strategy="prior", random_state=random_state)

    # Fit strictly on training split
    candidate_pipeline.fit(X_train, y_train)
    baseline_pipeline.fit(X_train, y_train)
    dummy_clf.fit(X_train, y_train)

    # Predict on test split
    p_cand = candidate_pipeline.predict(X_test)
    p_base = baseline_pipeline.predict(X_test)
    p_dummy = dummy_clf.predict(X_test)

    # Metrics
    cand_f1 = float(f1_score(y_test, p_cand, average="macro", zero_division=0))
    cand_bal = float(balanced_accuracy_score(y_test, p_cand))
    cand_exact = float((y_test == p_cand).sum() / len(y_test))

    base_f1 = float(f1_score(y_test, p_base, average="macro", zero_division=0))
    base_bal = float(balanced_accuracy_score(y_test, p_base))
    base_exact = float((y_test == p_base).sum() / len(y_test))

    dummy_f1 = float(f1_score(y_test, p_dummy, average="macro", zero_division=0))
    dummy_bal = float(balanced_accuracy_score(y_test, p_dummy))

    # Binary warning metrics for candidate (Warning = High / Critical)
    y_test_bin = (y_test >= 2).astype(int)
    p_cand_bin = (p_cand >= 2).astype(int)
    cm_bin = confusion_matrix(y_test_bin, p_cand_bin, labels=[0, 1])
    tn, fp, fn, tp = int(cm_bin[0, 0]), int(cm_bin[0, 1]), int(cm_bin[1, 0]), int(cm_bin[1, 1])

    w_prec = float(precision_score(y_test_bin, p_cand_bin, zero_division=0))
    w_rec = float(recall_score(y_test_bin, p_cand_bin, zero_division=0))
    w_f1 = float(f1_score(y_test_bin, p_cand_bin, zero_division=0))

    far = round(fp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    pofd = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0

    labels_all = [0, 1, 2, 3]
    cm_cand = confusion_matrix(y_test, p_cand, labels=labels_all).tolist()
    cm_base = confusion_matrix(y_test, p_base, labels=labels_all).tolist()

    rep_dict = classification_report(
        y_test, p_cand, labels=labels_all, target_names=RISK_CLASS_NAMES, output_dict=True, zero_division=0
    )

    metrics = ModelComparisonMetrics(
        horizon_hours=horizon_hours,
        target_name=f"target_+{horizon_hours}h",
        train_samples_count=len(y_train),
        test_samples_count=len(y_test),
        dummy_macro_f1=round(dummy_f1, 4),
        dummy_balanced_accuracy=round(dummy_bal, 4),
        baseline_rf_macro_f1=round(base_f1, 4),
        baseline_rf_balanced_accuracy=round(base_bal, 4),
        baseline_rf_exact_accuracy=round(base_exact, 4),
        candidate_gbdt_macro_f1=round(cand_f1, 4),
        candidate_gbdt_balanced_accuracy=round(cand_bal, 4),
        candidate_gbdt_exact_accuracy=round(cand_exact, 4),
        macro_f1_delta_vs_baseline=round(cand_f1 - base_f1, 4),
        per_class_candidate_metrics={
            k: {m: round(float(v), 4) for m, v in vals.items()}
            for k, vals in rep_dict.items() if isinstance(vals, dict)
        },
        confusion_matrix_candidate=cm_cand,
        confusion_matrix_baseline=cm_base,
        candidate_warning_precision=round(w_prec, 4),
        candidate_warning_recall=round(w_rec, 4),
        candidate_warning_f1=round(w_f1, 4),
        candidate_false_alarm_ratio=far,
        candidate_false_alarm_rate_pofd=pofd,
    )

    return candidate_pipeline, baseline_pipeline, dummy_clf, metrics


def run_candidate_training(
    data_path: Optional[Union[str, Path]] = None,
    models_dir: Optional[Union[str, Path]] = None,
    reports_dir: Optional[Union[str, Path]] = None,
    candidate_version: str = "candidate-v2",
    train_ratio: float = 0.75,
    random_state: int = 42,
) -> CandidateTrainingReport:
    """Execute offline candidate model training and benchmarking pipeline."""
    root = _REPO_ROOT
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    dpath = Path(data_path) if data_path else (root / "ml" / "data" / "processed" / "era5_glofas_labeled.csv")
    if not dpath.exists():
        dpath = root / "ml" / "data" / "processed" / "koshi_event_cleaned.csv"
    if not dpath.exists():
        raise FileNotFoundError(f"Dataset not found at {dpath}")

    logger.info(f"Inspecting dataset for label sufficiency: {dpath}")
    df = pd.read_csv(dpath)

    # 1. Inspect label sufficiency
    horizons = [1, 3, 6]
    is_sufficient, label_audit = audit_label_sufficiency(df, horizons=horizons)
    if not is_sufficient:
        logger.warning(
            f"Labels are INSUFFICIENT for candidate model training. "
            f"Reason: {label_audit.get('reason', 'Class imbalance or missing targets')}. "
            f"Aborting training to avoid creating a misleading model."
        )
        return CandidateTrainingReport(
            run_id=f"train_{candidate_version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            timestamp=now_iso,
            model_version=candidate_version,
            model_type="none",
            data_source=dpath.name,
            is_reanalysis_data=label_audit.get("is_reanalysis", False),
            is_synthetic_data=label_audit.get("is_synthetic", False),
            label_sufficiency_status="INSUFFICIENT",
            label_audit=label_audit,
            train_time_range={},
            test_time_range={},
            feature_list_numeric=DEFAULT_NUMERIC_FEATURES,
            feature_list_categorical=DEFAULT_CATEGORICAL_FEATURES,
            horizons=[],
            verdict="TRAINING_DEFERRED_DUE_TO_INSUFFICIENT_LABELS",
            disclaimer="Candidate training aborted because labels do not satisfy sufficiency criteria.",
        )

    logger.info("Labels verified sufficient. Proceeding with chronological train/test split.")

    # 2. Chronological Train / Test Split
    ts_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.sort_values(ts_col).reset_index(drop=True)

    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].copy().reset_index(drop=True)
    test_df = df.iloc[split_idx:].copy().reset_index(drop=True)

    train_range = {"start": str(train_df[ts_col].min()), "end": str(train_df[ts_col].max())}
    test_range = {"start": str(test_df[ts_col].min()), "end": str(test_df[ts_col].max())}
    logger.info(f"Train split: {len(train_df)} samples ({train_range['start']} to {train_range['end']})")
    logger.info(f"Test split:  {len(test_df)} samples ({test_range['start']} to {test_range['end']})")

    # Available feature columns
    num_cols = [c for c in DEFAULT_NUMERIC_FEATURES if c in df.columns]
    cat_cols = [c for c in DEFAULT_CATEGORICAL_FEATURES if c in df.columns]
    all_feature_cols = num_cols + cat_cols

    X_train_full = train_df[all_feature_cols]
    X_test_full = test_df[all_feature_cols]

    target_results: List[ModelComparisonMetrics] = []
    trained_pipelines: Dict[int, Pipeline] = {}

    mdir = Path(models_dir) if models_dir else (root / "ml" / "models")
    mdir.mkdir(parents=True, exist_ok=True)

    for h in horizons:
        target_col = f"target_+{h}h"
        if target_col not in df.columns:
            target_col = f"target_{h}h"

        valid_train = train_df[target_col].notna()
        X_tr = X_train_full[valid_train].copy()
        y_tr = train_df.loc[valid_train, target_col].astype(int)

        valid_test = test_df[target_col].notna()
        X_te = X_test_full[valid_test].copy()
        y_te = test_df.loc[valid_test, target_col].astype(int)

        logger.info(f"Training horizon +{h}h candidate GBDT model...")
        cand_pipe, base_pipe, dummy_clf, comp_metrics = train_single_candidate_horizon(
            X_train=X_tr,
            y_train=y_tr,
            X_test=X_te,
            y_test=y_te,
            numeric_cols=num_cols,
            categorical_cols=cat_cols,
            horizon_hours=h,
            random_state=random_state,
        )

        target_results.append(comp_metrics)
        trained_pipelines[h] = cand_pipe

        # Save candidate model artifact
        cand_artifact_path = mdir / f"candidate_gbdt_plus_{h}h_{candidate_version}.joblib"
        joblib.dump(cand_pipe, cand_artifact_path)
        logger.info(f"Saved candidate artifact: {cand_artifact_path}")

    # Save model metadata adhering to repository conventions
    meta_path = mdir / f"model_metadata_{candidate_version}.json"
    metadata_payload = {
        "model_version": candidate_version,
        "model_type": "GradientBoostingClassifier",
        "created_at": now_iso,
        "is_synthetic_data": bool(df.get("is_synthetic", pd.Series([False])).iloc[0]),
        "is_reanalysis_data": bool(df.get("is_reanalysis", pd.Series([False])).iloc[0]),
        "disclaimer": (
            "RESEARCH PROTOTYPE: Candidate model trained on ERA5 reanalysis precipitation and GloFAS discharge proxy. "
            "Benchmarked against baseline Random Forest (era5-v1). Not for unvalidated operational alerting."
        ),
        "features": {
            "numeric": num_cols,
            "categorical": cat_cols,
        },
        "horizons_hours": horizons,
        "training_samples": len(train_df),
        "test_samples": len(test_df),
        "target_mapping": {"0": "low", "1": "moderate", "2": "high", "3": "critical"},
        "candidate_hyperparameters": {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.08,
            "subsample": 0.9,
            "random_state": random_state,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2)
    logger.info(f"Saved candidate metadata: {meta_path}")

    # Build and save report
    report = CandidateTrainingReport(
        run_id=f"train_{candidate_version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        timestamp=now_iso,
        model_version=candidate_version,
        model_type="GradientBoostingClassifier",
        data_source=dpath.name,
        is_reanalysis_data=metadata_payload["is_reanalysis_data"],
        is_synthetic_data=metadata_payload["is_synthetic_data"],
        label_sufficiency_status="SUFFICIENT",
        label_audit=label_audit,
        train_time_range=train_range,
        test_time_range=test_range,
        feature_list_numeric=num_cols,
        feature_list_categorical=cat_cols,
        horizons=target_results,
        verdict="CANDIDATE_TRAINED_AND_BENCHMARKED",
    )

    rdir = Path(reports_dir) if reports_dir else (root / "ml" / "reports")
    rdir.mkdir(parents=True, exist_ok=True)
    report_path = rdir / f"training_report_{candidate_version}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    logger.info(f"Saved candidate training report: {report_path}")

    return report


if __name__ == "__main__":
    rep = run_candidate_training()
    print(f"\n{'='*75}\nCANDIDATE MODEL OFFLINE TRAINING & BENCHMARK\n{'='*75}")
    print(f"Run ID: {rep.run_id} | Model Version: {rep.model_version}")
    print(f"Verdict: {rep.verdict}\n")
    for h_res in rep.horizons:
        print(f"--- Horizon +{h_res.horizon_hours}h ---")
        print(f"  Dummy Macro F1:       {h_res.dummy_macro_f1:.4f} (Bal Acc: {h_res.dummy_balanced_accuracy:.4f})")
        print(f"  Baseline RF Macro F1: {h_res.baseline_rf_macro_f1:.4f} (Bal Acc: {h_res.baseline_rf_balanced_accuracy:.4f}, Exact: {h_res.baseline_rf_exact_accuracy*100:.2f}%)")
        print(f"  Candidate GBDT F1:    {h_res.candidate_gbdt_macro_f1:.4f} (Bal Acc: {h_res.candidate_gbdt_balanced_accuracy:.4f}, Exact: {h_res.candidate_gbdt_exact_accuracy*100:.2f}%)")
        print(f"  Delta vs Baseline:    {h_res.macro_f1_delta_vs_baseline:+.4f}")
        print(f"  Warning Precision:    {h_res.candidate_warning_precision*100:.2f}%, Recall: {h_res.candidate_warning_recall*100:.2f}%, F1: {h_res.candidate_warning_f1:.4f}")
        print(f"  FAR (False Alarm Ratio): {h_res.candidate_false_alarm_ratio*100:.2f}%, POFD: {h_res.candidate_false_alarm_rate_pofd*100:.2f}%")
    print(f"{'='*75}\n")
