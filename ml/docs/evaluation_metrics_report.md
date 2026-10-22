# FloodLens AI — Evaluation Metrics, Error Analysis & False Alarm Report

**Module**: Member 3 — AI / ML & Geospatial Hydrological Engineering  
**Project**: FloodLens AI / Chetna Early Warning System  
**Date**: October 21, 2026  
**Status**: Executed & Verified on Chronological Held-Out Test Split (August 1 to September 30, 2024; 1,464 Hourly Samples)  
**Evaluated Models**: Baseline Random Forest (`era5-v1`) vs. Candidate Gradient Boosting Decision Trees (`candidate-v2`)  

---

## 1. Executive Summary

This report establishes the quantitative performance, false-alarm characteristics, and numerical error bounds for FloodLens AI risk forecasts on the strictly isolated 25% chronological held-out test split (1,464 hourly records).

### Key Findings:
1. **Multiclass Risk Classification (+1h)**:
   - **Baseline RF (`era5-v1`)**: Macro F1 = **0.9095**, Balanced Accuracy = **89.47%**, Exact Match Accuracy = **98.02%**, Off-by-one Tolerance = **100.0%**.
   - **Candidate GBDT (`candidate-v2`)**: Macro F1 = **0.9059**, Balanced Accuracy = **89.45%**, Exact Match Accuracy = **98.84%**, Off-by-one Tolerance = **100.0%**.
2. **Binary Flood Warning (+1h, Warning = High or Critical)**:
   - **Baseline RF**: Warning Precision = **100.0%**, Warning Recall = **91.67%**, Warning F1 = **0.9565**, False Alarm Ratio (FAR) = **0.00%**, False Alarm Rate (POFD) = **0.00%**.
   - **Candidate GBDT**: Warning Precision = **100.0%**, Warning Recall = **97.92%**, Warning F1 = **0.9895**, False Alarm Ratio (FAR) = **0.00%**, False Alarm Rate (POFD) = **0.00%**.
3. **Severe False Alarm Jumps**:
   - Zero (0) predictions across either model jumped from `LOW` directly to `CRITICAL`.
4. **Numerical Forecasts (MAE & RMSE)**:
   - **NWP 3-Hour Precipitation Forecast**: MAE = **0.0 mm**, RMSE = **0.002 mm** against reanalysis accumulation.
   - **Continuous Floodwater Depth**: **AUDITED DATA LIMITATION**. Continuous depth observations do not exist (0 ground-truth depth points). MAE/RMSE are strictly not computed to prevent fabricated claims.

---

## 2. Multiclass Risk Classification Performance

### 2.1 Metric Definitions
- **Exact Match Accuracy**: Proportion of samples where $\hat{y} = y$.
- **Off-by-One Tolerance Accuracy**: Proportion of samples where $|\hat{y} - y| \le 1$ (e.g., predicting Moderate when true is Low).
- **Balanced Accuracy**: Unweighted average of recall across all 4 risk classes.
- **Macro F1**: Unweighted arithmetic mean of per-class F1-scores (equally weights rare Critical floods with common Low-risk periods).

### 2.2 Comprehensive Metric Comparison Table

| Metric | Horizon +1h (RF) | Horizon +1h (GBDT) | Horizon +3h (RF) | Horizon +3h (GBDT) | Horizon +6h (RF) | Horizon +6h (GBDT) | Reference (Dummy) |
|---|---|---|---|---|---|---|---|
| **Exact Accuracy** | 98.02% | **98.84%** | 96.58% | **96.71%** | 94.72% | **96.30%** | 90.71% |
| **Off-by-One Tolerance** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | **100.0%** | 96.65% |
| **Balanced Accuracy** | 89.47% | 89.45% | **88.83%** | 80.80% | **87.35%** | 77.60% | 25.00% |
| **Macro F1-Score** | **0.9095** | 0.9059 | **0.8637** | 0.8213 | **0.8096** | 0.7994 | 0.2379 |
| **Weighted F1-Score** | 0.9802 | **0.9880** | 0.9675 | **0.9676** | 0.9520 | **0.9628** | 0.8631 |

### 2.3 Multiclass Confusion Matrix (+1h Horizon, Sample Size = 1,463)

#### Baseline Random Forest (`era5-v1`):
```text
                  Predicted LOW   Predicted MOD   Predicted HIGH   Predicted CRIT   Support
True LOW (0):          1,316            12               0                0          1,328
True MODERATE (1):       11             76               0                0             87
True HIGH (2):            0              4              15                1             20
True CRITICAL (3):        0              0               1               27             28
```

#### Candidate Gradient Boosting (`candidate-v2`):
```text
                  Predicted LOW   Predicted MOD   Predicted HIGH   Predicted CRIT   Support
True LOW (0):          1,322             6               0                0          1,328
True MODERATE (1):        9             78               0                0             87
True HIGH (2):            0              1              19                0             20
True CRITICAL (3):        0              0               1               27             28
```

---

## 3. False Alarm Analysis & Detailed Formulations

### 3.1 Formulas and Disambiguation

In hydrological flood warning systems, two distinct formulas exist with different denominators:

1. **False Alarm Ratio (FAR)**:
   $$\text{FAR} = \frac{\text{False Positives (FP)}}{\text{Total Warnings Issued (TP + FP)}}$$
   - *Denominator*: Total alarms dispatched to civil protection.
   - *Interpretation*: The percentage of dispatched warnings that turned out to be false alarms.
2. **False Alarm Rate / Probability of False Detection (POFD)**:
   $$\text{POFD} = \frac{\text{False Positives (FP)}}{\text{Total Non-Flood Periods (FP + TN)}}$$
   - *Denominator*: Total non-hazardous periods.
   - *Interpretation*: The probability that a quiet, non-flood hour incorrectly generated an alarm.
3. **Severe False Alarm Jump**:
   $$\text{Severe Jump} = \sum \mathbb{I}(\hat{y} = \text{CRITICAL} \land y = \text{LOW})$$
   - *Interpretation*: Erroneous catastrophic warnings issued during calm conditions.

### 3.2 False Alarm Metrics Summary

| Horizon | Model | Total Warnings Issued (TP+FP) | Hits (TP) | False Alarms (FP) | Missed Floods (FN) | Correct Rejections (TN) | **False Alarm Ratio (FAR)** | **False Alarm Rate (POFD)** | Severe Jumps (0 $\to$ 3) |
|---|---|---|---|---|---|---|---|---|---|
| **+1h** | **Baseline RF** | 44 | 44 | **0** | 4 | 1,415 | **0.00%** ($0/44$) | **0.00%** ($0/1415$) | **0** |
| **+1h** | **Candidate GBDT** | 47 | 47 | **0** | 1 | 1,415 | **0.00%** ($0/47$) | **0.00%** ($0/1415$) | **0** |
| **+3h** | **Baseline RF** | 48 | 47 | **1** | 1 | 1,413 | **2.08%** ($1/48$) | **0.07%** ($1/1414$) | **0** |
| **+3h** | **Candidate GBDT** | 48 | 46 | **2** | 2 | 1,413 | **4.17%** ($2/48$) | **0.14%** ($2/1415$) | **0** |
| **+6h** | **Baseline RF** | 53 | 48 | **5** | 0 | 1,405 | **9.43%** ($5/53$) | **0.35%** ($5/1410$) | **0** |
| **+6h** | **Candidate GBDT** | 45 | 44 | **1** | 4 | 1,409 | **2.22%** ($1/45$) | **0.07%** ($1/1410$) | **0** |

> [!NOTE]
> At lead time +6h, Candidate GBDT lowers the False Alarm Ratio from **9.43% down to 2.22%**, drastically reducing unnecessary emergency warning dispatches at longer lead times.

---

## 4. Numerical Forecast Errors (MAE & RMSE)

| Variable | Sample Size | Observed Source | Target Value | MAE | RMSE | Mean Bias | Operational Status |
|---|---|---|---|---|---|---|---|
| **NWP Precipitation (3h)** | 1,461 | Open-Meteo ERA5 | 3-hour precipitation accumulation ($R_{3\text{h}}$) | **0.000 mm** | **0.002 mm** | **-0.000 mm** | **VALIDATED** |
| **Continuous Flood Depth ($m$)** | 0 | None (Data Void) | Physical floodwater depth above ground | **None** | **None** | **None** | **AUDITED DATA LIMITATION: Zero ground-truth measurements exist.** |
| **In-Situ River Stage ($m$)** | 0 | Nepal DHM 695 | Chatara gauge water elevation | **None** | **None** | **None** | **EXTERNAL GAP: REST API telemetry unavailable.** |

---

## 5. Data Coverage and Operational Limitations

1. **Chronological Coverage**: Evaluated across 1,464 consecutive hourly timestamps representing peak monsoon runoff (August 1 to September 30, 2024).
2. **Missing Input Resilience**: If live inputs are dropped, models refuse to output false low risk, emitting `data_quality: "UNAVAILABLE"`.
3. **Class Imbalance**: High and Critical flood risk periods comprise ~3.3% of the held-out test split. The models demonstrate high specificity (>99.7%) and balanced sensitivity.
