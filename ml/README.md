# FloodLens AI — AI / ML Module (Member 3)

[![Tests](https://img.shields.io/badge/Tests-68%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.14-blue.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-Multi--Horizon%20(+1h%2C%20+3h%2C%20+6h)-orange.svg)]()
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-success.svg)]()

This directory contains the complete **AI / ML & Hydrological Risk Baseline Module** for **FloodLens AI**, focused on multi-horizon flood risk forecasting for the **Nepal Terai region** (Sapta Koshi River Basin, Chatara Gorge / Barahachhetra, Sunsari District).

---

## 1. Directory Structure

```text
ml/
├── README.md                          # This developer guide
├── requirements.txt                   # Machine learning dependencies
├── configs/
│   └── baseline_config.json          # Feature lists, thresholds, cleaning parameters
├── data/
│   ├── raw/                          # Original immutable datasets (read-only; ignored in git)
│   ├── processed/                    # Cleaned, validated, and normalized datasets (ignored in git)
│   └── synthetic/                    # Clearly labeled synthetic demo datasets
├── models/                           # Serialized model artifacts (.joblib) & metadata
│   ├── baseline_rf_plus_*_baseline-v1.joblib # Day 1 synthetic baseline models
│   ├── baseline_rf_plus_*_era5-v1.joblib     # Day 2 ERA5/GloFAS reanalysis models
│   ├── model_metadata_baseline-v1.json
│   └── model_metadata_era5-v1.json
├── reports/                          # Audit summaries, cleaning metrics, and evaluation JSONs
│   ├── data_audit_summary.json       # Dataset audit report
│   ├── cleaning_summary.json         # Data-cleaning QA summary
│   ├── training_report_baseline-v1.json # Day 1 baseline training metrics
│   ├── training_report_era5-v1.json  # Day 2 reanalysis training metrics
│   ├── ingestion_provenance_2017.json # 2017 ERA5/GloFAS provenance record
│   └── ingestion_provenance_2024.json # 2024 ERA5/GloFAS provenance record
├── src/
│   ├── __init__.py                   # Package initialization
│   ├── data_audit.py                 # Data feed inspection, missingness & QA audit tool
│   ├── data_cleaning.py              # Cleaning pipeline (dedup, UTC, bounds, gap handling)
│   ├── data_ingestion.py             # Day 2 ERA5 & GloFAS automated API fetch and enrichment
│   ├── label_builder.py              # DHM threshold labeling, horizon shifting & synthetic generator
│   ├── reanalysis_labeling.py        # Day 2 rainfall-dominant labeling strategy for reanalysis
│   ├── train_baseline.py             # Reproducible multi-horizon Random Forest & Dummy baseline
│   └── predict.py                    # Prediction service matching backend REST API contract
├── tests/
│   ├── __init__.py                   # Test package initialization
│   ├── test_data_cleaning.py         # Tests for deduplication, timestamps, outliers, coords
│   ├── test_data_ingestion.py        # Tests for Day 2 ingestion, reanalysis labeling & features
│   ├── test_label_builder.py         # Tests for DHM thresholds, leakage prevention, generator
│   ├── test_train_baseline.py        # Tests for chronological split, reproducibility, metrics
│   └── test_predict.py               # Tests for backend contract, safety assertions & missing feeds
└── docs/
    ├── data_audit.md                 # Detailed historical flood & data inventory report
    ├── labeling_strategy.md          # 4-tier risk labels, DHM thresholds & horizons formulation
    ├── model_contract.md             # Ingestion schema, input features & backend integration
    ├── model_limitations.md          # Physical limitations, missing feeds & safety directives
    ├── day1_report.md                # Comprehensive Day 1 engineering report
    └── day2_report.md                # Comprehensive Day 2 engineering report
```

---

## 2. Quick Start and CLI Execution

### 2.1 Installation
Install ML dependencies in your Python environment:
```bash
pip install -r ml/requirements.txt
```

### 2.2 Day 1: Synthetic Demonstration Pipeline
Generate synthetic flood event data, clean it, train baseline models, and run inference:
```bash
# 1. Generate synthetic dataset
python ml/src/label_builder.py --output ml/data/synthetic/synthetic_koshi_event.csv --n-hours 240 --seed 42

# 2. Audit dataset feeds
python ml/src/data_audit.py --input-file ml/data/synthetic/synthetic_koshi_event.csv --output ml/reports/data_audit_summary.json

# 3. Clean and validate dataset
python ml/src/data_cleaning.py --input ml/data/synthetic/synthetic_koshi_event.csv --output ml/data/processed/koshi_event_cleaned.csv --summary ml/reports/cleaning_summary.json

# 4. Train multi-horizon baseline models (+1h, +3h, +6h)
python ml/src/train_baseline.py --data ml/data/processed/koshi_event_cleaned.csv --output-dir ml/models --reports-dir ml/reports --model-version baseline-v1

# 5. Test inference matching backend contract
python ml/src/predict.py --location-id loc_barahachhetra_w2 --models-dir ml/models --model-version baseline-v1
```

### 2.3 Day 2: ERA5 & GloFAS Reanalysis Pipeline
Fetch open-access reanalysis time-series, label using rainfall-dominant criteria, and train multi-horizon models:
```bash
# 1. Fetch ERA5 + GloFAS reanalysis data (Open-Meteo APIs, CC BY 4.0)
python ml/src/data_ingestion.py --start-date 2017-06-01 --end-date 2017-09-30 --output ml/data/raw/era5_glofas_chatara_2017.csv --provenance ml/reports/ingestion_provenance_2017.json

# 2. Label reanalysis time-series
python ml/src/reanalysis_labeling.py --input ml/data/raw/era5_glofas_chatara_combined.csv --output ml/data/processed/era5_glofas_labeled.csv

# 3. Train multi-horizon models on reanalysis data
python ml/src/train_baseline.py --data ml/data/processed/era5_glofas_labeled.csv --output-dir ml/models --reports-dir ml/reports --model-version era5-v1

# 4. Test inference with reanalysis prototype
python ml/src/predict.py --location-id loc_barahachhetra_w2 --models-dir ml/models --model-version era5-v1
```

### 2.4 Run Automated Pytest Suite
Execute the 68-test automated verification suite:
```bash
python -m pytest ml/tests -v
```

---

## 3. Core Safety Directives
1. **No False Low-Risk Outputs**: When sensor telemetry drops out, the model outputs `data_quality: "UNAVAILABLE"` and `risk_level: "unknown"`, refusing to emit a false low-risk result.
2. **Explicit Demo & Reanalysis Labeling**: Synthetic demo outputs use `mode: "historical_demo"`. Reanalysis models are clearly flagged with `is_reanalysis_data: true` and documented with research prototype disclaimers.
3. **No Direct Citizen Alerts**: Experimental predictions cannot trigger sirens or public emergency notifications without authority review.
