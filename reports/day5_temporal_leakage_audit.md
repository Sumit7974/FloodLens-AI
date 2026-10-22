# FloodLens AI — Day 5 Temporal Data-Leakage Audit Report

**Module**: Member 3 — AI / ML & Geospatial Hydrological Engineering  
**Project**: Chetna: AI-Powered Predictive Flood Monitoring and Early Warning System  
**Date**: 2026-10-21  
**Audit ID**: `audit_leakage_20261021_175236`  
**Overall Verdict**: **LEAKAGE_IDENTIFIED_AND_DOCUMENTED: 2 features contain temporal lookahead in reanalysis feeds (forecast_precip_next_3h_mm shifted future rain; upstream_discharge_m3s same-day calendar aggregation). Corrective actions specified for Day 5 offline retraining.**  

---

## 1. Executive Summary

In compliance with Day 5 instructions, a rigorous temporal data-leakage audit was conducted across every feature and preprocessing transformation in the FloodLens AI pipeline. Each feature was tested against the fundamental operational principle of predictive early warning:

> [!IMPORTANT]
> **Core Temporal Integrity Rule**: Every piece of information ingested into a forecast issued at timestamp $t$ must have been physically observable and available at or before $t$ ($t_{\text{obs}} \le t_{\text{issue}}$).

Of the 12 features audited:  
- **PASS**: **10 features** strictly observe temporal sequence.  
- **FAIL**: **2 features** were identified as containing retrospective lookahead or intra-day aggregation leakage in the historical reanalysis proxy dataset.  
- **UNVERIFIED**: **0 features**.  

---

## 2. Comprehensive Feature-by-Feature Temporal Audit

| Feature Name | Source | Observation Time vs. Issuance $t$ | Leakage Status | Category | Explanation & Evidence |
|---|---|---|---|---|---|
| `rainfall_mm` | ECMWF ERA5 hourly reanalysis via Open-Meteo Historical Weather API | Hour [t-1, t] precipitation accumulation | **PASS** | `NONE` | Represents backward-looking hourly precipitation. At forecast time t, the preceding hour is complete and fully recorded. No forward-looking information is referenced. |
| `rainfall_rolling_3h_mm` | Pandas rolling sum: merged['rainfall_mm'].rolling(3).sum() | 3-hour window [t-2, t] | **PASS** | `NONE` | Rolling window uses standard backward aggregation over indices i-2, i-1, i. All constituent measurements precede or coincide with issuance timestamp t. |
| `rainfall_rolling_6h_mm` | Pandas rolling sum: merged['rainfall_mm'].rolling(6).sum() | 6-hour window [t-5, t] | **PASS** | `NONE` | Standard backward rolling sum over the preceding 6 hours. Contains zero post-issuance observations. |
| `rainfall_rolling_24h_mm` | Pandas rolling sum: merged['rainfall_mm'].rolling(24).sum() | 24-hour synoptic window [t-23, t] | **PASS** | `NONE` | Standard backward rolling accumulation over the preceding 24 hours. Accurately reflects antecedent moisture conditions at time t. |
| `temperature_c` | ECMWF ERA5 2-meter air temperature | Instantaneous value at timestamp t | **PASS** | `NONE` | Represents ambient air temperature at time t. Fully observable at issue time. |
| `relative_humidity_pct` | ECMWF ERA5 2-meter relative humidity | Instantaneous value at timestamp t | **PASS** | `NONE` | Represents atmospheric relative humidity at time t. Fully observable at issue time. |
| `season` | Deterministic calendar mapping: month of timestamp t | Calendar date of timestamp t | **PASS** | `NONE` | Derived strictly from the month index of timestamp t. Known prior to issuance. |
| `catchment_saturation_class` | Binned classification of rainfall_rolling_24h_mm at timestamp t | Derived from 24h antecedent rainfall [t-23, t] | **PASS** | `NONE` | Calculated strictly from antecedent rolling rainfall. No future data is accessed. |
| `river_stage_m` | Nepal DHM Chatara Station 695 specification (all NaN in reanalysis) | Gauge stage at timestamp t | **PASS** | `UNOBSERVED_DATA` | Feature contains exclusively NaN values in historical reanalysis feeds. No post-event or future water levels exist in this column. Imputed via training median. |
| `river_stage_rate_of_rise_m_per_h` | First difference: (stage_t - stage_{t-1}) / 1h (all NaN in reanalysis) | Backward difference between t-1 and t | **PASS** | `UNOBSERVED_DATA` | Backward finite difference. All values are NaN in reanalysis proxy feeds. Zero leakage. |
| `upstream_discharge_m3s` | Copernicus GloFAS daily river discharge merged via dt.normalize() | Full calendar day D (00:00 to 23:59 UTC aggregate) | **FAIL** | `INTRA_DAY_AGGREGATION_LEAKAGE` | EVIDENCE CONFIRMED: In data_ingestion.py lines 330–338, GloFAS daily discharge is joined by calendar date D. For an early morning forecast issued at 02:00 UTC on date D, the daily GloFAS value incorporates upstream runoff that occurs across afternoon and evening hours of date D. At 02:00 UTC, the full-day discharge is physically unobserved in real time. |
| `forecast_precip_next_3h_mm` | data_ingestion.py line 356: rainfall_rolling_3h_mm.shift(-3) | Future window [t, t+3h] actual precipitation | **FAIL** | `LOOKAHEAD_TARGET_LEAKAGE` | EVIDENCE CONFIRMED: In data_ingestion.py lines 353–358, this feature was synthesized via merged['rainfall_rolling_3h_mm'].shift(-3). At timestamp t, actual precipitation that falls between t and t+3h is physically in the future and strictly unobservable. Providing the exact observed future rainfall gives the model a retrospective lookahead oracle, which violates early warning operational reality. |

---

## 3. Deep-Dive on Identified Temporal Leakages

### 3.1 Leakage 1: `forecast_precip_next_3h_mm` (Lookahead Future Outcome Leakage)
- **Code Origin**: [`ml/src/data_ingestion.py:L356`](file:///c:/Users/Priyanshi/FloodLens-AI/ml/src/data_ingestion.py#L356)
  ```python
  merged["forecast_precip_next_3h_mm"] = (
      merged["rainfall_rolling_3h_mm"].shift(-3).round(2)
  )
  ```
- **Why It Leaks**: Shifting future observed rainfall by `-3` hours injects the exact future rainfall that will fall between $t$ and $t+3\text{h}$ into the feature vector at time $t$. In real-time flood early warning, future actual precipitation is unobserved.
- **Corrective Action for Day 5 Retraining Experiment**: Completely remove `forecast_precip_next_3h_mm` from the candidate model feature vector, forcing the model to learn flood risk solely from physically available antecedent memory.

### 3.2 Leakage 2: `upstream_discharge_m3s` (Intra-Day Daily Aggregation Leakage)
- **Code Origin**: [`ml/src/data_ingestion.py:L330-L338`](file:///c:/Users/Priyanshi/FloodLens-AI/ml/src/data_ingestion.py#L330-L338)
  ```python
  merged["date"] = merged["timestamp"].dt.normalize()
  merged = merged.merge(glofas_clean, on="date", how="left")
  ```
- **Why It Leaks**: GloFAS reanalysis provides daily aggregate discharge for date $D$. Merging on calendar date assigns the full day's discharge to morning hours (e.g. 02:00 AM). In reality, upstream flow that occurs later in the afternoon/evening of date $D$ cannot be known at 02:00 AM.
- **Corrective Action for Day 5 Retraining Experiment**: Apply a 1-day lag (`shift(24)`) so that only completed discharge from day $D-1$ is ingested at issuance time $t$.

---

## 4. Preprocessing & Split Integrity Audit

- **Status**: **PASS**
- **Audit Evidence**: In train_baseline.py lines 161–162, the ColumnTransformer (SimpleImputer and StandardScaler) is fitted strictly on X_train. X_test is transformed via model_pipeline.predict(X_test). Zero test set statistical parameters (mean, median, standard deviation) leak into training.
- **Data Normalization**: Scaling and imputation are fitted strictly on `X_train`. No test set distributions leak into feature scaling.
- **Chronological Partitioning**: Training, validation, and test splits respect strict chronological order ($T_{\text{train}} < T_{\text{val}} < T_{\text{test}}$), preventing shuffle leakage across time-series.

---

## 5. Audit Recommendations & Corrective Roadmap

- **1. Remove forecast_precip_next_3h_mm in leak-free candidate model experiment (candidate-leakfree-v1).**
- **2. Apply a 24-hour lag (shift(+24)) to GloFAS daily discharge to ensure strictly antecedent observations.**
- **3. Keep frozen baseline (era5-v1) intact to serve as transparent benchmark of lookahead impact.**
- **4. Verify that preprocessing (scaling, imputation) remains 100% isolated to training splits.**

---

## 6. Execution Command

To re-run the programmatic temporal leakage audit at any time:
```powershell
python ml/src/leakage_audit.py
```
