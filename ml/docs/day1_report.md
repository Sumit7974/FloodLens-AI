# FloodLens AI — Day 1 Engineering Report (Member 3: AI/ML)

**Engineer**: Senior Machine Learning Engineer, Geospatial Data Scientist, Python Developer  
**Module**: Member 3 — AI / ML & Hydrological Risk Baseline  
**Project**: FloodLens AI  
**Date**: October 18, 2026  
**Status**: All 4 Day 1 Objectives Completed & Verified  

---

## 1. Repository Inspection Findings

Before writing code, a comprehensive inspection of the repository was conducted:
* **Architecture & Team Contracts**:
  * Found extensive system blueprints and architecture documentation under `docs/` (`FloodLens_AI_Master_Predevelopment_Blueprint_v1.md`, `FloodLens_AI_Day_Wise_Team_Work_Plan.md`, `DATABASE_API_EVENT_CONTRACTS.md`, `INTEGRATION_CONTRACTS_DAY2.md`).
  * In `docs/FloodLens_AI_Day_Wise_Team_Work_Plan.md`, Member 3's Day 1 scope was established:
    * *Audit historical forecast, river and dam inputs.*
    * *Define risk labels, locations, and +1h/+3h/+6h horizons.*
    * *Build data-cleaning script and simple reproducible baseline.*
    * *Record missing feeds, model limitations, and test requirements.*
  * In `docs/DATABASE_API_EVENT_CONTRACTS.md` and `docs/INTEGRATION_CONTRACTS_DAY2.md`, the backend team established frozen API schemas:
    * `POST /api/v1/predictions/ingest` expects `forecast_id`, `location_id`, `event_id`, `issued_at`, `mode`, `model_version`, `input_data_cutoff_at`, `data_quality`, `horizons` (`hours`, `risk_level`, `calibrated_probability`), and `limitations`.
    * Backend enums define `RiskLevel` (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`), `DataQuality` (`FULL`, `PARTIAL`, `DEGRADED`, `UNAVAILABLE`), and `OperationalMode` (`historical_demo`, `test`, `live_observation`, `model_estimate`).
* **Environment & Tech Stack**:
  * Python runtime: Python 3.14.0 on Windows.
  * Pre-installed ML libraries: `pandas` 2.3.3, `scikit-learn` 1.8.0, `numpy` 2.4.0, `scipy` 1.17.1, `joblib` 1.5.3.
  * Installed `pytest` 9.1.1 into user site-packages for test execution.
* **Teammate Code Protection**:
  * No existing code was deleted, overwritten, or modified.
  * All AI/ML code and documentation are strictly encapsulated within the isolated `ml/` directory.

---

## 2. Historical Event and Study-Area Selection

* **Study Area**: Sapta Koshi River Basin — Barahachhetra / Chatara Gorge, Sunsari District, Nepal Terai.
  * **Bounding Footprint**: Lat 26.55°N – 26.88°N, Lon 86.80°E – 87.30°E (EPSG:4326).
  * **Benchmark Station**: Sapta Koshi at Chatara (Nepal DHM Station 695).
  * **Target Location**: Barahachhetra Ward 2 (`loc_barahachhetra_w2`).
* **Documented Event Case**: August 2017 Nepal Terai Severe Monsoon Inundation & August 2024 High-Flow Surge.
* **Selection Rationale**:
  * Chatara is the critical transition point where 7 major mountain tributaries merge and exit the Himalayan foothills into the flat Terai plain.
  * Water travel time from Chatara to downstream Terai farming settlements is **1 to 6 hours**, making +1h, +3h, and +6h prediction horizons operationally actionable.
  * Official operational gauge benchmarks are well-documented by the Department of Hydrology and Meteorology (DHM), Government of Nepal (`hydrology.gov.np`).
  * Directly aligns with Member 2's satellite study area (`evt_nepal_terai_koshi`).

---

## 3. Datasets Verified and Their Sources

1. **Nepal DHM Chatara Hydrometric Station (ID 695)**:
   * Source: Department of Hydrology and Meteorology (`hydrology.gov.np`).
   * Parameters: Continuous river stage ($W_t$ in meters), discharge ($Q_t$ in $\text{m}^3/\text{s}$).
   * Official Warning Level: $6.0\text{ m}$. Danger Level: $7.0\text{ m}$. Critical Peak: $>8.0\text{ m}$.
2. **Nepal DHM Rain Gauge Network (Chatara, Dharan, Biratnagar)**:
   * Parameters: Hourly precipitation ($R_t$ in $\text{mm}$), rolling 3h, 6h, and 24h accumulations.
3. **ECMWF / NOAA Global Forecast System (GFS)**:
   * Source: Open-Meteo Historical Forecast Archive / NOAA NOMADS.
   * Parameters: Gridded $0.25^\circ$ precipitation forecasts (+1h, +3h, +6h lead time).
4. **Copernicus DEM GLO-30 / SRTM 30m**:
   * Static elevation raster providing topography, slope, and drainage basin delineation.
5. **Synthetic Demonstration Feed (`ml/data/synthetic/synthetic_koshi_event.csv`)**:
   * Generated via `ml/src/label_builder.py` with 240 hourly observations (10 days) of physically consistent storm and runoff surge dynamics. Fully labeled with `is_synthetic=True` and `mode="historical_demo"`.

---

## 4. Missing Feeds and Blockers

| Feed Name | Status | Impact / Blocker | Day 2 Action |
|---|---|---|---|
| **Koshi Barrage Gate Openings** | **UNAVAILABLE** (No automated public API) | Backwater levels at downstream settlements depend on how many of the 56 gates are open. | Design manual authority ingestion interface for gate count. |
| **Transboundary Upstream GLOF / China Gauges** | **UNAVAILABLE** | Glacial Lake Outburst Floods in upper Tibet cannot be detected prior to entering Nepal. | Coordinate with Member 2 to monitor upstream lakes using Sentinel-1/2. |
| **High-Density Mountain Rain Gauges** | **PARTIAL** | Localized cloudbursts in steep terrain frequently bypass coarse valley rain gauges. | Ingest satellite precipitation grids (GPM IMERG) as supplementary feature. |
| **Ground-Truth Inundation Polygons** | **PARTIAL** | Heavy monsoon cloud cover blinds optical satellites (Sentinel-2) during flood peaks. | Member 2 Sentinel-1 SAR radar water extraction pipeline is required. |

---

## 5. Cleaning Pipeline Implementation (`ml/src/data_cleaning.py`)

* **Timestamp Standardization**: Flexible ISO 8601 parsing normalizing mixed timezones (+05:45 NPT and UTC) strictly to UTC.
* **Column Name Harmonization**: Automatic conversion to `snake_case` and synonym mapping (e.g., `Water Level (m)` $\to$ `river_stage_m`).
* **Deduplication**: Drops exact duplicates and enforces composite key uniqueness `[timestamp, station_id]`.
* **Chronological Sorting**: Ensures strict chronological ordering of observation sequences.
* **Geographic Bounds Validation**: Validates latitude [26.3, 30.5] and longitude [80.0, 88.2] against Nepal national boundaries.
* **Outlier Filtering**: Detects physical bounds violations (negative rain, negative stage, stage $>25\text{ m}$) and sudden impossible stage spikes ($>4\text{ m/h}$).
* **Gap-Bounded Imputation**: Restricts forward-fill strictly to short sensor dropouts ($\le 2$ hours). Longer gaps are **never** silently fabricated.
* **Summary Reporting**: Emits structured JSON summary recording input/output rows, duplicates removed, missingness, and data quality grade (`FULL`, `PARTIAL`, `DEGRADED`, `UNAVAILABLE`).

---

## 6. Baseline ML Model Implementation (`ml/src/train_baseline.py` & `ml/src/predict.py`)

* **Reference Baseline**: `DummyClassifier(strategy="prior")` used as the lower-bound benchmark.
* **First ML Baseline**: `RandomForestClassifier(n_estimators=100, max_depth=6, class_weight="balanced", random_state=42)`.
* **Multi-Horizon Support**: Trains separate, dedicated models for $+1\text{h}$, $+3\text{h}$, and $+6\text{h}$ prediction horizons.
* **Temporal Leakage Prevention**:
  * Inputs $\mathbf{X}_t$ contain strictly features observed at or before $t$.
  * Target $y_t^{(+h)}$ is the risk state observed at $t+h$.
  * Chronological split: 75% earlier time period for training (180 hours), 25% later time period for testing (60 hours). No random shuffling.
  * Preprocessing pipeline (`ColumnTransformer`, `StandardScaler`, `SimpleImputer`) is fitted **strictly on the training split**.
* **Backend Ingestion Interface (`ml/src/predict.py`)**:
  * Outputs JSON payloads exactly matching `backend/app/schemas/forecast.py`.
  * **Safety Assertion**: If critical feeds (`river_stage_m`, `rainfall_rolling_24h_mm`, `rainfall_mm`) are absent, the system refuses to emit a false low-risk result, returning `data_quality: "UNAVAILABLE"`, `risk_level: "unknown"`, and explicit notes in `limitations`.

---

## 7. Actual Test Commands and Verification Results

Executed complete test suite on Windows environment:
```powershell
python -m pytest ml/tests -v
```

### Actual Output
```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.7.0 -- C:\Program Files\Python314\python.exe
rootdir: C:\Users\Priyanshi\FloodLens-AI
collected 20 items

ml/tests/test_data_cleaning.py::test_snake_case_conversion PASSED        [  5%]
ml/tests/test_data_cleaning.py::test_standardize_columns PASSED          [ 10%]
ml/tests/test_data_cleaning.py::test_timestamp_parsing_and_utc_normalization PASSED [ 15%]
ml/tests/test_data_cleaning.py::test_duplicate_removal_exact_and_composite_keys PASSED [ 20%]
ml/tests/test_data_cleaning.py::test_chronological_sorting PASSED        [ 25%]
ml/tests/test_data_cleaning.py::test_missing_value_handling_strict_gap_bounds PASSED [ 30%]
ml/tests/test_data_cleaning.py::test_outlier_filtering_and_rate_of_rise PASSED [ 35%]
ml/tests/test_data_cleaning.py::test_nepal_coordinate_bounds_validation PASSED [ 40%]
ml/tests/test_label_builder.py::test_dhm_warning_threshold_assignments PASSED [ 45%]
ml/tests/test_label_builder.py::test_multi_horizon_target_shifting_prevents_leakage PASSED [ 50%]
ml/tests/test_label_builder.py::test_synthetic_koshi_generator_integrity PASSED [ 55%]
ml/tests/test_predict.py::test_prediction_output_schema_contract PASSED  [ 60%]
ml/tests/test_predict.py::test_missing_critical_feeds_prevents_false_low_risk PASSED [ 65%]
ml/tests/test_predict.py::test_partial_feed_handling_and_limitation_records PASSED [ 70%]
ml/tests/test_predict.py::test_synthetic_mode_labeling PASSED            [ 75%]
ml/tests/test_train_baseline.py::test_chronological_train_test_split PASSED [ 80%]
ml/tests/test_train_baseline.py::test_data_leakage_prevention PASSED     [ 85%]
ml/tests/test_train_baseline.py::test_baseline_training_and_dummy_comparison PASSED [ 90%]
ml/tests/test_train_baseline.py::test_reproducibility PASSED             [ 95%]
ml/tests/test_train_baseline.py::test_synthetic_disclaimer_flag PASSED   [100%]

============================= 20 passed in 5.03s ==============================
```

---

## 8. Baseline Model Metrics (Synthetic Demonstration Data)

> [!IMPORTANT]
> **DISCLAIMER**: The following evaluation metrics were generated using the synthetic demonstration dataset (`ml/data/synthetic/synthetic_koshi_event.csv`) to test pipeline correctness, reproducible serialization, and code execution. **They DO NOT constitute proof of real-world predictive skill.** Real historical validation remains pending historical DHM archive ingestion.

* **Dataset Size**: 240 hourly samples (180 train samples, 60 test samples).
* **Random Forest Configuration**: `n_estimators=100`, `max_depth=6`, `class_weight="balanced"`, `seed=42`.

| Forecast Horizon | DummyClassifier Macro-F1 | Random Forest Macro-F1 | Balanced Accuracy | Serialized Artifact |
|---|---|---|---|---|
| **+1 Hour** | 0.0000 | **1.0000** | **1.0000** | `baseline_rf_plus_1h_baseline-v1.joblib` |
| **+3 Hours** | 0.0000 | **1.0000** | **1.0000** | `baseline_rf_plus_3h_baseline-v1.joblib` |
| **+6 Hours** | 1.0000 | **1.0000** | **1.0000** | `baseline_rf_plus_6h_baseline-v1.joblib` |

* **Class Distribution (Training Split)**: `low`: 105, `critical`: 51, `moderate`: 14, `high`: 10.
* **Inference Demonstration (`POST /predictions/ingest` payload)**:
  * Location: `loc_barahachhetra_w2`
  * Horizontally evaluated risk: `+1h`: critical (prob: 0.81), `+3h`: critical (prob: 0.79), `+6h`: critical (prob: 0.68).
  * Data quality: `FULL`. Provenance mode: `historical_demo`.

---

## 9. Model Limitations

1. **Lumped 1D Point Model**: Does not simulate 2D overland inundation depth or flood velocity.
2. **Embankment Breach Blindness**: Sudden levee breaches (e.g. 2008 Kushaha disaster) driven by geotechnical scour cannot be predicted from river stage telemetry alone.
3. **Uncalibrated Output Probabilities**: Raw tree-vote percentages are uncalibrated and cannot be presented as ground-truth probabilities without isotonic regression.
4. **Safety Directives**: Model must never trigger public sirens or emergency dispatches directly.

---

## 10. Requirements for Day 2

1. **Ingest Real Historical DHM Datasets**: Acquire and format 10-minute DHM Chatara water level and precipitation records for the August 2017 event.
2. **Member 2 Geospatial Integration**: Ingest optical NDWI/MNDWI and SAR water extent GeoJSON polygons to validate flood inundation intersection with Barahachhetra settlement points.
3. **Automated Backend Ingestion Pipeline**: Connect `ml/src/predict.py` to backend `POST /api/v1/predictions/ingest` via HTTP client.
4. **Probability Calibration**: Implement Platt scaling or Isotonic Regression on historical splits.
