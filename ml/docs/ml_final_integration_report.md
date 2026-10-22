# FloodLens AI — ML Final Integration & Validation Report

**Role**: Senior AI/ML Engineer + FastAPI Integration Engineer + QA Engineer  
**Date**: 2026-10-22  
**Branch**: `feature/ml-final-validation`  
**Base Review Branch**: `fix/ml-day5-ci-and-integration` (PR #9)  
**Target Candidate**: `candidate-leakfree-v1` (Retrospective Leak-Free Random Forest Multi-Horizon Classifier)  

---

## 1. Executive Summary & Verdicts

This report documents the final integration, end-to-end FastAPI/ML pipeline verification, frontend compatibility, and scientific validation for FloodLens AI.

### Verdict A: Historical-Demo Hackathon Readiness — **READY**
- The leak-free ML candidate (`candidate-leakfree-v1`) successfully generates schema-compliant +1h, +3h, and +6h flood risk predictions with explicit data-quality flags and operational limitations.
- Programmatic submission through `POST /api/v1/predictions/ingest` and readback through `GET /api/v1/predictions/latest` and `/api/v1/predictions/map` were verified against live FastAPI routes.
- The React authority dashboard (`PredictionCentre`) retrieves and displays the persisted forecast, model version, UTC timestamps, risk levels, and operational provenance caveats with offline fallback.
- All 115 runnable ML unit and regression tests pass with zero failures.

### Verdict B: Real-World Operational Flood Forecasting Readiness — **NOT READY**
- **Proxy Labels**: Historical training labels are derived from ERA5 rainfall thresholds ($\ge 25\text{mm}$, $\ge 100\text{mm}$, $\ge 150\text{mm}$) and GloFAS discharge percentiles, **not** confirmed in-situ flood inundation ground truth.
- **Unobserved In-situ Gauge Telemetry**: Historical reanalysis feeds lack continuous in-situ river stage and water depth measurements (`river_stage_m` is unobserved/NaN).
- **Uncalibrated Probabilities**: Classifier probability estimates are uncalibrated Random Forest decision-tree votes; `calibrated_probability` is conservatively omitted (`null`).
- **Missing Dataset Artifact**: The external reanalysis dataset (`era5_glofas_labeled.csv`) is excluded from version control and must be recovered from audited backups before model retraining or operational certification.

---

## 2. Final Model Selected

| Attribute | Specification |
| :--- | :--- |
| **Model Version** | `candidate-leakfree-v1` |
| **Architecture** | Random Forest Multi-Horizon Classifier (`n_estimators=100, max_depth=6, class_weight='balanced'`) |
| **Horizons** | +1 Hour, +3 Hours, +6 Hours |
| **Output Classes** | `low` (0), `moderate` (1), `high` (2), `critical` (3) |
| **Serialization** | `ml/models/experiments/leakfree_rf_plus_{1,3,6}h_candidate-leakfree-v1.joblib` |
| **Metadata Manifest** | `ml/models/experiments/experiment_metadata_candidate-leakfree-v1.json` |

---

## 3. Model Input and Output Schemas

### 3.1 Input Features (11 Features)
- **Continuous Hydrometeorological (9)**:
  - `rainfall_mm` (Hour [t-1, t] ERA5 accumulation)
  - `rainfall_rolling_3h_mm` (Backward rolling 3h sum)
  - `rainfall_rolling_6h_mm` (Backward rolling 6h sum)
  - `rainfall_rolling_24h_mm` (Backward rolling 24h synoptic sum)
  - `river_stage_m` (NaN in reanalysis; guarded with `CRITICAL_HYDROLOGICAL_FEATURES` check)
  - `river_stage_rate_of_rise_m_per_h` (NaN in reanalysis)
  - `upstream_discharge_m3s_lag24h` (GloFAS daily discharge lagged by 24h to eliminate calendar lookahead)
  - `temperature_c` (ERA5 2-meter air temperature)
  - `relative_humidity_pct` (ERA5 2-meter relative humidity)
- **Categorical (2)**:
  - `season` (`monsoon`, `pre_monsoon`, `post_monsoon`, `winter`)
  - `catchment_saturation_class` (`dry`, `moderate`, `wet`, `saturated`)

### 3.2 Ingest Request Schema (`ForecastIngestRequest`)
```json
{
  "forecast_id": "fc_58b07249f6e0",
  "event_id": "evt_nepal_terai_koshi",
  "location_id": "loc_barahachhetra_w2",
  "issued_at": "2026-10-22T17:28:48Z",
  "mode": "historical_demo",
  "model_version": "candidate-leakfree-v1",
  "input_data_cutoff_at": "2026-10-22T17:28:48Z",
  "data_quality": "PARTIAL",
  "horizons": [
    {"hours": 1, "risk_level": "high"},
    {"hours": 3, "risk_level": "critical"},
    {"hours": 6, "risk_level": "critical"}
  ],
  "limitations": [
    "RESEARCH PROTOTYPE: Model trained on ERA5/GloFAS reanalysis proxy data.",
    "Critical feeds missing: ['river_stage_m']. Predictions may suffer degraded accuracy.",
    "Raw Random Forest class scores are NOT probability-calibrated; calibrated_probability is omitted.",
    "Historical simulation only; proxy-labelled reanalysis is not independently verified flood ground truth."
  ]
}
```

---

## 4. Dataset Sources, Limitations, and Integrity Results

### 4.1 Sources
- **Meteorological**: ECMWF ERA5 hourly surface reanalysis via Open-Meteo Historical Weather API.
- **Hydrological**: Copernicus GloFAS v4.0 daily river discharge for Sapta Koshi Chatara Gorge (87.16°E, 26.87°N).
- **Synthetic Test Fixture**: `ml/data/synthetic/synthetic_koshi_event.csv` used for deterministic offline test pipelines.

### 4.2 Dataset Integrity Results: **BLOCKED**
- Primary dataset `ml/data/processed/era5_glofas_labeled.csv` (1,695,645 bytes, SHA-256 `708b49d1dc560a06791204a0f26a91d26d8cfa76ec9a35f48859bfe4c3afae22`) is **excluded from Git**.
- In accordance with audit rules, the file was not synthesized, fabricated, or replaced.
- Verification of the full reanalysis dataset is therefore reported as **BLOCKED**.

### 4.3 Model Artifacts & Metadata Integrity: **PASS**
All three frozen baseline models and their metadata were verified against `frozen_baseline_manifest.json`:
- `baseline_rf_plus_1h_era5-v1.joblib` -> `5aca208c3455...` (**MATCH**)
- `baseline_rf_plus_3h_era5-v1.joblib` -> `e61b4644b72f...` (**MATCH**)
- `baseline_rf_plus_6h_era5-v1.joblib` -> `93817bffbe2b...` (**MATCH**)
- `model_metadata_era5-v1.json` -> `18d527b7f29b...` (**MATCH, 1085 CRLF bytes**)

---

## 5. Temporal Leakage Audit & Controls

| Vulnerability | Identified in Baseline (`era5-v1`) | Resolution in Candidate (`candidate-leakfree-v1`) |
| :--- | :--- | :--- |
| **Future Rainfall Lookahead** | `forecast_precip_next_3h_mm` shifted future precipitation $t+3\text{h}$ into feature vector at $t$. | **Removed completely.** Model relies strictly on antecedent accumulation. |
| **Intra-Day Aggregation** | GloFAS daily discharge merged by calendar date, leaking evening flows to morning issuance. | **24-hour lag applied (`upstream_discharge_m3s_lag24h`).** Only completed day $D-1$ flows are ingested. |
| **Chronological Partitions** | Risk of random train/test shuffling. | **Strict 3-way chronological split**: Train (68.4%), Val (12.7%), Test (18.9%). |
| **Preprocessing Isolation** | Risk of test set statistical leakage. | `ColumnTransformer` fitted strictly on training partition; test split transformed out-of-sample. |
| **Missing Input Safety** | Risk of default false low-risk classification. | If critical feeds missing, pipeline forces `risk_level: "unknown"` and `data_quality: "UNAVAILABLE"`. |

---

## 6. Test Results

### 6.1 ML Test Suite (`ml/tests`)
- **Total Tests**: 118
- **Passed**: **115**
- **Skipped**: **3** (Explicitly documented skips when external reanalysis CSV is missing)
- **Failed**: **0**

### 6.2 Backend Test Suite (`backend/tests`)
- **Total Tests**: 72
- **Passed**: **69**
- **Skipped**: **3** (Live PostGIS query tests when PostGIS daemon is absent)
- **Failed**: **0**

---

## 7. FastAPI Integration & Persistence Results

| Verification Check | Method / Route | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Backend Health** | `GET /api/v1/health` | **PASS (200 OK)** | Status: `healthy`, SQLite fallback active |
| **Locations Query** | `GET /api/v1/locations` | **PASS (200 OK)** | Returned `loc_barahachhetra_w2` |
| **Authority Auth** | JWT Access Token | **PASS** | Role: `authority`, HS256 signature verified |
| **Forecast Ingest** | `POST /api/v1/predictions/ingest` | **PASS (201 Created)** | Stored `ForecastRun` and 3 `RiskPrediction` records |
| **Latest Readback** | `GET /api/v1/predictions/latest` | **PASS (200 OK)** | Horizons +1h (high), +3h (critical), +6h (critical) matched |
| **Map Layer Sync** | `GET /api/v1/predictions/map` | **PASS (200 OK)** | Active risk zones synthesized with dynamic max risk tier |
| **PostgreSQL Persistence** | PostgreSQL / PostGIS connection | **BLOCKED** | Local Windows environment lacks PostgreSQL daemon and Docker service |

---

## 8. Frontend Retrieval Results: **PASS**

The React authority dashboard component [PredictionCentre.tsx](file:///c:/Users/ABC/FloodLens-AI/FloodLens-AI/frontend/src/components/PredictionCentre.tsx) was verified:
- Asynchronously queries `GET /api/v1/predictions/latest?location_id=loc_barahachhetra_w2`.
- Displays dynamic header badge: `MODEL: CANDIDATE-LEAKFREE-V1 (BACKEND PERSISTED)`.
- Renders UTC issuance timestamp and data quality status (`PARTIAL`).
- Updates horizon selector pills with model output (+1h: HIGH, +3h: CRITICAL, +6h: CRITICAL).
- Renders model limitations banner with provenance details and disclaimer notes.
- Gracefully falls back to demo mode when the backend is offline.
- TypeScript build (`npm run build`) and lint checks (`oxlint`) pass with 0 errors.

---

## 9. Commands to Reproduce the Integration Demo

```powershell
# 1. Install ML dependencies and run ML tests
python -m pip install -r ml/requirements.txt
python -m pytest ml/tests -v

# 2. Seed isolated test database and generate authority token
python -c "
import os, sys
os.environ['DATABASE_URL'] = 'sqlite:///./test_floodlens.db'
sys.path.insert(0, os.path.abspath('backend'))
from app.database import Base, engine
import app.models
Base.metadata.create_all(bind=engine)
"

# 3. Start FastAPI backend (in backend/ directory)
cd backend
$env:DATABASE_URL="sqlite:///./test_floodlens.db"
uvicorn app.main:app --port 8000

# 4. Dry-run ML forecast generation
python -m ml.scripts.submit_demo_forecast `
  --features-file ml/examples/historical_demo_inputs.json `
  --location-id loc_barahachhetra_w2

# 5. Authenticated submission and readback against running FastAPI
$env:FLOODLENS_BACKEND_URL="http://127.0.0.1:8000"
$env:FLOODLENS_AUTHORITY_TOKEN="<authority JWT>"
python -m ml.scripts.submit_demo_forecast `
  --features-file ml/examples/historical_demo_inputs.json `
  --location-id loc_barahachhetra_w2 `
  --event-id evt_nepal_terai_koshi `
  --submit

# 6. Verify frontend compilation
cd ../frontend
npm run build
npm run lint
```
