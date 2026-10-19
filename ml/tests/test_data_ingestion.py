"""Tests for data-ingestion validation, reanalysis labeling, and feature engineering.

Covers:
  - Timestamp validation and UTC normalization
  - Physical plausibility limits checking
  - Location coordinate validation
  - Missing-value detection and reporting
  - Provenance field enforcement
  - Reanalysis labeling correctness (rainfall-dominant strategy)
  - Multi-horizon leakage prevention on reanalysis data
  - GloFAS discharge percentile threshold computation
  - Feature engineering (rolling rainfall, catchment class)
  - Class imbalance documentation
"""
from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from ml.src.data_ingestion import (
    CHATARA_LAT,
    CHATARA_LON,
    INGEST_PHYSICAL_LIMITS,
    validate_location,
    validate_missingness,
    validate_physical_limits,
    validate_provenance_fields,
    validate_timestamps,
    merge_and_enrich,
)
from ml.src.reanalysis_labeling import (
    RAIN24H_CRITICAL_MM,
    RAIN24H_HIGH_MM,
    RAIN24H_MODERATE_MM,
    RISK_LABEL_TO_ID,
    assign_reanalysis_risk_label,
    build_reanalysis_labels,
    compute_discharge_percentile_thresholds,
    get_labeling_strategy_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def minimal_era5_df() -> pd.DataFrame:
    """Minimal ERA5-shaped DataFrame with 48 hourly rows."""
    timestamps = pd.date_range("2017-08-10T00:00:00Z", periods=48, freq="h", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rainfall_mm": np.random.default_rng(42).exponential(2.0, 48).round(1),
        "temperature_c": np.full(48, 28.5),
        "relative_humidity_pct": np.full(48, 82.0),
        "et0_mm": np.full(48, 0.5),
    })


@pytest.fixture
def minimal_glofas_df() -> pd.DataFrame:
    """Minimal GloFAS-shaped DataFrame with 2 daily discharge rows."""
    return pd.DataFrame({
        "date": pd.to_datetime(["2017-08-10T00:00:00Z", "2017-08-11T00:00:00Z"], utc=True),
        "upstream_discharge_m3s": [4.2, 9.8],
    })


@pytest.fixture
def reanalysis_df() -> pd.DataFrame:
    """Reanalysis DataFrame with known rainfall values covering all 4 risk tiers."""
    n = 200
    rng = np.random.default_rng(7)
    timestamps = pd.date_range("2017-08-01T00:00:00Z", periods=n, freq="h", tz="UTC")

    # Construct rainfall to produce all 4 risk classes
    rain = np.concatenate([
        np.zeros(100),                         # low
        rng.uniform(25, 99, 40),              # moderate
        rng.uniform(100, 149, 40),            # high
        np.full(20, 155.0),                   # critical
    ])

    discharge = np.concatenate([
        np.full(100, 2.0),                     # low
        np.full(40, 6.0),                      # moderate
        np.full(40, 12.0),                     # high
        np.full(20, 25.0),                     # critical
    ])

    return pd.DataFrame({
        "timestamp": timestamps.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rainfall_mm": rain,
        "rainfall_rolling_3h_mm": rain,
        "rainfall_rolling_6h_mm": rain,
        "rainfall_rolling_24h_mm": rain,
        "upstream_discharge_m3s": discharge,
        "temperature_c": np.full(n, 27.0),
        "relative_humidity_pct": np.full(n, 80.0),
        "river_stage_m": np.full(n, np.nan),
        "river_stage_rate_of_rise_m_per_h": np.full(n, np.nan),
        "forecast_precip_next_3h_mm": rain,
        "season": ["monsoon"] * n,
        "catchment_saturation_class": ["normal"] * n,
        "is_reanalysis": [True] * n,
        "is_synthetic": [False] * n,
        "data_source": ["Open-Meteo ERA5+GloFAS"] * n,
        "mode": ["historical_reanalysis"] * n,
    })


# ---------------------------------------------------------------------------
# DATA INGESTION VALIDATION TESTS
# ---------------------------------------------------------------------------
class TestTimestampValidation:
    def test_valid_utc_timestamps_produce_no_warnings(self):
        df = pd.DataFrame({
            "timestamp": pd.date_range("2017-08-01", periods=5, freq="h", tz="UTC")
        })
        warnings: list = []
        validate_timestamps(df, "timestamp", warnings)
        assert len(warnings) == 0

    def test_missing_timestamp_column_raises_warning(self):
        df = pd.DataFrame({"value": [1, 2, 3]})
        warnings: list = []
        validate_timestamps(df, "timestamp", warnings)
        assert any("Timestamp column" in w for w in warnings)

    def test_string_timestamps_parsed_correctly(self):
        df = pd.DataFrame({
            "timestamp": ["2017-08-01T00:00:00Z", "2017-08-01T01:00:00Z"]
        })
        warnings: list = []
        validate_timestamps(df, "timestamp", warnings)
        # No warning about unparseable timestamps if all valid ISO strings
        assert not any("could not be parsed" in w for w in warnings)

    def test_duplicate_timestamps_detected(self):
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(
                ["2017-08-01T00:00:00Z", "2017-08-01T00:00:00Z", "2017-08-01T01:00:00Z"],
                utc=True,
            )
        })
        warnings: list = []
        validate_timestamps(df, "timestamp", warnings)
        assert any("duplicate" in w.lower() for w in warnings)


class TestPhysicalLimitsValidation:
    def test_valid_values_produce_no_warnings(self):
        df = pd.DataFrame({
            "rainfall_mm": [0.0, 5.0, 25.0, 100.0],
            "temperature_c": [20.0, 25.0, 30.0, 35.0],
            "relative_humidity_pct": [60.0, 70.0, 80.0, 90.0],
            "upstream_discharge_m3s": [100.0, 500.0, 1000.0, 5000.0],
        })
        warnings: list = []
        validate_physical_limits(df, warnings)
        assert len(warnings) == 0

    def test_negative_rainfall_flagged(self):
        df = pd.DataFrame({"rainfall_mm": [-1.0, 5.0, 10.0]})
        warnings: list = []
        validate_physical_limits(df, warnings)
        assert any("rainfall_mm" in w for w in warnings)

    def test_humidity_over_100_flagged(self):
        df = pd.DataFrame({"relative_humidity_pct": [80.0, 101.5, 90.0]})
        warnings: list = []
        validate_physical_limits(df, warnings)
        assert any("relative_humidity_pct" in w for w in warnings)

    def test_temperature_above_limit_flagged(self):
        df = pd.DataFrame({"temperature_c": [30.0, 55.0]})  # 55 > 52 limit
        warnings: list = []
        validate_physical_limits(df, warnings)
        assert any("temperature_c" in w for w in warnings)

    def test_excess_discharge_flagged(self):
        df = pd.DataFrame({"upstream_discharge_m3s": [1000.0, 70000.0]})  # 70000 > 60000
        warnings: list = []
        validate_physical_limits(df, warnings)
        assert any("upstream_discharge_m3s" in w for w in warnings)


class TestLocationValidation:
    def test_exact_chatara_coordinates_no_warning(self):
        warnings: list = []
        validate_location(CHATARA_LAT, CHATARA_LON, warnings=warnings)
        assert len(warnings) == 0

    def test_offset_within_tolerance_no_warning(self):
        warnings: list = []
        validate_location(CHATARA_LAT + 0.3, CHATARA_LON + 0.3, warnings=warnings)
        assert len(warnings) == 0

    def test_large_offset_raises_warning(self):
        warnings: list = []
        validate_location(28.0, 85.0, warnings=warnings)  # >0.5° off Chatara
        assert any("deviates" in w for w in warnings)


class TestMissingnessValidation:
    def test_no_missing_values_returns_empty_dict(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        warnings: list = []
        result = validate_missingness(df, warnings)
        assert result == {}

    def test_missing_values_counted_per_column(self):
        df = pd.DataFrame({
            "a": [1.0, None, 3.0],
            "b": [4.0, 5.0, None],
        })
        warnings: list = []
        result = validate_missingness(df, warnings)
        assert result.get("a") == 1
        assert result.get("b") == 1

    def test_high_missingness_triggers_warning(self):
        df = pd.DataFrame({"a": [None] * 10 + [1.0] * 5})  # 67% missing
        warnings: list = []
        validate_missingness(df, warnings)
        assert any("missing values" in w.lower() for w in warnings)


class TestProvenanceValidation:
    def test_valid_provenance_columns_no_warnings(self):
        df = pd.DataFrame({
            "is_reanalysis": [True, True],
            "data_source": ["Open-Meteo ERA5+GloFAS", "Open-Meteo ERA5+GloFAS"],
        })
        warnings: list = []
        validate_provenance_fields(df, warnings)
        assert len(warnings) == 0

    def test_missing_is_reanalysis_column_warns(self):
        df = pd.DataFrame({"data_source": ["Open-Meteo ERA5+GloFAS"]})
        warnings: list = []
        validate_provenance_fields(df, warnings)
        assert any("is_reanalysis" in w for w in warnings)

    def test_is_reanalysis_false_warns(self):
        df = pd.DataFrame({
            "is_reanalysis": [False, True],
            "data_source": ["Open-Meteo ERA5+GloFAS"] * 2,
        })
        warnings: list = []
        validate_provenance_fields(df, warnings)
        assert any("is_reanalysis=False" in w for w in warnings)


# ---------------------------------------------------------------------------
# FEATURE ENGINEERING TESTS
# ---------------------------------------------------------------------------
class TestMergeAndEnrich:
    def test_merge_produces_rolling_columns(self, minimal_era5_df, minimal_glofas_df):
        merged = merge_and_enrich(minimal_era5_df, minimal_glofas_df)
        assert "rainfall_rolling_3h_mm" in merged.columns
        assert "rainfall_rolling_6h_mm" in merged.columns
        assert "rainfall_rolling_24h_mm" in merged.columns

    def test_merge_produces_provenance_columns(self, minimal_era5_df, minimal_glofas_df):
        merged = merge_and_enrich(minimal_era5_df, minimal_glofas_df)
        assert "is_reanalysis" in merged.columns
        assert merged["is_reanalysis"].all()
        assert "is_synthetic" in merged.columns
        assert not merged["is_synthetic"].any()

    def test_season_assignment(self, minimal_era5_df, minimal_glofas_df):
        merged = merge_and_enrich(minimal_era5_df, minimal_glofas_df)
        # August data should be 'monsoon'
        assert merged["season"].iloc[0] == "monsoon"

    def test_rolling_rainfall_non_negative(self, minimal_era5_df, minimal_glofas_df):
        merged = merge_and_enrich(minimal_era5_df, minimal_glofas_df)
        assert (merged["rainfall_rolling_24h_mm"] >= 0).all()

    def test_catchment_saturation_class_values(self, minimal_era5_df, minimal_glofas_df):
        merged = merge_and_enrich(minimal_era5_df, minimal_glofas_df)
        valid_classes = {"saturated", "wet", "normal"}
        assert set(merged["catchment_saturation_class"].unique()).issubset(valid_classes)


# ---------------------------------------------------------------------------
# REANALYSIS LABELING TESTS
# ---------------------------------------------------------------------------
class TestDischargePercentileThresholds:
    def test_percentile_ordering(self):
        series = pd.Series(np.arange(100, dtype=float))
        pct = compute_discharge_percentile_thresholds(series)
        assert pct["p75"] <= pct["p90"] <= pct["p95"]

    def test_empty_series_returns_zero_thresholds(self):
        pct = compute_discharge_percentile_thresholds(pd.Series(dtype=float))
        assert pct["p90"] == 0.0 and pct["p95"] == 0.0

    def test_all_nan_series_returns_zero_thresholds(self):
        pct = compute_discharge_percentile_thresholds(pd.Series([float("nan")] * 10))
        assert pct["p90"] == 0.0


class TestAssignReanalysisRiskLabel:
    def test_critical_label_at_extreme_rain(self):
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=RAIN24H_CRITICAL_MM + 10,
            upstream_discharge_m3s=1.0,
            discharge_p90=5.0,
            discharge_p95=10.0,
        )
        assert label == "critical"

    def test_high_label_at_100mm_rain(self):
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=RAIN24H_HIGH_MM + 5,
            upstream_discharge_m3s=1.0,
            discharge_p90=5.0,
            discharge_p95=10.0,
        )
        assert label == "high"

    def test_moderate_label_at_25mm_rain(self):
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=RAIN24H_MODERATE_MM + 5,
            upstream_discharge_m3s=1.0,
            discharge_p90=5.0,
            discharge_p95=10.0,
        )
        assert label == "moderate"

    def test_low_label_at_dry_conditions(self):
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=5.0,
            upstream_discharge_m3s=1.0,
            discharge_p90=5.0,
            discharge_p95=10.0,
        )
        assert label == "low"

    def test_high_discharge_with_moderate_rain_gives_high(self):
        # discharge >= p90 AND rain >= moderate threshold => high
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=RAIN24H_MODERATE_MM + 5,
            upstream_discharge_m3s=12.0,  # above p90=10.0
            discharge_p90=10.0,
            discharge_p95=15.0,
        )
        assert label == "high"

    def test_extreme_discharge_with_extreme_rain_gives_critical(self):
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=RAIN24H_HIGH_MM + 10,  # 110mm
            upstream_discharge_m3s=18.0,  # above p95=15.0
            discharge_p90=10.0,
            discharge_p95=15.0,
        )
        assert label == "critical"

    def test_intense_hourly_rain_triggers_high(self):
        # 15mm in 1h and 30mm in 3h => high
        label = assign_reanalysis_risk_label(
            rainfall_rolling_24h_mm=10.0,
            upstream_discharge_m3s=1.0,
            discharge_p90=5.0,
            discharge_p95=10.0,
            rainfall_mm=15.0,
            rainfall_rolling_3h_mm=30.0,
        )
        assert label == "high"

    def test_risk_label_to_id_complete(self):
        """All four risk labels must have numeric codes 0-3."""
        assert RISK_LABEL_TO_ID["low"] == 0
        assert RISK_LABEL_TO_ID["moderate"] == 1
        assert RISK_LABEL_TO_ID["high"] == 2
        assert RISK_LABEL_TO_ID["critical"] == 3


class TestBuildReanalysisLabels:
    def test_all_four_classes_generated(self, reanalysis_df):
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1, 3, 6])
        unique_labels = set(labeled["instantaneous_risk_label"].dropna())
        assert "low" in unique_labels
        assert "moderate" in unique_labels
        assert "high" in unique_labels
        assert "critical" in unique_labels

    def test_horizon_target_columns_present(self, reanalysis_df):
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1, 3, 6])
        for h in [1, 3, 6]:
            assert f"risk_label_+{h}h" in labeled.columns
            assert f"target_+{h}h" in labeled.columns

    def test_trailing_horizon_rows_are_nan(self, reanalysis_df):
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1, 3, 6])
        n = len(labeled)
        # Last row cannot have +1h target
        assert pd.isna(labeled.loc[n - 1, "risk_label_+1h"])
        # Row n-3 cannot have +3h target
        assert pd.isna(labeled.loc[n - 3, "risk_label_+3h"])
        # Row n-6 cannot have +6h target
        assert pd.isna(labeled.loc[n - 6, "risk_label_+6h"])

    def test_leakage_prevention_instant_label_uses_current_row_only(self, reanalysis_df):
        """Features at row t must not include any future observations."""
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1])
        # Verify row 0's rainfall feature is the row 0 rainfall (not row 1)
        assert labeled.loc[0, "rainfall_rolling_24h_mm"] == reanalysis_df.loc[0, "rainfall_rolling_24h_mm"]

    def test_is_reanalysis_label_column_set_true(self, reanalysis_df):
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1])
        assert labeled["is_reanalysis_label"].all()

    def test_labeling_strategy_column_documented(self, reanalysis_df):
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1])
        assert "labeling_strategy" in labeled.columns
        assert (labeled["labeling_strategy"] == "rainfall_dominant_era5_glofas").all()

    def test_percentiles_returned_as_dict(self, reanalysis_df):
        _, pctiles = build_reanalysis_labels(reanalysis_df, horizons=[1])
        assert "p75" in pctiles
        assert "p90" in pctiles
        assert "p95" in pctiles
        assert pctiles["p75"] <= pctiles["p90"] <= pctiles["p95"]

    def test_class_distribution_documented(self, reanalysis_df):
        """Verify that all 4 classes are present and imbalance is predictable."""
        labeled, _ = build_reanalysis_labels(reanalysis_df, horizons=[1])
        dist = labeled["instantaneous_risk_label"].value_counts().to_dict()
        assert dist.get("low", 0) >= dist.get("critical", 0), (
            "Expected low > critical (natural imbalance in monsoon data)"
        )


class TestLabelingStrategySummary:
    def test_summary_contains_required_keys(self):
        summary = get_labeling_strategy_summary()
        for key in ["strategy_name", "risk_tiers", "limitations", "data_status", "horizons_hours"]:
            assert key in summary

    def test_summary_marks_data_as_provisional(self):
        summary = get_labeling_strategy_summary()
        assert "PROVISIONAL" in summary["data_status"]

    def test_summary_lists_leakage_prevention_rules(self):
        summary = get_labeling_strategy_summary()
        assert len(summary["leakage_prevention"]) >= 3

    def test_summary_includes_class_imbalance_mitigation(self):
        summary = get_labeling_strategy_summary()
        assert len(summary["class_imbalance_mitigation"]) >= 2
