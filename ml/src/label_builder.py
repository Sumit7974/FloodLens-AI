"""Label builder and multi-horizon target generator for FloodLens AI.

Defines 4-tier flood risk classification based on Nepal DHM warning thresholds,
constructs non-leaking prediction targets for +1h, +3h, and +6h forecasting horizons,
and provides a physically consistent synthetic demonstration dataset generator
representing the Sapta Koshi River basin in the Nepal Terai region.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Numeric mapping for risk classes
RISK_LABEL_TO_ID: Dict[str, int] = {
    "low": 0,
    "moderate": 1,
    "high": 2,
    "critical": 3,
}

RISK_ID_TO_LABEL: Dict[int, str] = {v: k for k, v in RISK_LABEL_TO_ID.items()}

# Official DHM Chatara Benchmark Thresholds (Sapta Koshi Gauge)
DHM_CHATARA_WARNING_STAGE_M = 6.0
DHM_CHATARA_DANGER_STAGE_M = 7.0
DHM_CHATARA_CRITICAL_STAGE_M = 8.0

# 24-hour cumulative precipitation thresholds (mm)
RAIN_24H_MODERATE_MM = 50.0
RAIN_24H_HIGH_MM = 100.0
RAIN_24H_CRITICAL_MM = 150.0


def assign_instantaneous_risk_label(
    river_stage_m: float,
    rate_of_rise_m_per_h: float = 0.0,
    rainfall_rolling_24h_mm: float = 0.0,
    upstream_discharge_m3s: Optional[float] = None,
) -> str:
    """Classify instantaneous flood risk into one of 4 tiers: low, moderate, high, critical.

    Uses DHM Chatara operational benchmarks:
    - critical: stage >= 7.0m (DHM Danger), or discharge >= 9000 m3/s, or 24h rain >= 150mm.
    - high: stage >= 6.0m (DHM Warning), or discharge >= 6500 m3/s, or 24h rain >= 100mm.
    - moderate: stage >= 4.5m or rapid rise rate >= 0.5 m/h, or 24h rain >= 50mm.
    - low: below all warning benchmarks.
    """
    if pd.isna(river_stage_m) and pd.isna(rainfall_rolling_24h_mm):
        return "unknown"

    stage = float(river_stage_m) if not pd.isna(river_stage_m) else 0.0
    rain24 = float(rainfall_rolling_24h_mm) if not pd.isna(rainfall_rolling_24h_mm) else 0.0
    rise = float(rate_of_rise_m_per_h) if not pd.isna(rate_of_rise_m_per_h) else 0.0
    discharge = float(upstream_discharge_m3s) if upstream_discharge_m3s is not None and not pd.isna(upstream_discharge_m3s) else None

    # Tier 3: Critical
    if stage >= DHM_CHATARA_DANGER_STAGE_M:
        return "critical"
    if discharge is not None and discharge >= 9000.0:
        return "critical"
    if rain24 >= RAIN_24H_CRITICAL_MM and stage >= 5.5:
        return "critical"

    # Tier 2: High
    if stage >= DHM_CHATARA_WARNING_STAGE_M:
        return "high"
    if discharge is not None and discharge >= 6500.0:
        return "high"
    if rain24 >= RAIN_24H_HIGH_MM and stage >= 5.0:
        return "high"

    # Tier 1: Moderate
    if stage >= 4.5 or (stage >= 3.5 and rise >= 0.5):
        return "moderate"
    if rain24 >= RAIN_24H_MODERATE_MM:
        return "moderate"

    # Tier 0: Low
    return "low"


def build_multi_horizon_labels(
    df: pd.DataFrame,
    horizons: List[int] = [1, 3, 6],
    timestamp_col: str = "timestamp",
    stage_col: str = "river_stage_m",
    rise_col: str = "river_stage_rate_of_rise_m_per_h",
    rain24_col: str = "rainfall_rolling_24h_mm",
    discharge_col: Optional[str] = "upstream_discharge_m3s",
) -> pd.DataFrame:
    """Compute instantaneous risk labels and construct future horizon labels (+1h, +3h, +6h).

    STRICT TEMPORAL LEAKAGE RULE:
    Observations at row t represent features known at or before timestamp t.
    The prediction target for horizon +h hours is obtained by looking at the true
    risk label realized at timestamp t + h hours.
    No future features (rainfall, river level) are merged into row t's feature space.
    """
    out_df = df.copy()

    # Sort strictly by timestamp
    if timestamp_col in out_df.columns:
        out_df[timestamp_col] = pd.to_datetime(out_df[timestamp_col], utc=True)
        out_df = out_df.sort_values(timestamp_col).reset_index(drop=True)

    # Compute instantaneous label at current time t
    discharge_vals = out_df[discharge_col] if discharge_col and discharge_col in out_df.columns else [None] * len(out_df)
    labels: List[str] = []
    for s, r, r24, d in zip(
        out_df[stage_col],
        out_df[rise_col] if rise_col in out_df.columns else [0.0] * len(out_df),
        out_df[rain24_col] if rain24_col in out_df.columns else [0.0] * len(out_df),
        discharge_vals,
    ):
        labels.append(assign_instantaneous_risk_label(s, r, r24, d))

    out_df["instantaneous_risk_label"] = labels
    out_df["instantaneous_risk_id"] = [RISK_LABEL_TO_ID.get(lbl, -1) for lbl in labels]

    # Create target columns for each horizon h by shifting future instantaneous label backward
    for h in horizons:
        label_col_name = f"risk_label_+{h}h"
        id_col_name = f"target_+{h}h"

        out_df[label_col_name] = out_df["instantaneous_risk_label"].shift(-h)
        # Convert to numeric class ID (-1 for missing/end-of-series)
        out_df[id_col_name] = out_df[label_col_name].map(lambda x: RISK_LABEL_TO_ID.get(str(x), np.nan))

    return out_df


def generate_synthetic_koshi_event(
    start_date: str = "2024-08-10T00:00:00Z",
    n_hours: int = 240,  # 10 days of hourly observations
    random_state: int = 42,
    location_id: str = "loc_barahachhetra_w2",
    station_id: str = "dhm_chatara_gauge",
) -> pd.DataFrame:
    """Generate physically consistent synthetic demonstration data for the Sapta Koshi basin.

    Models a realistic monsoon flood surge in Barahachhetra / Chatara, Sunsari District, Nepal:
    - Base flow with seasonal monsoon background
    - Multi-day heavy cloudburst rainfall event (hours 60 to 120)
    - Runoff propagation delay (river crests ~6-12 hours after rainfall peak)
    - Realistic gauge dynamics, discharge correlation, temperature drop, and humidity rise
    - Injects realistic noise and realistic edge conditions

    Explicitly marked with mode='historical_demo' and is_synthetic=True.
    """
    rng = np.random.default_rng(random_state)
    start_ts = pd.to_datetime(start_date, utc=True)
    timestamps = [start_ts + timedelta(hours=i) for i in range(n_hours)]

    # Time array in hours
    t = np.arange(n_hours)

    # Base monsoon rainfall (diurnal variation + random light showers)
    diurnal_rain = np.maximum(0.0, 3.0 * np.sin(2 * np.pi * t / 24.0) + rng.normal(0, 1.5, n_hours))

    # Extreme monsoon cloudburst wave peaking around hour 80-100
    peak_center = 85.0
    storm_width = 16.0
    storm_surge = 45.0 * np.exp(-((t - peak_center) ** 2) / (2 * (storm_width ** 2)))
    # Add second secondary pulse
    surge_2 = 30.0 * np.exp(-((t - 110.0) ** 2) / (2 * (10.0 ** 2)))

    hourly_rain = np.maximum(0.0, diurnal_rain + storm_surge + surge_2 + rng.exponential(1.5, n_hours))
    # Round to 1 decimal place (standard gauge precision)
    hourly_rain = np.round(hourly_rain, 1)

    # Catchment rolling rainfall
    rain_s = pd.Series(hourly_rain)
    rain_3h = rain_s.rolling(3, min_periods=1).sum().round(1)
    rain_6h = rain_s.rolling(6, min_periods=1).sum().round(1)
    rain_24h = rain_s.rolling(24, min_periods=1).sum().round(1)

    # River stage response (Sapta Koshi at Chatara)
    # Baseline non-flood stage: 3.2m
    # Runoff convolution with physical lag (~8 hours)
    lag = 8
    convolved_runoff = np.zeros(n_hours)
    for i in range(lag, n_hours):
        # Weighted accumulation of past 24 hours rainfall
        window = hourly_rain[max(0, i - 24):i - lag]
        if len(window) > 0:
            convolved_runoff[i] = np.sum(window) * 0.015

    base_stage = 3.2 + 0.3 * np.sin(2 * np.pi * t / 24.0)
    river_stage = base_stage + convolved_runoff + rng.normal(0, 0.08, n_hours)
    # Bound to realistic physical bounds
    river_stage = np.clip(np.round(river_stage, 2), 2.5, 9.5)

    # River stage rate of rise (m/h)
    stage_s = pd.Series(river_stage)
    rate_of_rise = stage_s.diff().fillna(0.0).round(3)

    # Discharge roughly follows rating curve Q = a * (h - h0)^b
    # For Sapta Koshi at Chatara, base discharge ~ 2,500 m3/s, peak up to 10,000 m3/s
    discharge = 2000.0 + 850.0 * (river_stage - 2.5) ** 1.6 + rng.normal(0, 150, n_hours)
    discharge = np.clip(np.round(discharge, 1), 1200.0, 15000.0)

    # Forecast precipitation for next 3 hours (simulating GFS/ECMWF forecast available at time t)
    # Forecast captures storm trend with some prediction error
    lead_rain = np.roll(hourly_rain, -3)
    forecast_precip_next_3h = pd.Series(lead_rain).rolling(3, min_periods=1).sum() + rng.normal(0, 3.0, n_hours)
    forecast_precip_next_3h = np.maximum(0.0, np.round(forecast_precip_next_3h, 1))

    # Temperature and humidity
    # Heavy rain causes temperature drop from 32C to 24C, and humidity rise to 98%
    temperature_c = np.round(31.0 - 6.0 * (rain_24h / (rain_24h.max() + 1e-5)) + rng.normal(0, 0.5, n_hours), 1)
    relative_humidity_pct = np.round(np.clip(72.0 + 25.0 * (rain_24h / (rain_24h.max() + 1e-5)) + rng.normal(0, 1.5, n_hours), 50.0, 100.0), 1)

    # Categorical features
    season = ["monsoon"] * n_hours
    catchment_saturation_class = [
        "saturated" if r > 100 else ("wet" if r > 40 else "normal") for r in rain_24h
    ]

    df = pd.DataFrame({
        "timestamp": [ts.isoformat() for ts in timestamps],
        "event_id": ["evt_nepal_terai_koshi"] * n_hours,
        "location_id": [location_id] * n_hours,
        "station_id": [station_id] * n_hours,
        "latitude": [26.87] * n_hours,
        "longitude": [87.16] * n_hours,
        "rainfall_mm": hourly_rain,
        "rainfall_rolling_3h_mm": rain_3h.values,
        "rainfall_rolling_6h_mm": rain_6h.values,
        "rainfall_rolling_24h_mm": rain_24h.values,
        "river_stage_m": river_stage,
        "river_stage_rate_of_rise_m_per_h": rate_of_rise.values,
        "upstream_discharge_m3s": discharge,
        "forecast_precip_next_3h_mm": forecast_precip_next_3h.values,
        "temperature_c": temperature_c,
        "relative_humidity_pct": relative_humidity_pct,
        "season": season,
        "catchment_saturation_class": catchment_saturation_class,
        "mode": ["historical_demo"] * n_hours,
        "is_synthetic": [True] * n_hours,
    })

    # Build targets
    labeled_df = build_multi_horizon_labels(df)
    return labeled_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Koshi flood dataset and labels.")
    parser.add_argument("--output", type=str, default="ml/data/synthetic/synthetic_koshi_event.csv", help="Output path for synthetic CSV.")
    parser.add_argument("--n-hours", type=int, default=240, help="Number of hourly timesteps.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = parser.parse_args()

    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    df = generate_synthetic_koshi_event(n_hours=args.n_hours, random_state=args.seed)
    df.to_csv(out_p, index=False)
    logger.info(f"Generated {len(df)} synthetic records saved to {out_p}")


if __name__ == "__main__":
    main()
