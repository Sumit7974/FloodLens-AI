"""Data audit module for FloodLens AI.

Audits historical weather, river stage, rainfall, and reservoir feeds to verify
completeness, timestamp regularity, missingness, units, coordinates, and potential
data quality anomalies for the Nepal Terai region study area.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Bounding box constraints for Nepal (WGS 84)
NEPAL_BOUNDS = {
    "lat_min": 26.3,
    "lat_max": 30.5,
    "lon_min": 80.0,
    "lon_max": 88.2,
}


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ColumnAuditResult:
    """Audit summary for a single column."""
    name: str
    dtype: str
    total_count: int
    null_count: int
    null_percentage: float
    unique_count: int
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    negative_value_count: int = 0


@dataclass
class DatasetAuditReport:
    """Comprehensive audit report for a dataset file."""
    dataset_name: str
    file_path: str
    total_rows: int
    total_columns: int
    columns: List[ColumnAuditResult] = field(default_factory=list)
    duplicate_rows_count: int = 0
    duplicate_timestamp_count: int = 0
    time_coverage_start: Optional[str] = None
    time_coverage_end: Optional[str] = None
    median_time_interval_minutes: Optional[float] = None
    irregular_intervals_count: int = 0
    geo_coordinates_valid: Optional[bool] = None
    geo_coordinate_issues: List[str] = field(default_factory=list)
    audit_timestamp: str = field(default_factory=utc_now_str)
    data_quality_status: str = "UNVERIFIED"  # FULL, PARTIAL, DEGRADED, UNAVAILABLE
    quality_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_dataframe(
    df: pd.DataFrame,
    dataset_name: str = "dataset",
    file_path: str = "in_memory",
    timestamp_col: Optional[str] = "timestamp",
    lat_col: Optional[str] = "latitude",
    lon_col: Optional[str] = "longitude",
) -> DatasetAuditReport:
    """Audit an in-memory pandas DataFrame."""
    report = DatasetAuditReport(
        dataset_name=dataset_name,
        file_path=file_path,
        total_rows=len(df),
        total_columns=len(df.columns),
    )

    if df.empty:
        report.data_quality_status = "UNAVAILABLE"
        report.quality_notes.append("Dataset is empty (0 rows).")
        return report

    # Duplicate rows check
    report.duplicate_rows_count = int(df.duplicated().sum())

    # Column level audits
    for col in df.columns:
        series = df[col]
        null_cnt = int(series.isna().sum())
        null_pct = round((null_cnt / len(df)) * 100.0, 2)
        unique_cnt = int(series.nunique(dropna=True))

        min_val = None
        max_val = None
        neg_val_cnt = 0

        if pd.api.types.is_numeric_dtype(series):
            clean_series = series.dropna()
            if not clean_series.empty:
                min_val = float(clean_series.min())
                max_val = float(clean_series.max())
                neg_val_cnt = int((clean_series < 0).sum())
        elif pd.api.types.is_datetime64_any_dtype(series):
            clean_series = series.dropna()
            if not clean_series.empty:
                min_val = str(clean_series.min())
                max_val = str(clean_series.max())

        col_audit = ColumnAuditResult(
            name=col,
            dtype=str(series.dtype),
            total_count=len(series),
            null_count=null_cnt,
            null_percentage=null_pct,
            unique_count=unique_cnt,
            min_value=min_val,
            max_value=max_val,
            negative_value_count=neg_val_cnt,
        )
        report.columns.append(col_audit)

    # Timestamp audit
    if timestamp_col and timestamp_col in df.columns:
        ts_series = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        valid_ts = ts_series.dropna()
        if not valid_ts.empty:
            report.time_coverage_start = valid_ts.min().isoformat()
            report.time_coverage_end = valid_ts.max().isoformat()
            report.duplicate_timestamp_count = int(ts_series.duplicated().sum())

            # Check intervals if sorted
            sorted_ts = valid_ts.sort_values()
            diffs = sorted_ts.diff().dropna().dt.total_seconds() / 60.0  # in minutes
            if not diffs.empty:
                report.median_time_interval_minutes = float(diffs.median())
                # Flag irregular gaps > 1.5x median or < 0.5x median
                med = report.median_time_interval_minutes
                if med > 0:
                    irregular = ((diffs > 1.5 * med) | (diffs < 0.5 * med)).sum()
                    report.irregular_intervals_count = int(irregular)
        else:
            report.quality_notes.append(f"Timestamp column '{timestamp_col}' could not be parsed to datetime.")

    # Geographic coordinate validation
    if lat_col and lon_col and lat_col in df.columns and lon_col in df.columns:
        lats = pd.to_numeric(df[lat_col], errors="coerce")
        lons = pd.to_numeric(df[lon_col], errors="coerce")
        out_of_bounds = (
            (lats < NEPAL_BOUNDS["lat_min"])
            | (lats > NEPAL_BOUNDS["lat_max"])
            | (lons < NEPAL_BOUNDS["lon_min"])
            | (lons > NEPAL_BOUNDS["lon_max"])
        )
        oob_count = int(out_of_bounds.sum())
        if oob_count > 0:
            report.geo_coordinates_valid = False
            report.geo_coordinate_issues.append(
                f"{oob_count} coordinate pairs fall outside Nepal bounds: "
                f"lat [{NEPAL_BOUNDS['lat_min']}, {NEPAL_BOUNDS['lat_max']}], "
                f"lon [{NEPAL_BOUNDS['lon_min']}, {NEPAL_BOUNDS['lon_max']}]."
            )
        else:
            report.geo_coordinates_valid = True

    # Determine composite data quality status
    max_null_pct = max((c.null_percentage for c in report.columns), default=0.0)
    if max_null_pct > 50.0 or report.duplicate_rows_count > (len(df) * 0.2):
        report.data_quality_status = "DEGRADED"
        report.quality_notes.append("Severe missingness or high duplicate rate detected.")
    elif max_null_pct > 15.0 or report.irregular_intervals_count > 5:
        report.data_quality_status = "PARTIAL"
        report.quality_notes.append("Moderate missingness or temporal irregularity observed.")
    else:
        report.data_quality_status = "FULL"

    return report


def audit_file(file_path: Path | str) -> DatasetAuditReport:
    """Audit a single CSV dataset file."""
    path = Path(file_path)
    if not path.exists():
        report = DatasetAuditReport(
            dataset_name=path.name,
            file_path=str(path),
            total_rows=0,
            total_columns=0,
            data_quality_status="UNAVAILABLE",
            quality_notes=[f"File not found: {path}"],
        )
        return report

    try:
        df = pd.read_csv(path)
        return audit_dataframe(df, dataset_name=path.stem, file_path=str(path))
    except Exception as exc:
        logger.error(f"Failed to audit file {path}: {exc}")
        return DatasetAuditReport(
            dataset_name=path.stem,
            file_path=str(path),
            total_rows=0,
            total_columns=0,
            data_quality_status="UNAVAILABLE",
            quality_notes=[f"Failed to read CSV: {exc}"],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit datasets for FloodLens AI.")
    parser.add_argument("--input-file", type=str, help="Path to single CSV file to audit.")
    parser.add_argument("--input-dir", type=str, default="ml/data/raw", help="Directory of CSV files to audit.")
    parser.add_argument("--output", type=str, default="ml/reports/data_audit_summary.json", help="Path to save JSON audit report.")
    args = parser.parse_args()

    reports: List[Dict[str, Any]] = []

    if args.input_file:
        res = audit_file(args.input_file)
        reports.append(res.to_dict())
    else:
        in_dir = Path(args.input_dir)
        if in_dir.exists():
            for p in in_dir.glob("*.csv"):
                logger.info(f"Auditing {p}...")
                res = audit_file(p)
                reports.append(res.to_dict())
        else:
            logger.warning(f"Input directory does not exist: {in_dir}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)

    logger.info(f"Audit completed. {len(reports)} datasets analyzed. Saved to {out_path}")


if __name__ == "__main__":
    main()
