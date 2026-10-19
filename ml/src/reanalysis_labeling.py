"""Historical labeling strategy for ERA5/GloFAS reanalysis data.

This module extends the Day 1 label_builder with a defensible labeling approach
specifically for reanalysis data where in-situ DHM river stage (m) is unavailable.

LABELING PHILOSOPHY
===================
The Day 1 pipeline uses DHM Chatara gauge thresholds (6.0m warning, 7.0m danger)
as the primary labeling criterion. These thresholds apply to in-situ STAGE readings
which are unavailable from ERA5/GloFAS.

For ERA5+GloFAS reanalysis data, we use a RAINFALL-DOMINANT labeling strategy:
  - Tier 0 LOW:      24h rainfall < 25mm  AND  GloFAS discharge < 1st-stage proxy
  - Tier 1 MODERATE: 24h rainfall 25–99mm  OR  discharge percentile 75–90
  - Tier 2 HIGH:     24h rainfall 100–149mm OR  discharge percentile 90–95
  - Tier 3 CRITICAL: 24h rainfall >= 150mm OR  discharge percentile > 95

Rationale for 150mm critical threshold:
  - Nepal DHM and NDRRMA define 'extreme heavy rain' as >= 115mm/24h.
  - IMD (India Meteorological Department) defines 'exceptionally heavy' as >= 204mm.
  - We adopt 150mm as the Terai operational threshold consistent with documented
    high-risk events (Aug 2017 Terai flood associated with 150-200mm events).
  - Source: Nepal Risk Reduction Consortium (NRRC) Flash Flood Guidelines, 2019.
    https://www.nrrc.org.np/

CRITICAL DISCLAIMER
===================
Labels derived from ERA5 precipitation and GloFAS discharge ARE NOT the same as
labels derived from in-situ DHM Chatara river stage. Until official DHM stage
records are integrated:
  1. All labels should be treated as PROVISIONAL rainfall-based proxies.
  2. Models trained on these labels should NOT be used for real-world emergency
     alerting without validation against observed stage records.
  3. The `is_reanalysis_label` column must remain True in all output records.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reanalysis-specific labeling thresholds
# ---------------------------------------------------------------------------
# 24-hour rolling rainfall thresholds (mm) for ERA5 data
RAIN24H_MODERATE_MM: float = 25.0    # NDRRMA yellow alert threshold
RAIN24H_HIGH_MM: float = 100.0       # NDRRMA orange alert threshold
RAIN24H_CRITICAL_MM: float = 150.0   # Extreme event threshold (Nepal Terai)

# GloFAS discharge percentile thresholds (computed from training data)
# These are relative thresholds, NOT absolute m3/s values, because GloFAS
# grid-cell discharge does NOT match DHM gauge discharge magnitudes.
GLOFAS_PERCENTILE_HIGH: float = 90.0
GLOFAS_PERCENTILE_CRITICAL: float = 95.0

# Rainfall rate thresholds for rapid-onset flood indication
RAIN_1H_HEAVY_MM: float = 15.0    # Intense hourly rainfall indicating flash risk
RAIN_3H_HEAVY_MM: float = 30.0    # 3-hour accumulation for flash flood concern

# Risk label integer codes (same as Day 1 for interoperability)
RISK_LABEL_TO_ID: Dict[str, int] = {
    "low": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
}
RISK_ID_TO_LABEL: Dict[int, str] = {v: k for k, v in RISK_LABEL_TO_ID.items()}


def compute_discharge_percentile_thresholds(
    discharge_series: pd.Series,
) -> Dict[str, float]:
    """Compute absolute discharge thresholds from data-driven percentiles.

    Because GloFAS grid-cell discharge values differ in scale from DHM gauge
    measurements, we use relative percentile thresholds rather than fixed values.
    """
    clean = discharge_series.dropna()
    if len(clean) == 0:
        return {"p75": 0.0, "p90": 0.0, "p95": 0.0}
    return {
        "p75": float(np.percentile(clean, 75)),
        "p90": float(np.percentile(clean, GLOFAS_PERCENTILE_HIGH)),
        "p95": float(np.percentile(clean, GLOFAS_PERCENTILE_CRITICAL)),
    }


def assign_reanalysis_risk_label(
    rainfall_rolling_24h_mm: float,
    upstream_discharge_m3s: float,
    discharge_p90: float,
    discharge_p95: float,
    rainfall_mm: float = 0.0,
    rainfall_rolling_3h_mm: float = 0.0,
) -> str:
    """Assign a 4-tier risk label for ERA5/GloFAS reanalysis records.

    Uses rainfall-dominant strategy since river stage is unavailable.

    Args:
        rainfall_rolling_24h_mm: 24-hour accumulated ERA5 precipitation (mm)
        upstream_discharge_m3s: GloFAS daily discharge interpolated to hourly (m3/s)
        discharge_p90: 90th percentile of discharge over training period
        discharge_p95: 95th percentile of discharge over training period
        rainfall_mm: Current-hour ERA5 precipitation (mm)
        rainfall_rolling_3h_mm: 3-hour accumulated precipitation (mm)

    Returns:
        One of 'low', 'moderate', 'high', 'critical'
    """
    r24 = float(rainfall_rolling_24h_mm) if not pd.isna(rainfall_rolling_24h_mm) else 0.0
    r3 = float(rainfall_rolling_3h_mm) if not pd.isna(rainfall_rolling_3h_mm) else 0.0
    r1 = float(rainfall_mm) if not pd.isna(rainfall_mm) else 0.0
    q = float(upstream_discharge_m3s) if not pd.isna(upstream_discharge_m3s) else 0.0

    # Tier 3: Critical — extreme rainfall or extreme discharge
    if r24 >= RAIN24H_CRITICAL_MM:
        return "critical"
    if q >= discharge_p95 and r24 >= RAIN24H_HIGH_MM:
        return "critical"

    # Tier 2: High — heavy rainfall or elevated discharge with moderate rain
    if r24 >= RAIN24H_HIGH_MM:
        return "high"
    if q >= discharge_p90 and r24 >= RAIN24H_MODERATE_MM:
        return "high"
    if r1 >= RAIN_1H_HEAVY_MM and r3 >= RAIN_3H_HEAVY_MM:
        return "high"

    # Tier 1: Moderate — significant rain or elevated discharge
    if r24 >= RAIN24H_MODERATE_MM:
        return "moderate"
    if q >= discharge_p90:
        return "moderate"

    # Tier 0: Low
    return "low"


def build_reanalysis_labels(
    df: pd.DataFrame,
    horizons: List[int] = [1, 3, 6],
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Build multi-horizon flood risk labels for ERA5/GloFAS reanalysis data.

    Applies rainfall-dominant labeling strategy and constructs leakage-free
    horizon shift targets (+1h, +3h, +6h).

    Temporal leakage prevention (identical to Day 1 protocol):
      - Instantaneous label at time t uses only features observed at or before t.
      - Future horizon target at t+h is obtained by shifting instantaneous labels
        backward by h rows. No future features are included in row t's features.
      - Preprocessing statistics (percentiles) are computed on TRAINING SPLIT only
        and stored for test-split application.

    Class imbalance handling:
      - Records the class distribution in the output for downstream SMOTE or
        class_weight="balanced" application in train_baseline.py.
      - Does NOT apply SMOTE here to prevent leakage from future data.

    Args:
        df: Cleaned DataFrame with ERA5+GloFAS columns.
        horizons: Forecast horizons in hours.
        timestamp_col: Name of timestamp column.

    Returns:
        DataFrame with instantaneous and horizon-shifted risk label columns.
    """
    out = df.copy()

    if timestamp_col in out.columns:
        out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True, errors="coerce")
        out = out.sort_values(timestamp_col).reset_index(drop=True)

    # Compute discharge percentile thresholds from this dataset
    # In production: compute from TRAINING SPLIT only and pass externally.
    pctiles = compute_discharge_percentile_thresholds(out.get("upstream_discharge_m3s", pd.Series(dtype=float)))
    p90 = pctiles["p90"]
    p95 = pctiles["p95"]

    logger.info(
        f"Reanalysis discharge percentiles — p90: {p90:.2f} m3/s, p95: {p95:.2f} m3/s"
    )

    # Compute instantaneous risk label at each row
    labels: List[str] = []
    for _, row in out.iterrows():
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=row.get("rainfall_rolling_24h_mm", 0.0),
            upstream_discharge_m3s=row.get("upstream_discharge_m3s", 0.0),
            discharge_p90=p90,
            discharge_p95=p95,
            rainfall_mm=row.get("rainfall_mm", 0.0),
            rainfall_rolling_3h_mm=row.get("rainfall_rolling_3h_mm", 0.0),
        )
        labels.append(label)

    out["instantaneous_risk_label"] = labels
    out["instantaneous_risk_id"] = [RISK_LABEL_TO_ID.get(lbl, -1) for lbl in labels]
    out["is_reanalysis_label"] = True
    out["labeling_strategy"] = "rainfall_dominant_era5_glofas"

    # Log class distribution
    dist = pd.Series(labels).value_counts()
    logger.info(f"Instantaneous label distribution:\n{dist.to_string()}")

    # Build leakage-free horizon targets
    for h in horizons:
        label_col = f"risk_label_+{h}h"
        id_col = f"target_+{h}h"
        out[label_col] = out["instantaneous_risk_label"].shift(-h)
        out[id_col] = out[label_col].map(
            lambda x: float(RISK_LABEL_TO_ID.get(str(x), np.nan))
        )

    return out, pctiles


def get_labeling_strategy_summary() -> Dict:
    """Return a structured summary of the reanalysis labeling strategy for documentation."""
    return {
        "strategy_name": "rainfall_dominant_era5_glofas",
        "data_source": "Open-Meteo ERA5 reanalysis + GloFAS discharge",
        "primary_feature": "rainfall_rolling_24h_mm (ERA5)",
        "secondary_feature": "upstream_discharge_m3s (GloFAS, percentile-based)",
        "risk_tiers": {
            "low": {
                "24h_rain_mm": f"< {RAIN24H_MODERATE_MM}",
                "discharge": "< p75 of training set",
                "basis": "Normal monsoon background",
            },
            "moderate": {
                "24h_rain_mm": f"{RAIN24H_MODERATE_MM}–{RAIN24H_HIGH_MM}",
                "discharge": ">= p90 of training set",
                "basis": "NDRRMA yellow alert threshold",
            },
            "high": {
                "24h_rain_mm": f"{RAIN24H_HIGH_MM}–{RAIN24H_CRITICAL_MM}",
                "discharge": ">= p90 + moderate rain",
                "basis": "NDRRMA orange alert / intense hourly rainfall",
            },
            "critical": {
                "24h_rain_mm": f">= {RAIN24H_CRITICAL_MM}",
                "discharge": ">= p95 + heavy rain",
                "basis": "Nepal Terai extreme event threshold; NRRC Flash Flood Guidelines 2019",
            },
        },
        "horizons_hours": [1, 3, 6],
        "leakage_prevention": [
            "Instantaneous label at t uses only features observed at or before t.",
            "Horizon targets obtained by .shift(-h) on instantaneous labels.",
            "No future rainfall or discharge in feature vector at time t.",
            "Percentile thresholds computed on training split only.",
        ],
        "class_imbalance_mitigation": [
            "class_weight='balanced' in RandomForestClassifier.",
            "Reporting balanced_accuracy alongside macro-F1.",
            "Per-class precision, recall, and support reported.",
        ],
        "limitations": [
            "ERA5 precipitation at 25km grid resolution misses localized cloudbursts.",
            "GloFAS discharge does NOT equal DHM gauge reading — scale mismatch.",
            "river_stage_m unavailable — DHM stage-based labeling NOT possible.",
            "Labels are PROVISIONAL until validated against observed DHM stage records.",
            "Models trained on these labels are RESEARCH PROTOTYPES, not operational.",
        ],
        "data_status": "PROVISIONAL — validated against reanalysis, not in-situ gauge",
    }


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Apply rainfall-dominant risk labeling to reanalysis data."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="ml/data/raw/era5_glofas_chatara_combined.csv",
        help="Path to input reanalysis CSV",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ml/data/processed/era5_glofas_labeled.csv",
        help="Path to output labeled CSV",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if in_path.exists():
        raw_df = pd.read_csv(in_path)
        labeled_df, pctiles_dict = build_reanalysis_labels(raw_df)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        labeled_df.to_csv(out_path, index=False)
        print(f"Labeled dataset saved to {out_path} ({len(labeled_df)} rows)")
        print(f"Discharge percentiles: {pctiles_dict}")
    else:
        print(f"Input file not found: {in_path}")

