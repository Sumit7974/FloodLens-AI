"""Prediction service and backend contract integration for FloodLens AI.

Loads trained multi-horizon baseline models, validates input hydrological features,
guards against missing feed edge-cases (preventing silent false low-risk predictions),
and formats prediction payloads adhering strictly to the backend API contract.
"""
from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ID_TO_RISK_LABEL = {0: "low", 1: "moderate", 2: "high", 3: "critical"}
RISK_LABEL_TO_ID = {v: k for k, v in ID_TO_RISK_LABEL.items()}

# Core critical features that cannot be entirely absent without degrading prediction safety
CRITICAL_HYDROLOGICAL_FEATURES = ["river_stage_m", "rainfall_rolling_24h_mm", "rainfall_mm"]


class FloodRiskPredictor:
    """Predictor providing multi-horizon flood risk inferences adhering to backend contracts."""

    def __init__(
        self,
        models_dir: Path | str = "ml/models",
        model_version: str = "baseline-v1",
    ) -> None:
        self.models_dir = Path(models_dir)
        self.model_version = model_version
        self.models: Dict[int, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Load model metadata and horizon pipelines from serialized joblib artifacts."""
        meta_path = self.models_dir / f"model_metadata_{self.model_version}.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            logger.warning(f"Model metadata not found at {meta_path}. Using default configuration.")
            self.metadata = {
                "model_version": self.model_version,
                "is_synthetic_data": True,
                "horizons_hours": [1, 3, 6],
                "features": {
                    "numeric": [
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
                    ],
                    "categorical": ["season", "catchment_saturation_class"],
                },
            }

        horizons = self.metadata.get("horizons_hours", [1, 3, 6])
        for h in horizons:
            model_path = self.models_dir / f"baseline_rf_plus_{h}h_{self.model_version}.joblib"
            if model_path.exists():
                self.models[h] = joblib.load(model_path)
                logger.info(f"Loaded baseline model for horizon +{h}h from {model_path}")
            else:
                logger.warning(f"Horizon +{h}h model artifact not found at {model_path}")

    def validate_features(self, features: Dict[str, Any]) -> Tuple[bool, List[str], str]:
        """Validate feature dictionary.

        Returns:
            (is_valid, limitations_list, data_quality_status)
        """
        limitations: List[str] = []

        # Check metadata synthetic flag
        if self.metadata.get("is_synthetic_data", True):
            limitations.append("Experimental pipeline test mode: Model trained on synthetic demonstration data.")

        # Check presence of critical features
        missing_critical: List[str] = []
        for feat in CRITICAL_HYDROLOGICAL_FEATURES:
            val = features.get(feat)
            if val is None or pd.isna(val):
                missing_critical.append(feat)

        if len(missing_critical) == len(CRITICAL_HYDROLOGICAL_FEATURES):
            limitations.append(f"All critical hydrological feeds missing: {missing_critical}. Cannot infer risk safely.")
            return False, limitations, "UNAVAILABLE"

        if missing_critical:
            limitations.append(f"Critical feeds missing: {missing_critical}. Predictions may suffer degraded accuracy.")
            return True, limitations, "PARTIAL"

        return True, limitations, "FULL"

    def predict(
        self,
        features: Dict[str, Any],
        location_id: str = "loc_barahachhetra_w2",
        event_id: Optional[str] = "evt_nepal_terai_koshi",
        issued_at: Optional[str] = None,
        input_data_cutoff_at: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate multi-horizon risk forecast matching backend API schema."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        issued_ts = issued_at or now_iso
        cutoff_ts = input_data_cutoff_at or now_iso

        operational_mode = mode or ("historical_demo" if self.metadata.get("is_synthetic_data", True) else "model_estimate")
        is_valid, limitations, data_quality = self.validate_features(features)

        # Safety rule: If critical inputs are missing, NEVER emit a false low-risk result!
        if not is_valid or not self.models:
            if not self.models:
                limitations.append("No trained model artifacts loaded.")
            return {
                "forecast_id": f"fc_{uuid.uuid4().hex[:12]}",
                "event_id": event_id,
                "location_id": location_id,
                "issued_at": issued_ts,
                "mode": operational_mode,
                "model_version": self.model_version,
                "input_data_cutoff_at": cutoff_ts,
                "data_quality": "UNAVAILABLE",
                "horizons": [
                    {"hours": h, "risk_level": "unknown", "calibrated_probability": None}
                    for h in [1, 3, 6]
                ],
                "limitations": limitations,
            }

        # Prepare DataFrame row
        numeric_cols = self.metadata.get("features", {}).get("numeric", [])
        categorical_cols = self.metadata.get("features", {}).get("categorical", [])
        all_cols = numeric_cols + categorical_cols

        row_dict = {}
        for c in all_cols:
            row_dict[c] = features.get(c, np.nan)

        df_row = pd.DataFrame([row_dict])

        horizon_predictions: List[Dict[str, Any]] = []
        for h, model in sorted(self.models.items()):
            try:
                # Predict class
                pred_class_id = int(model.predict(df_row)[0])
                risk_level = ID_TO_RISK_LABEL.get(pred_class_id, "low")

                # Probabilities
                prob = None
                if hasattr(model, "predict_proba"):
                    proba_vec = model.predict_proba(df_row)[0]
                    # Probability of critical or high risk
                    # Note: We do not present uncalibrated model probability as ground truth
                    # We report the model's confidence for the predicted class
                    classes = getattr(model, "classes_", [0, 1, 2, 3])
                    if pred_class_id in classes:
                        class_idx = list(classes).index(pred_class_id)
                        prob = round(float(proba_vec[class_idx]), 4)

                horizon_predictions.append({
                    "hours": h,
                    "risk_level": risk_level,
                    "calibrated_probability": prob,
                })
            except Exception as exc:
                logger.error(f"Error predicting horizon +{h}h: {exc}")
                limitations.append(f"Inference error for horizon +{h}h: {str(exc)}")
                horizon_predictions.append({
                    "hours": h,
                    "risk_level": "unknown",
                    "calibrated_probability": None,
                })

        return {
            "forecast_id": f"fc_{uuid.uuid4().hex[:12]}",
            "event_id": event_id,
            "location_id": location_id,
            "issued_at": issued_ts,
            "mode": operational_mode,
            "model_version": self.model_version,
            "input_data_cutoff_at": cutoff_ts,
            "data_quality": data_quality,
            "horizons": horizon_predictions,
            "limitations": limitations,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run inference using trained FloodLens baseline model.")
    parser.add_argument("--features", type=str, help="JSON string or path to JSON file containing feature dictionary.")
    parser.add_argument("--location-id", type=str, default="loc_barahachhetra_w2", help="Target location identifier.")
    parser.add_argument("--models-dir", type=str, default="ml/models", help="Directory with trained model artifacts.")
    parser.add_argument("--model-version", type=str, default="baseline-v1", help="Model version identifier.")
    args = parser.parse_args()

    predictor = FloodRiskPredictor(models_dir=args.models_dir, model_version=args.model_version)

    sample_features: Dict[str, Any] = {
        "rainfall_mm": 28.5,
        "rainfall_rolling_3h_mm": 64.0,
        "rainfall_rolling_6h_mm": 110.2,
        "rainfall_rolling_24h_mm": 165.4,
        "river_stage_m": 6.85,
        "river_stage_rate_of_rise_m_per_h": 0.35,
        "upstream_discharge_m3s": 7800.0,
        "forecast_precip_next_3h_mm": 35.0,
        "temperature_c": 24.5,
        "relative_humidity_pct": 96.0,
        "season": "monsoon",
        "catchment_saturation_class": "saturated",
    }

    if args.features:
        feat_p = Path(args.features)
        if feat_p.exists():
            with open(feat_p, "r", encoding="utf-8") as f:
                sample_features = json.load(f)
        else:
            sample_features = json.loads(args.features)

    prediction = predictor.predict(sample_features, location_id=args.location_id)
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()
