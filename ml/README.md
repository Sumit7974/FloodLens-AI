# FloodLens AI — AI / ML Module (Member 3)

[![Tests](https://img.shields.io/badge/Tests-20%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.14-blue.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-Multi--Horizon%20(+1h%2C%20+3h%2C%20+6h)-orange.svg)]()

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
│   ├── raw/                          # Original immutable datasets (read-only)
│   ├── processed/                    # Cleaned, validated, and normalized datasets
│   └── synthetic/                    # Clearly labeled synthetic demo datasets
├── models/                           # Serialized model artifacts (.joblib) & metadata
├── reports/                          # Audit summaries, cleaning metrics, and evaluation JSONs
├── src/
│   ├── __init__.py                   # Package initialization
│   ├── data_audit.py                 # Data feed inspection, missingness & QA audit tool
│   ├── data_cleaning.py              # Cleaning pipeline (dedup, UTC, bounds, gap handling)
│   ├── label_builder.py              # DHM threshold labeling, horizon shifting & synthetic generator
│   ├── train_baseline.py             # Reproducible multi-horizon Random Forest & Dummy baseline
│   └── predict.py                    # Prediction service matching backend REST API contract
├── tests/
│   ├── __init__.py                   # Test package initialization
│   ├── test_data_cleaning.py         # Tests for deduplication, timestamps, outliers, coords
│   ├── test_label_builder.py         # Tests for DHM thresholds, leakage prevention, generator
│   ├── test_train_baseline.py        # Tests for chronological split, reproducibility, metrics
│   └── test_predict.py               # Tests for backend contract, safety assertions & missing feeds
└── docs/
    ├── data_audit.md                 # Detailed historical flood & data inventory report
    ├── labeling_strategy.md          # 4-tier risk labels, DHM thresholds & horizons formulation
    ├── model_contract.md             # Ingestion schema, input features & backend integration
    ├── model_limitations.md          # Physical limitations, missing feeds & safety directives
    └── day1_report.md                # Comprehensive Day 1 engineering report
```

---

## 2. Quick Start and CLI Execution

### 2.1 Installation
Install ML dependencies in your Python environment:
```bash
pip install -r ml/requirements.txt
```

### 2.2 Step 1: Generate Synthetic Demonstration Dataset
Generate a physically consistent 10-day hourly synthetic flood event for the Sapta Koshi basin:
```bash
python ml/src/label_builder.py --output ml/data/synthetic/synthetic_koshi_event.csv --n-hours 240 --seed 42
```

### 2.3 Step 2: Audit Dataset Feeds
Audit the raw or synthetic dataset for nulls, coordinate boundaries, and interval regularity:
```bash
python ml/src/data_audit.py --input-file ml/data/synthetic/synthetic_koshi_event.csv --output ml/reports/data_audit_summary.json
```

### 2.4 Step 3: Run the Data-Cleaning Pipeline
Clean, deduplicate, validate coordinates against Nepal bounds, and handle short sensor gaps:
```bash
python ml/src/data_cleaning.py --input ml/data/synthetic/synthetic_koshi_event.csv --output ml/data/processed/koshi_event_cleaned.csv --summary ml/reports/cleaning_summary.json
```

### 2.5 Step 4: Train Baseline Multi-Horizon Models (+1h, +3h, +6h)
Train reproducible Random Forest classifiers using strict chronological splitting (no data leakage):
```bash
python ml/src/train_baseline.py --data ml/data/processed/koshi_event_cleaned.csv --output-dir ml/models --reports-dir ml/reports --model-version baseline-v1
```

### 2.6 Step 5: Test Inference & Backend Contract
Run prediction inference and inspect the backend-compliant JSON output:
```bash
python ml/src/predict.py --location-id loc_barahachhetra_w2 --models-dir ml/models --model-version baseline-v1
```

### 2.7 Step 6: Run Pytest Test Suite
Execute the 20-test automated verification suite:
```bash
python -m pytest ml/tests -v
```

---

## 3. Core Safety Directives
1. **No False Low-Risk Outputs**: When sensor telemetry drops out, the model outputs `data_quality: "UNAVAILABLE"` and `risk_level: "unknown"`, refusing to emit a false low-risk result.
2. **Explicit Demo Labeling**: All synthetic demonstration results are tagged with `mode: "historical_demo"`.
3. **No Direct Citizen Alerts**: Experimental predictions cannot trigger sirens or public emergency notifications without authority review.
