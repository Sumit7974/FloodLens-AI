"""Tests for flood risk label construction, horizon shifting, and synthetic data generation."""
import numpy as np
import pandas as pd
import pytest

from ml.src.label_builder import (
    DHM_CHATARA_DANGER_STAGE_M,
    DHM_CHATARA_WARNING_STAGE_M,
    RISK_LABEL_TO_ID,
    assign_instantaneous_risk_label,
    build_multi_horizon_labels,
    generate_synthetic_koshi_event,
)


def test_dhm_warning_threshold_assignments():
    # Critical risk: stage >= 7.0m (DHM Danger level)
    assert assign_instantaneous_risk_label(river_stage_m=7.1) == "critical"
    # Critical risk: discharge >= 9000 m3/s
    assert assign_instantaneous_risk_label(river_stage_m=5.8, upstream_discharge_m3s=9200.0) == "critical"

    # High risk: stage >= 6.0m (DHM Warning level)
    assert assign_instantaneous_risk_label(river_stage_m=6.2) == "high"
    # High risk: 24h rain >= 100mm and elevated stage
    assert assign_instantaneous_risk_label(river_stage_m=5.2, rainfall_rolling_24h_mm=110.0) == "high"

    # Moderate risk: stage >= 4.5m
    assert assign_instantaneous_risk_label(river_stage_m=4.8) == "moderate"
    # Moderate risk: rapid rate of rise >= 0.5 m/h
    assert assign_instantaneous_risk_label(river_stage_m=3.8, rate_of_rise_m_per_h=0.6) == "moderate"

    # Low risk: normal baseline
    assert assign_instantaneous_risk_label(river_stage_m=3.2, rate_of_rise_m_per_h=0.1, rainfall_rolling_24h_mm=15.0) == "low"


def test_multi_horizon_target_shifting_prevents_leakage():
    # Construct 10 hours with known river stages
    # At t=0: stage 3.0 (low)
    # At t=1: stage 4.6 (moderate)
    # At t=3: stage 6.2 (high)
    # At t=6: stage 7.2 (critical)
    timestamps = [f"2024-08-10T{i:02d}:00:00Z" for i in range(10)]
    stages = [3.0, 4.6, 5.0, 6.2, 6.5, 6.8, 7.2, 7.5, 6.0, 5.0]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "river_stage_m": stages,
        "rainfall_rolling_24h_mm": [20.0] * 10,
    })

    labeled_df = build_multi_horizon_labels(df, horizons=[1, 3, 6])

    # Check row 0: features reflect t=0 (stage 3.0)
    assert labeled_df.loc[0, "river_stage_m"] == 3.0
    assert labeled_df.loc[0, "instantaneous_risk_label"] == "low"

    # Horizon +1h: realized at t=1 (stage 4.6 -> moderate)
    assert labeled_df.loc[0, "risk_label_+1h"] == "moderate"
    assert labeled_df.loc[0, "target_+1h"] == RISK_LABEL_TO_ID["moderate"]

    # Horizon +3h: realized at t=3 (stage 6.2 -> high)
    assert labeled_df.loc[0, "risk_label_+3h"] == "high"
    assert labeled_df.loc[0, "target_+3h"] == RISK_LABEL_TO_ID["high"]

    # Horizon +6h: realized at t=6 (stage 7.2 -> critical)
    assert labeled_df.loc[0, "risk_label_+6h"] == "critical"
    assert labeled_df.loc[0, "target_+6h"] == RISK_LABEL_TO_ID["critical"]

    # Verify trailing edges are NaN (cannot predict past end of series)
    assert pd.isna(labeled_df.loc[9, "risk_label_+1h"])
    assert pd.isna(labeled_df.loc[7, "risk_label_+3h"])
    assert pd.isna(labeled_df.loc[4, "risk_label_+6h"])


def test_synthetic_koshi_generator_integrity():
    df = generate_synthetic_koshi_event(n_hours=120, random_state=42)

    assert len(df) == 120
    assert "timestamp" in df.columns
    assert "river_stage_m" in df.columns
    assert "rainfall_mm" in df.columns
    assert "upstream_discharge_m3s" in df.columns
    assert "target_+1h" in df.columns
    assert "target_+3h" in df.columns
    assert "target_+6h" in df.columns

    # Explicit synthetic and demo provenance metadata
    assert bool(df["is_synthetic"].iloc[0]) is True
    assert df["mode"].iloc[0] == "historical_demo"

    # Check realistic physical range bounds
    assert df["river_stage_m"].min() >= 2.0
    assert df["river_stage_m"].max() <= 12.0
    assert df["rainfall_mm"].min() >= 0.0
