"""Reproducible data-import and validation workflow for FloodLens AI.

Fetches open-access reanalysis data from two free, no-key-required APIs:

  1. Open-Meteo Historical Weather API (ERA5 reanalysis, 1940-present):
     https://archive-api.open-meteo.com/v1/archive
     Variables: hourly precipitation, temperature, relative humidity, ET0.
     License: CC BY 4.0 (non-commercial use; attribution required).

  2. Open-Meteo Flood API (GloFAS reanalysis, daily river discharge):
     https://flood-api.open-meteo.com/v1/flood
     Variable: daily river_discharge (m3/s, GloFAS-ERA5 forced).
     License: CC BY 4.0 (non-commercial use; attribution required).

Study area: Sapta Koshi River Basin — Barahachhetra / Chatara, Sunsari District,
Nepal Terai. Benchmark gauge: DHM Chatara Station 695.
Coordinates: Lat 26.87 N, Lon 87.16 E (WGS84 / EPSG:4326).

IMPORTANT LIMITATIONS:
  - ERA5 precipitation is reanalysis at ~25 km grid cell resolution. It is NOT
    a direct replacement for in-situ DHM gauge observations. Calibration against
    real gauge records is required for operational forecasting.
  - GloFAS river_discharge is a hydrological model estimate, NOT a measured river
    stage. It does NOT map directly to DHM water-level thresholds (6.0m / 7.0m).
  - These datasets are suitable as training features alongside (or as proxy for)
    missing in-situ gauge data, NOT as ground-truth labels on their own.
  - Do NOT remove the is_reanalysis=True flag from records sourced from these APIs.

Attribution (required under CC BY 4.0):
  Zippenfenig, P. (2023). Open-Meteo.com Weather API [Computer software].
  Zenodo. https://doi.org/10.5281/zenodo.7970649
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Study-area constants
# ---------------------------------------------------------------------------
CHATARA_LAT: float = 26.87
CHATARA_LON: float = 87.16
LOCATION_ID: str = "loc_barahachhetra_w2"
STATION_ID: str = "dhm_chatara_gauge_era5_proxy"
EVENT_ID: str = "evt_nepal_terai_koshi"

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
ERA5_API_URL = "https://archive-api.open-meteo.com/v1/archive"
GLOFAS_API_URL = "https://flood-api.open-meteo.com/v1/flood"

# ERA5 hourly variables to request
ERA5_HOURLY_VARS = [
    "precipitation",
    "temperature_2m",
    "relative_humidity_2m",
    "et0_fao_evapotranspiration",
]

# GloFAS daily discharge variable
GLOFAS_DAILY_VARS = ["river_discharge"]

# Physical plausibility bounds for incoming data
INGEST_PHYSICAL_LIMITS: Dict[str, Dict[str, float]] = {
    "rainfall_mm": {"min": 0.0, "max": 300.0},
    "temperature_c": {"min": -10.0, "max": 52.0},
    "relative_humidity_pct": {"min": 0.0, "max": 100.0},
    "upstream_discharge_m3s": {"min": 0.0, "max": 60000.0},
}

# Default request timeout in seconds
REQUEST_TIMEOUT_S: int = 60
# Retry settings
MAX_RETRIES: int = 3
RETRY_BACKOFF_S: float = 5.0


# ---------------------------------------------------------------------------
# Provenance dataclass
# ---------------------------------------------------------------------------
@dataclass
class IngestionProvenance:
    """Records metadata about the data-fetch operation."""
    source_era5_url: str
    source_glofas_url: str
    era5_api_params: Dict[str, Any]
    glofas_api_params: Dict[str, Any]
    fetch_timestamp_utc: str
    era5_rows_fetched: int
    glofas_rows_fetched: int
    merged_rows: int
    missing_values_by_column: Dict[str, int] = field(default_factory=dict)
    validation_warnings: List[str] = field(default_factory=list)
    data_quality_grade: str = "UNVERIFIED"
    is_reanalysis: bool = True
    license: str = "CC BY 4.0 — Attribution required. Non-commercial use only."
    citation: str = (
        "Zippenfenig, P. (2023). Open-Meteo.com Weather API [Computer software]. "
        "Zenodo. https://doi.org/10.5281/zenodo.7970649"
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# API fetch helpers
# ---------------------------------------------------------------------------
def _fetch_with_retry(
    url: str,
    params: Dict[str, Any],
    timeout: int = REQUEST_TIMEOUT_S,
    max_retries: int = MAX_RETRIES,
) -> Dict[str, Any]:
    """Fetch JSON from a URL with exponential back-off retry."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            wait = RETRY_BACKOFF_S * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {exc}. Retrying in {wait:.0f}s…")
            time.sleep(wait)
    raise RuntimeError(
        f"Failed to fetch {url} after {max_retries} attempts. Last error: {last_exc}"
    )


def fetch_era5_precipitation(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch ERA5 hourly precipitation, temperature, humidity, and ET0 from Open-Meteo.

    Returns a DataFrame with UTC-indexed timestamps and renamed schema columns.
    """
    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(ERA5_HOURLY_VARS),
        "timezone": "UTC",
    }
    logger.info(f"Fetching ERA5 data: {start_date} to {end_date} @ ({lat}, {lon})")
    data = _fetch_with_retry(ERA5_API_URL, params)

    hourly = data.get("hourly", {})
    if not hourly or not hourly.get("time"):
        raise ValueError("ERA5 API returned empty hourly data.")

    df = pd.DataFrame(hourly)
    df["timestamp"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop(columns=["time"])

    # Rename to FloodLens ML schema
    df = df.rename(columns={
        "precipitation": "rainfall_mm",
        "temperature_2m": "temperature_c",
        "relative_humidity_2m": "relative_humidity_pct",
        "et0_fao_evapotranspiration": "et0_mm",
    })

    logger.info(f"ERA5 fetch: {len(df)} hourly records ({start_date} to {end_date})")
    return df


def fetch_glofas_discharge(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch GloFAS daily river discharge from Open-Meteo Flood API.

    Returns a DataFrame with UTC date-indexed timestamps and discharge_m3s column.
    Note: This is daily resolution from GloFAS hydrological model (ERA5 forced),
    NOT in-situ gauge stage readings.
    """
    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(GLOFAS_DAILY_VARS),
    }
    logger.info(f"Fetching GloFAS discharge: {start_date} to {end_date} @ ({lat}, {lon})")
    data = _fetch_with_retry(GLOFAS_API_URL, params)

    daily = data.get("daily", {})
    if not daily or not daily.get("time"):
        raise ValueError("GloFAS Flood API returned empty daily data.")

    df = pd.DataFrame(daily)
    df["date"] = pd.to_datetime(df["time"], utc=True).dt.normalize()
    df = df.drop(columns=["time"])
    df = df.rename(columns={"river_discharge": "upstream_discharge_m3s_glofas_daily"})

    logger.info(f"GloFAS fetch: {len(df)} daily records ({start_date} to {end_date})")
    return df


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_provenance_fields(df: pd.DataFrame, warnings: List[str]) -> None:
    """Warn if expected provenance columns are missing or have unexpected values."""
    for col in ["is_reanalysis", "data_source"]:
        if col not in df.columns:
            warnings.append(f"Provenance field '{col}' is absent from dataset.")

    if "is_reanalysis" in df.columns and not df["is_reanalysis"].all():
        warnings.append(
            "Some rows have is_reanalysis=False despite using Open-Meteo API source. "
            "Verify data provenance."
        )


def validate_physical_limits(df: pd.DataFrame, warnings: List[str]) -> None:
    """Flag rows where sensor values exceed physical plausibility limits."""
    for col, bounds in INGEST_PHYSICAL_LIMITS.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        out_of_range = series.notna() & (
            (series < bounds["min"]) | (series > bounds["max"])
        )
        count = int(out_of_range.sum())
        if count > 0:
            warnings.append(
                f"Column '{col}': {count} values outside physical range "
                f"[{bounds['min']}, {bounds['max']}]."
            )


def validate_timestamps(df: pd.DataFrame, timestamp_col: str, warnings: List[str]) -> None:
    """Check timestamp completeness, UTC normalization, and monotonicity."""
    if timestamp_col not in df.columns:
        warnings.append(f"Timestamp column '{timestamp_col}' not found.")
        return

    ts = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
    null_count = int(ts.isna().sum())
    if null_count > 0:
        warnings.append(f"{null_count} timestamps could not be parsed to UTC datetime.")

    if not (ts.dropna() == ts.dropna().sort_values()).all():
        warnings.append("Timestamps are not monotonically increasing — dataset may not be sorted.")

    dup_count = int(ts.duplicated().sum())
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate timestamps detected.")

    if ts.dt.tz is None:
        warnings.append("Timestamps are timezone-naive — UTC localization required.")


def validate_location(
    lat: float,
    lon: float,
    expected_lat: float = CHATARA_LAT,
    expected_lon: float = CHATARA_LON,
    tolerance_deg: float = 0.5,
    warnings: List[str] = None,
) -> None:
    """Confirm fetched coordinates match the expected study area within tolerance."""
    if warnings is None:
        warnings = []
    if abs(lat - expected_lat) > tolerance_deg or abs(lon - expected_lon) > tolerance_deg:
        warnings.append(
            f"Fetched location ({lat}, {lon}) deviates more than {tolerance_deg}° "
            f"from expected Chatara coordinates ({expected_lat}, {expected_lon})."
        )


def validate_missingness(df: pd.DataFrame, warnings: List[str]) -> Dict[str, int]:
    """Record missing-value counts per column; warn on high missingness."""
    missing: Dict[str, int] = {}
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            missing[col] = null_count
            pct = 100.0 * null_count / len(df)
            if pct > 20.0:
                warnings.append(
                    f"Column '{col}' has {null_count} missing values ({pct:.1f}%). "
                    "Consider imputation or exclusion."
                )
    return missing


# ---------------------------------------------------------------------------
# Core merge and enrich pipeline
# ---------------------------------------------------------------------------
def merge_and_enrich(
    era5_df: pd.DataFrame,
    glofas_df: pd.DataFrame,
) -> pd.DataFrame:
    """Merge ERA5 hourly and GloFAS daily data on a common UTC timestamp.

    Strategy:
      - ERA5 is hourly; GloFAS is daily.
      - Each ERA5 hour is forward-filled with the GloFAS daily discharge
        value for that calendar date. This is a coarse proxy — it does NOT
        substitute for in-situ 10-minute or hourly gauge readings.
    """
    merged = era5_df.copy()
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    merged = merged.sort_values("timestamp").reset_index(drop=True)

    # Extract date component from hourly timestamps for join key
    merged["date"] = merged["timestamp"].dt.normalize()

    glofas_clean = glofas_df.rename(columns={
        "upstream_discharge_m3s_glofas_daily": "upstream_discharge_m3s"
    }).copy()
    glofas_clean["date"] = pd.to_datetime(glofas_clean["date"], utc=True).dt.normalize()
    glofas_clean = glofas_clean[["date", "upstream_discharge_m3s"]]

    merged = merged.merge(glofas_clean, on="date", how="left")
    merged = merged.drop(columns=["date"])

    # Add rolling rainfall accumulations
    rain_s = merged["rainfall_mm"]
    merged["rainfall_rolling_3h_mm"] = rain_s.rolling(3, min_periods=1).sum().round(2)
    merged["rainfall_rolling_6h_mm"] = rain_s.rolling(6, min_periods=1).sum().round(2)
    merged["rainfall_rolling_24h_mm"] = rain_s.rolling(24, min_periods=1).sum().round(2)

    # Rate-of-rise proxy: not available from ERA5 — placeholder for gauge integration
    # NOTE: This column will be NaN for purely ERA5-sourced data. Real river stage
    # rate-of-rise requires in-situ DHM gauge data.
    merged["river_stage_m"] = float("nan")
    merged["river_stage_rate_of_rise_m_per_h"] = float("nan")

    # Forecast precipitation proxy: shift ERA5 actual rainfall by 3h as naive forecast stand-in
    # WARNING: This is NOT a real NWP forecast — it is a backward-looking stand-in for testing.
    # Replace with ECMWF/GFS forecast API output in production.
    merged["forecast_precip_next_3h_mm"] = (
        merged["rainfall_rolling_3h_mm"].shift(-3).round(2)
    )

    # Metadata columns
    merged["timestamp"] = merged["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    merged["event_id"] = EVENT_ID
    merged["location_id"] = LOCATION_ID
    merged["station_id"] = STATION_ID
    merged["latitude"] = CHATARA_LAT
    merged["longitude"] = CHATARA_LON
    merged["is_reanalysis"] = True
    merged["is_synthetic"] = False
    merged["data_source"] = "Open-Meteo ERA5+GloFAS"
    merged["mode"] = "historical_reanalysis"

    # Season label (Northern Hemisphere monsoon in Nepal: June–September)
    ts_dt = pd.to_datetime(merged["timestamp"], utc=True)
    month = ts_dt.dt.month
    merged["season"] = month.apply(
        lambda m: "monsoon" if 6 <= m <= 9 else ("pre_monsoon" if 3 <= m <= 5 else "post_monsoon")
    )

    # Catchment saturation class based on rolling 24h rainfall
    merged["catchment_saturation_class"] = merged["rainfall_rolling_24h_mm"].apply(
        lambda r: "saturated" if r > 100 else ("wet" if r > 40 else "normal")
    )

    return merged


# ---------------------------------------------------------------------------
# Main ingestion orchestrator
# ---------------------------------------------------------------------------
def ingest_historical_data(
    start_date: str,
    end_date: str,
    output_path: Optional[Path] = None,
    provenance_path: Optional[Path] = None,
    lat: float = CHATARA_LAT,
    lon: float = CHATARA_LON,
) -> Tuple[pd.DataFrame, IngestionProvenance]:
    """Orchestrate full data-ingestion pipeline for the Chatara study area.

    Args:
        start_date: ISO date string "YYYY-MM-DD"
        end_date:   ISO date string "YYYY-MM-DD"
        output_path: Optional path to save merged CSV
        provenance_path: Optional path to save provenance JSON
        lat: Latitude of target location
        lon: Longitude of target location

    Returns:
        (merged_df, provenance) tuple
    """
    fetch_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    warnings: List[str] = []

    # --- Fetch ---
    era5_df = fetch_era5_precipitation(lat, lon, start_date, end_date)
    glofas_df = fetch_glofas_discharge(lat, lon, start_date, end_date)

    # --- Validate locations ---
    validate_location(lat, lon, warnings=warnings)

    # --- Validate timestamps ---
    validate_timestamps(era5_df, "timestamp", warnings)

    # --- Merge ---
    merged = merge_and_enrich(era5_df, glofas_df)

    # --- Validate after merge ---
    validate_physical_limits(merged, warnings)
    missing_values = validate_missingness(merged, warnings)
    validate_provenance_fields(merged, warnings)

    # --- Grade data quality ---
    critical_cols = ["rainfall_mm", "temperature_c", "relative_humidity_pct"]
    critical_nulls = sum(missing_values.get(c, 0) for c in critical_cols)
    total_cells = len(merged) * len(merged.columns)
    overall_null_pct = 100.0 * sum(missing_values.values()) / (total_cells or 1)

    if overall_null_pct > 40 or critical_nulls > len(merged) * 0.3:
        quality_grade = "DEGRADED"
    elif overall_null_pct > 10 or warnings:
        quality_grade = "PARTIAL"
    else:
        quality_grade = "FULL"

    # Note: river_stage_m is always NaN from this source — mark as PARTIAL minimum
    if "river_stage_m" in merged.columns and merged["river_stage_m"].isna().all():
        if quality_grade == "FULL":
            quality_grade = "PARTIAL"
        warnings.append(
            "river_stage_m is entirely NaN (not available from ERA5/GloFAS). "
            "DHM in-situ gauge data is required for river stage labeling. "
            "This dataset can train rainfall and discharge features only."
        )

    era5_params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join(ERA5_HOURLY_VARS),
        "timezone": "UTC",
    }
    glofas_params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(GLOFAS_DAILY_VARS),
    }

    provenance = IngestionProvenance(
        source_era5_url=ERA5_API_URL,
        source_glofas_url=GLOFAS_API_URL,
        era5_api_params=era5_params,
        glofas_api_params=glofas_params,
        fetch_timestamp_utc=fetch_ts,
        era5_rows_fetched=len(era5_df),
        glofas_rows_fetched=len(glofas_df),
        merged_rows=len(merged),
        missing_values_by_column=missing_values,
        validation_warnings=warnings,
        data_quality_grade=quality_grade,
    )

    # --- Persist ---
    if output_path is not None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(out_p, index=False)
        logger.info(f"Merged dataset saved to {out_p} ({len(merged)} rows)")

    if provenance_path is not None:
        prov_p = Path(provenance_path)
        prov_p.parent.mkdir(parents=True, exist_ok=True)
        with open(prov_p, "w", encoding="utf-8") as f:
            json.dump(provenance.to_dict(), f, indent=2)
        logger.info(f"Provenance record saved to {prov_p}")

    logger.info(
        f"Ingestion complete: {len(merged)} rows, quality={quality_grade}, "
        f"warnings={len(warnings)}"
    )
    return merged, provenance


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch ERA5 precipitation and GloFAS discharge from Open-Meteo for "
            "the FloodLens AI Chatara study area."
        )
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2017-06-01",
        help="Start date YYYY-MM-DD (default: 2017-06-01 — Nepal monsoon onset)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2017-09-30",
        help="End date YYYY-MM-DD (default: 2017-09-30 — monsoon withdrawal)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="ml/data/raw/era5_glofas_chatara.csv",
        help="Output path for merged CSV",
    )
    parser.add_argument(
        "--provenance",
        type=str,
        default="ml/reports/ingestion_provenance.json",
        help="Output path for provenance JSON",
    )
    parser.add_argument("--lat", type=float, default=CHATARA_LAT)
    parser.add_argument("--lon", type=float, default=CHATARA_LON)
    args = parser.parse_args()

    df, prov = ingest_historical_data(
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=Path(args.output),
        provenance_path=Path(args.provenance),
        lat=args.lat,
        lon=args.lon,
    )

    logger.info(
        f"\n{'='*60}\n"
        f"INGESTION SUMMARY\n"
        f"  Date range:     {args.start_date} to {args.end_date}\n"
        f"  Total rows:     {len(df)}\n"
        f"  Quality grade:  {prov.data_quality_grade}\n"
        f"  Warnings:       {len(prov.validation_warnings)}\n"
        f"  is_reanalysis:  {prov.is_reanalysis}\n"
        f"  river_stage_m:  {'UNAVAILABLE (NaN) — in-situ DHM gauge required' if df['river_stage_m'].isna().all() else 'PRESENT'}\n"
        f"{'='*60}"
    )
    for w in prov.validation_warnings:
        logger.warning(f"  [WARN] {w}")


if __name__ == "__main__":
    main()
