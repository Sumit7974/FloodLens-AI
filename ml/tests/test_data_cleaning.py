"""Tests for data cleaning, validation, deduplication, and outlier filtering."""
import numpy as np
import pandas as pd
import pytest

from ml.src.data_cleaning import (
    NEPAL_LAT_MAX,
    NEPAL_LAT_MIN,
    NEPAL_LON_MAX,
    NEPAL_LON_MIN,
    clean_hydrological_data,
    standardize_columns,
    to_snake_case,
)


def test_snake_case_conversion():
    assert to_snake_case("Water Level (m)") == "water_level_m"
    assert to_snake_case("Rainfall-mm") == "rainfall_mm"
    assert to_snake_case("RiverStageM") == "river_stage_m"
    assert to_snake_case("  temperature_C  ") == "temperature_c"


def test_standardize_columns():
    df = pd.DataFrame({
        "DateTime": ["2024-08-10 00:00:00"],
        "Water Level": [4.2],
        "Precipitation": [12.0],
        "Discharge": [3100.0],
        "Temp": [28.0],
    })
    std_df = standardize_columns(df)
    expected_cols = ["timestamp", "river_stage_m", "rainfall_mm", "upstream_discharge_m3s", "temperature_c"]
    assert list(std_df.columns) == expected_cols


def test_timestamp_parsing_and_utc_normalization():
    df = pd.DataFrame({
        "timestamp": [
            "2024-08-10T06:00:00Z",
            "2024-08-10 11:45:00+05:45",  # Nepal Standard Time (+05:45)
            "invalid_time_string",
        ],
        "river_stage_m": [3.5, 3.8, 4.0],
        "rainfall_mm": [0.0, 5.0, 10.0],
    })
    clean_df, summary = clean_hydrological_data(df, timestamp_col="timestamp")

    # Invalid timestamp row must be rejected
    assert len(clean_df) == 2
    assert summary.rejected_rows_count == 1
    # Check UTC normalization
    assert clean_df["timestamp"].dt.tz is not None
    # 11:45 NPT (+05:45) is 06:00 UTC
    assert clean_df.iloc[0]["timestamp"] == clean_df.iloc[1]["timestamp"]


def test_duplicate_removal_exact_and_composite_keys():
    df = pd.DataFrame({
        "timestamp": [
            "2024-08-10T06:00:00Z",
            "2024-08-10T06:00:00Z",  # Exact duplicate
            "2024-08-10T06:00:00Z",  # Duplicate key with conflicting value
            "2024-08-10T07:00:00Z",
        ],
        "station_id": ["dhm_chatara", "dhm_chatara", "dhm_chatara", "dhm_chatara"],
        "river_stage_m": [3.5, 3.5, 3.6, 3.8],
        "rainfall_mm": [0.0, 0.0, 2.0, 5.0],
    })
    clean_df, summary = clean_hydrological_data(df, timestamp_col="timestamp", station_col="station_id")

    assert len(clean_df) == 2
    assert summary.duplicate_rows_removed == 1
    assert summary.duplicate_keys_removed == 1


def test_chronological_sorting():
    df = pd.DataFrame({
        "timestamp": [
            "2024-08-10T08:00:00Z",
            "2024-08-10T05:00:00Z",
            "2024-08-10T07:00:00Z",
        ],
        "river_stage_m": [4.1, 3.2, 3.9],
        "rainfall_mm": [10.0, 0.0, 5.0],
    })
    clean_df, _ = clean_hydrological_data(df, timestamp_col="timestamp")
    timestamps = clean_df["timestamp"].tolist()
    assert timestamps == sorted(timestamps)


def test_missing_value_handling_strict_gap_bounds():
    # Gap of 2 missing rows (within limit 2) should be forward-filled
    # Gap of 4 missing rows (exceeds limit 2) should NOT be fully filled
    df = pd.DataFrame({
        "timestamp": [f"2024-08-10T{i:02d}:00:00Z" for i in range(10)],
        "river_stage_m": [3.0, 3.1, np.nan, np.nan, 3.5, np.nan, np.nan, np.nan, np.nan, 4.0],
        "rainfall_mm": [0.0] * 10,
    })
    clean_df, summary = clean_hydrological_data(df, max_impute_gap_hours=2)

    # First gap (indices 2, 3) filled: 2 values imputed
    # Second gap (indices 5, 6, 7, 8): only first 2 filled, remaining 2 remain NaN
    assert summary.imputed_values_by_column["river_stage_m"] == 4
    assert clean_df["river_stage_m"].isna().sum() == 2


def test_outlier_filtering_and_rate_of_rise():
    df = pd.DataFrame({
        "timestamp": [
            "2024-08-10T01:00:00Z",
            "2024-08-10T02:00:00Z",
            "2024-08-10T03:00:00Z",
            "2024-08-10T04:00:00Z",
        ],
        # Negative stage, physically impossible jump (15m in 1h), normal stage
        "river_stage_m": [3.5, -2.0, 18.5, 3.7],
        "rainfall_mm": [5.0, 12.0, -50.0, 8.0],  # Negative rain is invalid
    })
    clean_df, summary = clean_hydrological_data(df, max_impute_gap_hours=0)

    assert "river_stage_m" in summary.outliers_flagged
    assert "rainfall_mm" in summary.outliers_flagged
    # Without forward-fill imputation, invalid outlier cells must be NaN
    assert pd.isna(clean_df.loc[1, "river_stage_m"])
    assert pd.isna(clean_df.loc[2, "rainfall_mm"])


def test_nepal_coordinate_bounds_validation():
    df = pd.DataFrame({
        "timestamp": ["2024-08-10T01:00:00Z", "2024-08-10T02:00:00Z"],
        "river_stage_m": [3.5, 3.6],
        "rainfall_mm": [0.0, 1.0],
        "latitude": [26.87, 45.00],  # 45.0 is in Europe/Russia, not Nepal!
        "longitude": [87.16, 12.00],
    })
    clean_df, summary = clean_hydrological_data(df)
    assert summary.geo_bounds_violations == 1
    assert any("Nepal boundaries" in r for r in summary.rejection_reasons)
