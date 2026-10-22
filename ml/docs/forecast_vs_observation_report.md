# FloodLens AI — Forecast vs. Observation Comparison Report

**Module**: Member 3 — AI / ML & Geospatial Engineering  
**Project**: FloodLens AI / Chetna Early Warning System  
**Date**: October 21, 2026  
**Status**: Executed & Verified on Chronological Held-Out Test Split (August 1 to September 30, 2024)  
**Study Area**: Sapta Koshi Basin — Barahachhetra Ward 2 / Chatara Gauge (Station 695: 26.87°N, 87.16°E)  
**Evaluated Models**: Baseline Random Forest (`era5-v1`) & Candidate Gradient Boosting (`candidate-v2`)  

---

## 1. Matching Methodology & Integrity Controls

To evaluate forecast accuracy without data leakage or chronological distortion:

1. **Strict Held-Out Isolation**:
   - Evaluation is conducted exclusively on the final **25% chronological held-out test split** spanning **August 1, 2024 00:00:00 UTC to September 30, 2024 23:00:00 UTC** ($1,464\text{ hourly records}$).
   - Training records (June 1, 2017 to July 31, 2024; $4,392\text{ samples}$) are strictly segregated and never evaluated as test instances.
2. **Lead-Time Alignment**:
   - A forecast issued at timestamp $t$ with lead time $h \in \{1, 3, 6\}$ hours is matched with the ground-truth observation valid at:
     $$\text{valid\_at} = t + h\text{ hours}$$
   - Concordance is evaluated between the predicted risk at $(t, +h)$ and the observed risk label at $(t + h)$.
3. **Boundary Condition & Unmatched Records Audit**:
   - At the tail boundary of the dataset, forecasts issued during the last $h$ hours have target timestamps exceeding the dataset end date (`2024-09-30 23:00 UTC`).
   - These instances lack subsequent observations and are explicitly categorized as **unmatched boundary records** rather than being dropped silently or filled with fabricated data.
4. **Distinction of Data Provenance**:
   - **Real Reanalysis Records**: ECMWF ERA5 meteorological variables + Copernicus GloFAS discharge reanalysis (`is_reanalysis: True`, `is_synthetic: False`).
   - **Simulated Sensor Readings**: Parametric synthetic records (`is_synthetic: True`) used in Day 1 component tests are isolated from this evaluation run.

---

## 2. Matching Summary Audit

| Horizon ($+h\text{h}$) | Total Forecasts Issued | Total Observations | Matched Pairs Count | Unmatched Boundary Forecasts | Location Mismatch Rejected | Data Provenance | Matching Status |
|---|---|---|---|---|---|---|---|
| **+1 Hour** | 1,464 | 1,464 | **1,463** | **1** (tail timestamp: `2024-09-30 23:00`) | 0 | Open-Meteo ERA5 + GloFAS Reanalysis | **VERIFIED_MATCHED** |
| **+3 Hours** | 1,464 | 1,464 | **1,461** | **3** (tail timestamps: `21:00`, `22:00`, `23:00`) | 0 | Open-Meteo ERA5 + GloFAS Reanalysis | **VERIFIED_MATCHED** |
| **+6 Hours** | 1,464 | 1,464 | **1,458** | **6** (tail timestamps: `18:00` to `23:00`) | 0 | Open-Meteo ERA5 + GloFAS Reanalysis | **VERIFIED_MATCHED** |

---

## 3. Matched Paired Records Sample (from Real Held-Out Test Data)

The following excerpt demonstrates real-world timestamp matching from `ml/reports/forecast_vs_observation_report.json`:

```text
Record ID        Issued Timestamp (UTC)   Valid/Observed (UTC)     Pred Risk   Obs Risk   Delta   Concordance
----------------------------------------------------------------------------------------------------------------
pair_h1_00000    2024-08-01 00:00:00+00   2024-08-01 01:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00001    2024-08-01 01:00:00+00   2024-08-01 02:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00002    2024-08-01 02:00:00+00   2024-08-01 03:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00003    2024-08-01 03:00:00+00   2024-08-01 04:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00004    2024-08-01 04:00:00+00   2024-08-01 05:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00005    2024-08-01 05:00:00+00   2024-08-01 06:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00006    2024-08-01 06:00:00+00   2024-08-01 07:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00007    2024-08-01 07:00:00+00   2024-08-01 08:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00008    2024-08-01 08:00:00+00   2024-08-01 09:00:00+00   LOW         LOW        0       EXACT_MATCH
pair_h1_00009    2024-08-01 09:00:00+00   2024-08-01 10:00:00+00   LOW         LOW        0       EXACT_MATCH
```

---

## 4. Data-Quality Issues Identified

During the automated matching workflow, three specific data-quality characteristics were audited:

1. **In-Situ River Stage Null Gap**:
   - `river_stage_m` is `NaN` across all 1,464 test instances because the Nepal Department of Hydrology & Meteorology (DHM) Chatara Station 695 has no public REST API.
   - Handled via `SimpleImputer(strategy="median")` in the pipeline and supplemented with GloFAS river discharge ($Q$ in $\text{m}^3/\text{s}$).
2. **Unobserved Continuous Flood Depth**:
   - No ground-truth depth observations exist. The pipeline refused to pair continuous depth targets, recording the limitation transparently.
3. **Class Imbalance in Test Partition**:
   - Out of 1,464 test records:
     - Low Risk ($0$): 1,328 ($90.7\%$)
     - Moderate Risk ($1$): 87 ($5.9\%$)
     - High Risk ($2$): 20 ($1.4\%$)
     - Critical Risk ($3$): 28 ($1.9\%$)
   - Because flood events are rare, standard accuracy ($98.0\%$) is supplemented with Balanced Accuracy ($89.5\%$) and Macro F1 ($0.9095$) to prevent class-imbalance bias.
