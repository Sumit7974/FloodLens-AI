"""Data cleaning and validation pipeline for FloodLens AI.

Enforces schema integrity, explicit UTC timestamp normalization, chronological sorting,
duplicate deduplication, geographical coordinate bounds checking for Nepal Terai,
outlier detection and handling, and strict missing value policies preventing silent
fabrication across extended missing observation intervals.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Geographic bounding constraints for Nepal
NEPAL_LAT_MIN = 26.3
NEPAL_LAT_MAX = 30.5
NEPAL_LON_MIN = 80.0
NEPAL_LON_MAX = 88.2

# Standard physical limits for sensor variables
DEFAULT_PHYSICAL_LIMITS: Dict[str, Dict[str, float]] = {
    "rainfall_mm": {"min": 0.0, "max": 300.0},
    "river_stage_m": {"min": 0.0, "max": 25.0, "max_hourly_delta": 4.0},
    "upstream_discharge_m3s": {"min": 0.0, "max": 40000.0},
    "temperature_c": {"min": -10.0, "max": 52.0},
    "relative_humidity_pct": {"min": 0.0, "max": 100.0},
}


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CleaningSummary:
    """Structured report documenting the cleaning and validation outcome."""
    input_file: str
    output_file: Optional[str]
    input_rows: int
    output_rows: int
    duplicate_rows_removed: int = 0
    duplicate_keys_removed: int = 0
    missing_values_by_column: Dict[str, int] = field(default_factory=dict)
    imputed_values_by_column: Dict[str, int] = field(default_factory=dict)
    rejected_rows_count: int = 0
    rejection_reasons: List[str] = field(default_factory=list)
    outliers_flagged: Dict[str, int] = field(default_factory=dict)
    geo_bounds_violations: int = 0
    cleaned_timestamp: str = field(default_factory=utc_now_iso)
    data_quality_grade: str = "FULL"  # FULL, PARTIAL, DEGRADED, UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def to_snake_case(name: str) -> str:
    """Convert an arbitrary string into snake_case format."""
    s = re.sub(r"[^\w\s]", "_", name.strip())
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return re.sub(r"_+", "_", s).lower().strip("_")


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names to snake_case and map common naming variations."""
    mapping: Dict[str, str] = {
        "datetime": "timestamp",
        "date_time": "timestamp",
        "time": "timestamp",
        "water_level": "river_stage_m",
        "water_level_m": "river_stage_m",
        "stage": "river_stage_m",
        "gauge_height": "river_stage_m",
        "precipitation": "rainfall_mm",
        "precip_mm": "rainfall_mm",
        "rain_mm": "rainfall_mm",
        "discharge": "upstream_discharge_m3s",
        "flow": "upstream_discharge_m3s",
        "flow_m3s": "upstream_discharge_m3s",
        "temp": "temperature_c",
        "temperature": "temperature_c",
        "humidity": "relative_humidity_pct",
        "rh": "relative_humidity_pct",
        "lat": "latitude",
        "lon": "longitude",
        "long": "longitude",
    }
    new_cols = {}
    for col in df.columns:
        sc = to_snake_case(str(col))
        new_cols[col] = mapping.get(sc, sc)
    return df.rename(columns=new_cols)


def clean_hydrological_data(
    df: pd.DataFrame,
    input_source_name: str = "in_memory",
    timestamp_col: str = "timestamp",
    station_col: Optional[str] = "station_id",
    location_col: Optional[str] = "location_id",
    max_impute_gap_hours: int = 2,
    physical_limits: Optional[Dict[str, Dict[str, float]]] = None,
) -> Tuple[pd.DataFrame, CleaningSummary]:
    """Execute complete data cleaning pipeline on a raw dataframe."""
    limits = physical_limits or DEFAULT_PHYSICAL_LIMITS
    summary = CleaningSummary(
        input_file=input_source_name,
        output_file=None,
        input_rows=len(df),
        output_rows=0,
    )

    if df.empty:
        summary.data_quality_grade = "UNAVAILABLE"
        summary.rejection_reasons.append("Empty input dataframe.")
        return df.copy(), summary

    clean_df = df.copy()

    # 1. Standardize column names
    clean_df = standardize_columns(clean_df)

    # 2. Validate and parse timestamps to UTC
    if timestamp_col not in clean_df.columns:
        summary.data_quality_grade = "UNAVAILABLE"
        summary.rejection_reasons.append(f"Required timestamp column '{timestamp_col}' missing.")
        return clean_df, summary

    try:
        parsed_ts = pd.to_datetime(clean_df[timestamp_col], format="ISO8601", errors="coerce", utc=True)
    except Exception:
        parsed_ts = pd.to_datetime(clean_df[timestamp_col], errors="coerce", utc=True)

    unparsed_mask = parsed_ts.isna() & clean_df[timestamp_col].notna()
    if unparsed_mask.any():
        fallback_ts = pd.to_datetime(clean_df.loc[unparsed_mask, timestamp_col], errors="coerce", utc=True)
        parsed_ts.loc[unparsed_mask] = fallback_ts

    invalid_ts_mask = parsed_ts.isna()
    invalid_ts_count = int(invalid_ts_mask.sum())
    if invalid_ts_count > 0:
        clean_df = clean_df[~invalid_ts_mask].copy()
        clean_df[timestamp_col] = parsed_ts[~invalid_ts_mask]
        summary.rejected_rows_count += invalid_ts_count
        summary.rejection_reasons.append(f"Rejected {invalid_ts_count} rows with unparseable timestamps.")
    else:
        clean_df[timestamp_col] = parsed_ts

    if clean_df.empty:
        summary.data_quality_grade = "UNAVAILABLE"
        summary.rejection_reasons.append("All rows contained invalid timestamps.")
        return clean_df, summary

    # 3. Deduplicate
    initial_cnt = len(clean_df)
    clean_df = clean_df.drop_duplicates()
    exact_dups = initial_cnt - len(clean_df)
    summary.duplicate_rows_removed = exact_dups

    # Deduplicate on composite key if station/location columns exist
    key_cols = [timestamp_col]
    if station_col and station_col in clean_df.columns:
        key_cols.append(station_col)
    elif location_col and location_col in clean_df.columns:
        key_cols.append(location_col)

    if len(key_cols) > 1:
        before_key_dedup = len(clean_df)
        clean_df = clean_df.drop_duplicates(subset=key_cols, keep="last")
        summary.duplicate_keys_removed = before_key_dedup - len(clean_df)

    # 4. Chronological sort
    clean_df = clean_df.sort_values(key_cols).reset_index(drop=True)

    # 5. Geographic bounds check
    if "latitude" in clean_df.columns and "longitude" in clean_df.columns:
        lats = pd.to_numeric(clean_df["latitude"], errors="coerce")
        lons = pd.to_numeric(clean_df["longitude"], errors="coerce")
        geo_invalid = (
            (lats < NEPAL_LAT_MIN)
            | (lats > NEPAL_LAT_MAX)
            | (lons < NEPAL_LON_MIN)
            | (lons > NEPAL_LON_MAX)
        )
        invalid_geo_count = int(geo_invalid.sum())
        if invalid_geo_count > 0:
            summary.geo_bounds_violations = invalid_geo_count
            summary.rejection_reasons.append(
                f"Flagged {invalid_geo_count} rows with coordinates outside Nepal boundaries."
            )

    # 6. Physical outlier and invalid sensor value filtering
    for col, bounds in limits.items():
        if col in clean_df.columns and pd.api.types.is_numeric_dtype(clean_df[col]):
            series = clean_df[col]
            min_val = bounds.get("min")
            max_val = bounds.get("max")
            outliers_mask = pd.Series(False, index=clean_df.index)

            if min_val is not None:
                outliers_mask |= (series < min_val)
            if max_val is not None:
                outliers_mask |= (series > max_val)

            # Check hourly rate of rise delta if specified
            max_delta = bounds.get("max_hourly_delta")
            if max_delta is not None and len(series) > 1:
                deltas = series.diff().abs()
                outliers_mask |= (deltas > max_delta)

            flagged_cnt = int(outliers_mask.sum())
            if flagged_cnt > 0:
                summary.outliers_flagged[col] = flagged_cnt
                # Set invalid outliers to NaN so they can be treated as missing or rejected
                clean_df.loc[outliers_mask, col] = np.nan

    # 7. Record missingness
    for col in clean_df.columns:
        null_count = int(clean_df[col].isna().sum())
        if null_count > 0:
            summary.missing_values_by_column[col] = null_count

    # 8. Missing value handling: Strict gap-bounded forward fill
    # Rules: Gaps <= max_impute_gap_hours may be forward-filled for short sensor lags.
    # Long missing gaps (> max_impute_gap_hours) must NEVER be silently fabricated.
    numeric_cols = [c for c in clean_df.columns if pd.api.types.is_numeric_dtype(clean_df[c]) and c != timestamp_col]
    for col in numeric_cols:
        initial_nulls = int(clean_df[col].isna().sum())
        if initial_nulls > 0 and max_impute_gap_hours > 0:
            # Forward fill with strict limit
            filled_series = clean_df[col].ffill(limit=max_impute_gap_hours)
            imputed_cnt = initial_nulls - int(filled_series.isna().sum())
            if imputed_cnt > 0:
                clean_df[col] = filled_series
                summary.imputed_values_by_column[col] = imputed_cnt

    summary.output_rows = len(clean_df)

    # Assess overall quality grade
    total_cells = summary.output_rows * len(clean_df.columns) if summary.output_rows > 0 else 1
    total_remaining_nulls = sum(clean_df[c].isna().sum() for c in clean_df.columns)
    null_ratio = total_remaining_nulls / total_cells

    if summary.output_rows == 0:
        summary.data_quality_grade = "UNAVAILABLE"
    elif null_ratio > 0.4 or summary.rejected_rows_count > (summary.input_rows * 0.3):
        summary.data_quality_grade = "DEGRADED"
    elif null_ratio > 0.1 or summary.imputed_values_by_column:
        summary.data_quality_grade = "PARTIAL"
    else:
        summary.data_quality_grade = "FULL"

    return clean_df, summary


def clean_file(
    input_path: Path | str,
    output_path: Optional[Path | str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, CleaningSummary]:
    """Clean a CSV file from disk and save the validated result to the designated processed path."""
    in_p = Path(input_path)
    if not in_p.exists():
        summary = CleaningSummary(
            input_file=str(in_p),
            output_file=None,
            input_rows=0,
            output_rows=0,
            data_quality_grade="UNAVAILABLE",
            rejection_reasons=[f"File not found: {in_p}"],
        )
        return pd.DataFrame(), summary

    df = pd.read_csv(in_p)
    clean_df, summary = clean_hydrological_data(
        df,
        input_source_name=str(in_p),
    )

    if output_path is not None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        clean_df.to_csv(out_p, index=False)
        summary.output_file = str(out_p)
        logger.info(f"Cleaned dataset written to {out_p} ({len(clean_df)} rows)")

    return clean_df, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and validate hydrological datasets.")
    parser.add_argument("--input", type=str, required=True, help="Input raw CSV path.")
    parser.add_argument("--output", type=str, required=True, help="Output processed CSV path.")
    parser.add_argument("--summary", type=str, default="ml/reports/cleaning_summary.json", help="Path to write JSON cleaning summary.")
    args = parser.parse_args()

    clean_df, summary = clean_file(args.input, args.output)

    summary_p = Path(args.summary)
    summary_p.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_p, "w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, indent=2)

    logger.info(f"Cleaning summary saved to {summary_p}")


if __name__ == "__main__":
    main()
