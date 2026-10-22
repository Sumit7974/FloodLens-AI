"""
Day 5 Validation Tests: Baseline Freeze Integrity, Temporal Leakage Audit, and Sandboxed Retraining.

Tests:
1. Baseline Freeze Manifest verification and cryptographic tamper detection.
2. Temporal Leakage Audit feature categorization (detecting lookahead shift and same-day aggregation).
3. Chronological 3-way partition boundaries and non-overlap.
4. Candidate leak-free experiment artifact validation (omission of leaking features, valid inference).
5. Safety constraints: ensuring candidate artifacts are sandboxed and baseline remains untouched.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import joblib

from ml.src.baseline_freeze import (
    compute_sha256,
    generate_baseline_freeze_manifest,
    verify_frozen_baseline_integrity,
)
from ml.src.leakage_audit import (
    run_temporal_leakage_audit,
    audit_feature_temporal_integrity,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "ml" / "reports" / "frozen_baseline_manifest.json"
DATASET_PATH = REPO_ROOT / "ml" / "data" / "processed" / "era5_glofas_labeled.csv"
AUDIT_REPORT_PATH = REPO_ROOT / "ml" / "reports" / "temporal_leakage_audit.json"


class TestDay5BaselineFreeze:
    """Verifies that the frozen baseline model artifacts and dataset are cryptographically verified."""

    def test_manifest_file_exists_and_valid_json(self):
        assert MANIFEST_PATH.exists(), f"Manifest file missing at {MANIFEST_PATH}"
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["manifest_id"].startswith("manifest_freeze_era5_v1_")
        assert manifest["total_samples_count"] == 5856
        assert len(manifest["primary_dataset_sha256"]) == 64
        assert len(manifest["frozen_artifacts"]) == 5  # 1 dataset + 3 models + 1 metadata

    def test_baseline_dataset_and_models_integrity(self):
        is_intact, discrepancies = verify_frozen_baseline_integrity()
        assert is_intact is True, f"Integrity violations detected: {discrepancies}"
        assert len(discrepancies) == 0

    def test_tamper_detection(self, tmp_path):
        # Create a modified manifest with a corrupted hash
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["frozen_artifacts"][0]["sha256_checksum"] = "0" * 64
        
        tampered_manifest_path = tmp_path / "tampered_manifest.json"
        with open(tampered_manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
            
        is_intact, discrepancies = verify_frozen_baseline_integrity(manifest_path=tampered_manifest_path)
        assert is_intact is False
        assert any("CHECKSUM MISMATCH" in d for d in discrepancies)


class TestDay5TemporalLeakageAudit:
    """Verifies that the temporal data-leakage audit correctly identifies lookahead and calendar aggregation flaws."""

    def test_audit_report_identifies_leaks(self):
        df = pd.read_csv(DATASET_PATH)
        records, preprocessing_audit = audit_feature_temporal_integrity(df)
        assert len(records) >= 11, f"Expected at least 11 audited features, got {len(records)}"

        results_by_name = {rec.feature_name: rec for rec in records}

        # Check the 2 failing features
        precip_next_3h = results_by_name["forecast_precip_next_3h_mm"]
        assert precip_next_3h.leakage_status == "FAIL"
        assert "shift(-3)" in precip_next_3h.evidence_and_explanation

        upstream_q = results_by_name["upstream_discharge_m3s"]
        assert upstream_q.leakage_status == "FAIL"
        assert "24 hours" in upstream_q.corrective_action_required

        # Check antecedent features pass
        assert results_by_name["rainfall_mm"].leakage_status == "PASS"
        assert results_by_name["rainfall_rolling_3h_mm"].leakage_status == "PASS"
        assert results_by_name["rainfall_rolling_24h_mm"].leakage_status == "PASS"

        # Check preprocessing status
        assert preprocessing_audit["status"] == "PASS"

    def test_audit_report_json_matches_results(self):
        assert AUDIT_REPORT_PATH.exists()
        with open(AUDIT_REPORT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_features_audited"] == 12
        assert data["fail_count"] == 2
        assert data["pass_count"] == 10


class TestDay5ChronologicalSplits:
    """Verifies strict chronological ordering and non-overlap for train, validation, and test splits."""

    def test_chronological_splits_strictly_ordered(self):
        assert DATASET_PATH.exists()
        df = pd.read_csv(DATASET_PATH)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        n = len(df)
        train_end = int(n * 0.70)
        val_end = int(n * 0.82)

        train_df = df.iloc[:train_end]
        val_df = df.iloc[train_end:val_end]
        test_df = df.iloc[val_end:]

        assert len(train_df) + len(val_df) + len(test_df) == n

        # Verify strict non-overlapping temporal ordering
        max_train_ts = train_df["timestamp"].max()
        min_val_ts = val_df["timestamp"].min()
        max_val_ts = val_df["timestamp"].max()
        min_test_ts = test_df["timestamp"].min()

        assert max_train_ts < min_val_ts, f"Train overlap: {max_train_ts} >= {min_val_ts}"
        assert max_val_ts < min_test_ts, f"Val overlap: {max_val_ts} >= {min_test_ts}"


class TestDay5RetrainingExperiment:
    """Verifies candidate model artifacts, safety isolation, and omission of leaked features."""

    @pytest.mark.parametrize("horizon", ["1h", "3h", "6h"])
    def test_candidate_artifacts_exist_and_isolated(self, horizon):
        candidate_path = REPO_ROOT / "ml" / "models" / "experiments" / f"leakfree_rf_plus_{horizon}_candidate-leakfree-v1.joblib"
        assert candidate_path.exists(), f"Candidate model missing at {candidate_path}"

        baseline_path = REPO_ROOT / "ml" / "models" / f"baseline_rf_plus_{horizon}_era5-v1.joblib"
        assert baseline_path.exists(), f"Baseline model missing at {baseline_path}"

        # Ensure they are distinct files
        assert candidate_path.resolve() != baseline_path.resolve()

    def test_candidate_omits_leaked_features(self):
        candidate_path = REPO_ROOT / "ml" / "models" / "experiments" / "leakfree_rf_plus_1h_candidate-leakfree-v1.joblib"
        pipeline = joblib.load(candidate_path)

        # Candidate feature list omits forecast_precip_next_3h_mm
        metadata_path = REPO_ROOT / "ml" / "models" / "experiments" / "experiment_metadata_candidate-leakfree-v1.json"
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        
        feature_names = meta["features"]["numeric"] + meta["features"]["categorical"]
        assert len(feature_names) == 11
        assert "forecast_precip_next_3h_mm" not in feature_names
        assert "rainfall_mm" in feature_names
        assert "upstream_discharge_m3s_lag24h" in feature_names

    def test_candidate_inference_outputs_valid_probabilities(self):
        candidate_path = REPO_ROOT / "ml" / "models" / "experiments" / "leakfree_rf_plus_3h_candidate-leakfree-v1.joblib"
        pipeline = joblib.load(candidate_path)

        metadata_path = REPO_ROOT / "ml" / "models" / "experiments" / "experiment_metadata_candidate-leakfree-v1.json"
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        
        # Dummy feature row matching candidate features
        dummy_row = pd.DataFrame([{
            "rainfall_mm": 5.0,
            "rainfall_rolling_3h_mm": 12.0,
            "rainfall_rolling_6h_mm": 20.0,
            "rainfall_rolling_24h_mm": 45.0,
            "river_stage_m": np.nan,
            "river_stage_rate_of_rise_m_per_h": np.nan,
            "upstream_discharge_m3s_lag24h": 1200.0,
            "temperature_c": 28.5,
            "relative_humidity_pct": 82.0,
            "season": "monsoon",
            "catchment_saturation_class": "saturated",
        }])

        pred = pipeline.predict(dummy_row)
        probs = pipeline.predict_proba(dummy_row)[0]

        assert pred[0] in [0, 1, 2, 3]
        assert len(probs) == 4
        assert np.isclose(np.sum(probs), 1.0)
        assert all(0.0 <= p <= 1.0 for p in probs)
