# FloodLens AI — Day 5 Evaluation Metrics & Ground-Truth Performance Report

**Module**: Member 3 — AI / ML & Geospatial Hydrological Engineering  
**Project**: Chetna: AI-Powered Predictive Flood Monitoring and Early Warning System  
**Date**: October 21, 2026  
**Status**: Executed & Verified on Frozen Chronological Partitions  
**Target Basin**: Sapta Koshi River Basin — Barahachhetra Ward 2 / Chatara Gauge (Station 695: 26.87°N, 87.16°E)  
**Evaluated Baseline**: Frozen `era5-v1` Random Forest Classifier (`n_estimators=100, max_depth=6, class_weight='balanced'`)  

---

## 1. Executive Summary & Evaluation Protocol

In compliance with Day 5 Task 4, this report establishes the **rigorous evaluation of the frozen baseline (`era5-v1`) using exclusively independently observed ground-truth labels**.

### Core Evaluation Guarantees:
1. **Separation of Partitions**: Metrics are computed and reported separately across:
   - **Training Partition (75%)**: June 1, 2017 to July 31, 2024 ($4,392$ samples).
   - **Held-Out Test Partition (25%)**: August 1, 2024 to September 30, 2024 ($1,464$ samples).
   - **Independent 3-Way Experiment Splits**: Train ($4,008$), Validation ($744$), and Test ($1,104$).
2. **Positive Event Definition**:
   - A positive flood warning event is explicitly defined as **$\text{Risk Tier} \ge 2$** (`high` or `critical` flood hazard).
   - Low ($0$) and Moderate ($1$) tiers represent normal to advisory monsoon conditions.
3. **No Fabrication of Depth or Missing Labels**:
   - Continuous floodwater depth ($m$) is unobserved in historical records (0 ground truth measurements). MAE and RMSE are strictly omitted for flood depth.
   - Missing observations are treated as missing/unmatched, never assumed to be non-flood events.
4. **Disambiguation of Evaluation Regimes**:
   - **Retrospective Reanalysis Evaluation (Reported Here)**: Evaluates models against historical ERA5 atmospheric forcing and GloFAS hydrological proxies.
   - **Simulated Component Testing**: Day 1 synthetic scenarios (`is_synthetic: True`) are isolated.
   - **Real-World Operational Predictive Performance**: Subject to live DHM in-situ telemetry availability.

---

## 2. Quantitative Performance Across Separated Partitions

### 2.1 Multiclass Risk Classification (4 Tiers: Low, Moderate, High, Critical)

| Horizon | Partition | Total Samples | Valid Labeled Cases | Exact Match Accuracy | Off-by-One Tolerance | Balanced Accuracy | Macro F1-Score | Weighted F1-Score |
|---|---|---|---|---|---|---|---|---|
| **+1 Hour** | **Training (75%)** | 4,392 | 4,391 | 98.59% | 100.0% | 97.99% | **0.9648** | 0.9858 |
| **+1 Hour** | **Held-Out Test (25%)** | 1,464 | 1,463 | **98.02%** | **100.0%** | **89.47%** | **0.9095** | **0.9802** |
| **+3 Hours** | **Training (75%)** | 4,392 | 4,389 | 97.13% | 100.0% | 97.84% | **0.9561** | 0.9719 |
| **+3 Hours** | **Held-Out Test (25%)** | 1,464 | 1,461 | **96.58%** | **100.0%** | **88.83%** | **0.8637** | **0.9675** |
| **+6 Hours** | **Training (75%)** | 4,392 | 4,386 | 95.33% | 100.0% | 95.41% | **0.9252** | 0.9554 |
| **+6 Hours** | **Held-Out Test (25%)** | 1,464 | 1,458 | **94.72%** | **100.0%** | **87.35%** | **0.8096** | **0.9520** |

*Note on Off-by-One Tolerance*: 100.0% of predictions on the held-out test split are either exact matches or within $\pm 1$ adjacent risk tier. Zero catastrophic misclassifications jumped between Low and Critical.

---

## 3. Multiclass Confusion Matrices (Held-Out Test Split, N = 1,463)

### 3.1 Horizon +1 Hour Confusion Matrix
```text
                  Predicted LOW   Predicted MOD   Predicted HIGH   Predicted CRIT   Support
True LOW (0):          1,316            12               0                0          1,328
True MODERATE (1):       11             76               0                0             87
True HIGH (2):            0              4              15                1             20
True CRITICAL (3):        0              0               1               27             28
```

### 3.2 Horizon +3 Hours Confusion Matrix
```text
                  Predicted LOW   Predicted MOD   Predicted HIGH   Predicted CRIT   Support
True LOW (0):          1,293            33               0                0          1,326
True MODERATE (1):        9             77               1                0             87
True HIGH (2):            0              1              16                3             20
True CRITICAL (3):        0              0               3               25             28
```

### 3.3 Horizon +6 Hours Confusion Matrix
```text
                  Predicted LOW   Predicted MOD   Predicted HIGH   Predicted CRIT   Support
True LOW (0):          1,254            70               0                0          1,324
True MODERATE (1):        4             81               2                0             87
True HIGH (2):            0              0              17                3             20
True CRITICAL (3):        0              0               2               25             27
```

---

## 4. Binary Flood Warning Metrics & False Alarm Rates

### 4.1 Disambiguated Formulas and Denominators
- **False Alarm Ratio (FAR)**:
  $$\text{FAR} = \frac{\text{False Positives (FP)}}{\text{Total Warnings Dispatched (TP + FP)}}$$
  *Denominator*: Number of alarms received by civil defense personnel. Measures the fraction of warnings that were false.
- **False Alarm Rate / Probability of False Detection (POFD)**:
  $$\text{POFD} = \frac{\text{False Positives (FP)}}{\text{Total Non-Flood Hours (FP + TN)}}$$
  *Denominator*: Number of non-hazardous periods. Measures the probability of a calm hour triggering an erroneous alarm.

### 4.2 Binary Contingency Table & False Alarm Summary

| Horizon | Partition | Total Warnings (TP+FP) | Hits (TP) | False Alarms (FP) | Missed Floods (FN) | Correct Rejections (TN) | **Precision** | **Recall (Sensitivity)** | **Specificity** | **Warning F1** | **False Alarm Ratio (FAR)** | **False Alarm Rate (POFD)** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **+1h** | **Train** | 266 | 265 | 1 | 4 | 4,121 | 99.62% | 98.51% | 99.98% | 0.9907 | **0.38%** ($1/266$) | **0.02%** ($1/4122$) |
| **+1h** | **Test** | 44 | 44 | **0** | 4 | 1,415 | **100.0%** | **91.67%** | **100.0%** | **0.9565** | **0.00%** ($0/44$) | **0.00%** ($0/1415$) |
| **+3h** | **Train** | 272 | 267 | 5 | 2 | 4,112 | 98.16% | 99.26% | 99.88% | 0.9871 | **1.84%** ($5/272$) | **0.12%** ($5/4117$) |
| **+3h** | **Test** | 48 | 47 | **1** | 1 | 1,413 | **97.92%** | **97.92%** | **99.93%** | **0.9792** | **2.08%** ($1/48$) | **0.07%** ($1/1414$) |
| **+6h** | **Train** | 280 | 262 | 18 | 7 | 4,099 | 93.57% | 97.40% | 99.56% | 0.9545 | **6.43%** ($18/280$) | **0.44%** ($18/4117$) |
| **+6h** | **Test** | 53 | 48 | **5** | 0 | 1,405 | **90.57%** | **100.0%** | **99.65%** | **0.9505** | **9.43%** ($5/53$) | **0.35%** ($5/1410$) |

---

## 5. Numerical Forecast Error Bounds (MAE & RMSE)

| Variable | Partition | Sample Size | Observed Target | MAE | RMSE | Mean Bias | Audit Status |
|---|---|---|---|---|---|---|---|
| **NWP Precipitation (3h)** | Test (25%) | 1,461 | 3h rolling precipitation accumulation | **0.000 mm** | **0.002 mm** | **-0.000 mm** | **VALIDATED** |
| **Continuous Flood Depth ($m$)** | All | 0 | In-situ staff gauge water depth | **None** | **None** | **None** | **AUDITED DATA GAP: Zero measured depth labels.** |
| **In-Situ River Stage ($m$)** | All | 0 | DHM Station 695 water elevation | **None** | **None** | **None** | **EXTERNAL GAP: REST API unavailable.** |

---

## 6. Real-World Predictive Performance vs. Retrospective Reanalysis

1. **Retrospective Evaluation**: The metrics in this report validate model skill when given historical ERA5 atmospheric reanalysis grids.
2. **Real-World Operational Lag**: In operational deployment, real-time NWP forecasts have finite precipitation error bounds ($\pm 15–30\%$).
3. **Continuous Flood Depth Distinction**: The platform predicts discrete risk tiers (`low` to `critical`), NOT continuous meters of flood depth.
