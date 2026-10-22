# FloodLens AI — Day 5 Baseline & Evaluation Data Freeze Report

**Module**: Member 3 — AI / ML & Geospatial Hydrological Engineering  
**Project**:  AI-Powered Predictive Flood Monitoring and Early Warning System  
**Date**: 2026-10-21  
**Manifest ID**: `manifest_freeze_era5_v1_20261021_175127`  
**Tamper Protection Status**: **VERIFIED_LOCKED**  

---

## 1. Executive Summary

In accordance with Day 5 scientific and engineering requirements, this document formally **freezes the baseline risk forecasting model (`era5-v1`) and the primary historical evaluation dataset**. Cryptographic SHA-256 hashes, temporal bounds, and chronological partition boundaries are recorded below to ensure that subsequent experiments cannot overwrite or silently alter the established baseline.

---

## 2. Frozen Artifacts & Cryptographic SHA-256 Manifest

| Artifact Relative Path | Type | File Size | SHA-256 Cryptographic Checksum | Purpose |
|---|---|---|---|---|
| `ml/data/processed/era5_glofas_labeled.csv` | `dataset` | 1,695,645 bytes | `708b49d1dc560a06791204a0f26a91d26d8cfa76ec9a35f48859bfe4c3afae22` | Operational evaluation and reanalysis training dataset for Sapta Koshi Chatara Gorge. |
| `ml/models/baseline_rf_plus_1h_era5-v1.joblib` | `model_binary` | 822,059 bytes | `5aca208c3455ecbb5141488d50ff0861e7ef1e77874140c78f7fbdbef19cc68e` | Baseline Random Forest multi-horizon classifier for +1h lead time. |
| `ml/models/baseline_rf_plus_3h_era5-v1.joblib` | `model_binary` | 896,555 bytes | `e61b4644b72f04512643ea5b1aa05e66dfc554950a0cc39d7d438f65eb9747b3` | Baseline Random Forest multi-horizon classifier for +3h lead time. |
| `ml/models/baseline_rf_plus_6h_era5-v1.joblib` | `model_binary` | 963,947 bytes | `93817bffbe2bec77ab2596926ca069b95dacc73e817cd5f7e87f391e93ce2fe6` | Baseline Random Forest multi-horizon classifier for +6h lead time. |
| `ml/models/model_metadata_era5-v1.json` | `metadata` | 1,085 bytes | `18d527b7f29bf57336176c912fdccbc12eaedb472f3c47f8716fbb6a1f8536a7` | Model hyperparameter, feature schema, and threshold metadata for era5-v1. |

---

## 3. Baseline Model Specification (`era5-v1`)

- **Model Architecture**: Random Forest Classifier (`n_estimators=100, max_depth=6, class_weight='balanced'`)
- **Prediction Horizons**: +1 Hour, +3 Hours, +6 Hours
- **Feature Inputs (12 features)**:
  - **Continuous Hydrometeorological (10)**: `rainfall_mm`, `rainfall_rolling_3h_mm`, `rainfall_rolling_6h_mm`, `rainfall_rolling_24h_mm`, `river_stage_m` (NaN), `river_stage_rate_of_rise_m_per_h` (NaN), `upstream_discharge_m3s`, `forecast_precip_next_3h_mm`, `temperature_c`, `relative_humidity_pct`
  - **Categorical (2)**: `season`, `catchment_saturation_class`
- **Preprocessing Pipeline**:
  - Numeric: `SimpleImputer(strategy='median')` + `StandardScaler()`
  - Categorical: `SimpleImputer(strategy='most_frequent')` + `OneHotEncoder(handle_unknown='ignore')`
- **Binary Warning Threshold**: Positive event defined as $\text{Risk Tier} \ge 2$ (`high` or `critical`).

---

## 4. Chronological Partition Boundaries

To guarantee zero data leakage between training and testing, data splitting strictly respects temporal sequence:

| Partition Name | Start UTC | End UTC | Sample Count | % of Total | Operational Role |
|---|---|---|---|---|---|
| `frozen_baseline_train_75pct` | `2017-06-01T00:00:00+00:00` | `2024-07-31T23:00:00+00:00` | 4,392 | 75.0% | Historical training partition used to train era5-v1 baseline models. |
| `frozen_baseline_test_25pct` | `2024-08-01T00:00:00+00:00` | `2024-09-30T23:00:00+00:00` | 1,464 | 25.0% | Immutable held-out test split for evaluating baseline and candidate models (Aug-Sep 2024). |
| `experiment_training_partition` | `2017-06-01T00:00:00+00:00` | `2024-07-15T23:00:00+00:00` | 4,008 | 68.44% | Historical training window for candidate offline model experimentation. |
| `experiment_validation_partition` | `2024-07-16T00:00:00+00:00` | `2024-08-15T23:00:00+00:00` | 744 | 12.7% | Tuning partition for hyperparameter selection and threshold calibration (NO TEST LEAKAGE). |
| `experiment_test_partition` | `2024-08-16T00:00:00+00:00` | `2024-09-30T23:00:00+00:00` | 1,104 | 18.85% | Untouched held-out test split reserved exclusively for final candidate benchmarking. |

---

## 5. Documented Missing-Data Limitations

- **Zero in-situ river stage telemetry: river_stage_m is NaN in reanalysis feeds.**
- **Continuous floodwater depth is unobserved in historical records (0 ground-truth depth observations).**
- **GloFAS discharge represents daily reanalysis estimate, not direct in-situ gauge readings.**
- **ERA5 25km grid cell smooths sub-grid mountain convective cloudbursts (<15min onset).**

---

## 6. Tamper-Detection Verification Command

To verify that baseline models and evaluation data remain untouched at any point during development:

```powershell
python -c "from ml.src.baseline_freeze import verify_frozen_baseline_integrity; ok, issues = verify_frozen_baseline_integrity(); print('Intact:', ok, issues)"
```
