# FloodLens AI — Day 2 Engineering Report (Member 3: AI/ML)

**Engineer**: Senior Machine Learning Engineer, Geospatial Data Scientist, Python Developer  
**Module**: Member 3 — AI / ML & Hydrological Risk Baseline  
**Project**: FloodLens AI  
**Date**: October 19, 2026  
**Status**: All Day 2 Deliverables Implemented, Verified, and Documented  

---

## 1. Executive Summary

Building upon the Day 1 foundation, Day 2 focused on operationalizing real open-access hydrological reanalysis feeds, building feature engineering pipelines, training multi-horizon risk models on genuine monsoon time-series, comparing models against dummy baselines, and maintaining strict schema compatibility with the backend `POST /api/v1/predictions/ingest` contract.

### Key Deliverables Completed:
1. **Open-Access Reanalysis Data Ingestion (`ml/src/data_ingestion.py`)**:
   - Automated ingestion of ECMWF ERA5 hourly atmospheric variables (precipitation, temperature, relative humidity, reference evapotranspiration ET0) via Open-Meteo Historical Weather API.
   - Ingestion of GloFAS daily river discharge reanalysis via Open-Meteo Flood API.
   - Benchmarked at Sapta Koshi Chatara Gorge (DHM Station 695: Lat 26.87°N, Lon 87.16°E, EPSG:4326).
   - Ingestion provenance records generated with full API parameters, fetch timestamps, license attribution (CC BY 4.0), and data quality validation warnings.
2. **Reanalysis Labeling Engine (`ml/src/reanalysis_labeling.py`)**:
   - Implemented a defensible, rainfall-dominant 4-tier labeling strategy designed specifically for reanalysis regimes where in-situ DHM river stage (m) is unavailable.
   - Grounded in Nepal Department of Hydrology & Meteorology (DHM), National Disaster Risk Reduction & Management Authority (NDRRMA), and NRRC Flash Flood Guidelines (150 mm/24h extreme threshold).
   - Formulated data-driven GloFAS percentile thresholds (p75, p90, p95) computed strictly on training splits to prevent data scale distortion.
   - Shifted multi-horizon target labels (+1h, +3h, +6h) with strict temporal leakage prevention.
3. **Feature Engineering Pipeline**:
   - Multi-scale rolling precipitation accumulations: 3-hour, 6-hour, and 24-hour windows.
   - Season classification (`monsoon`, `pre_monsoon`, `post_monsoon`).
   - Catchment saturation index (`saturated`, `wet`, `normal`).
   - Forward NWP forecast precipitation proxy.
4. **Model Training & Comparison (`era5-v1`)**:
   - Trained multi-horizon Random Forest models on 5,856 hourly monsoon records spanning 2017 and 2024.
   - Chronological split: 75% train (4,392 samples: June 1, 2017 to July 31, 2024), 25% test (1,464 samples: August 1, 2024 to September 30, 2024).
   - Rigorous comparison against `DummyClassifier(strategy="prior")`:
     - **+1h Horizon**: Random Forest Macro-F1 = **0.9095** (vs Dummy = **0.2379**; Balanced Accuracy = 0.9080 vs 0.2500)
     - **+3h Horizon**: Random Forest Macro-F1 = **0.8637** (vs Dummy = **0.2379**; Balanced Accuracy = 0.8601 vs 0.2500)
     - **+6h Horizon**: Random Forest Macro-F1 = **0.8096** (vs Dummy = **0.2379**; Balanced Accuracy = 0.8038 vs 0.2500)
5. **Prediction Service & Backend Compatibility (`ml/src/predict.py`)**:
   - Updated `FloodRiskPredictor` to seamlessly support both `baseline-v1` (synthetic demo) and `era5-v1` (reanalysis prototype).
   - Enforced safety guards against missing feeds: emits `data_quality: "UNAVAILABLE"` and `risk_level: "unknown"` if essential inputs are missing, strictly preventing false low-risk outputs.
   - Formatted output payloads validated directly against FastAPI backend `ForecastIngestRequest` schema.
6. **Automated Testing & CI**:
   - Expanded test suite from 20 to **68 passing tests** covering timestamp validation, physical limits, location bounds, missingness, provenance, feature engineering, reanalysis labeling, leakage prevention, model reproducibility, and backend contract validation.
   - Created GitHub Actions CI workflow (`.github/workflows/ml-tests.yml`) testing Python 3.11 and 3.12.

---

## 2. Reanalysis Data Ingestion & Provenance Matrix

| Source / Feed | Spatial Resolution | Temporal Resolution | Variables Extracted | License | Limitations Documented |
|---|---|---|---|---|---|
| **ECMWF ERA5** (via Open-Meteo) | ~25 km grid cell | Hourly | Precipitation, Temp 2m, RH 2m, ET0 | CC BY 4.0 | Coarse grid cell average; smooths out localized mountain cloudbursts. |
| **Copernicus GloFAS** (via Open-Meteo) | 0.05° (~5 km) | Daily | River discharge ($Q$ in $\text{m}^3/\text{s}$) | CC BY 4.0 | Hydrological model estimate, not direct in-situ gauge measurement. |
| **Nepal DHM Chatara Gauge (Station 695)** | Point (26.87°N, 87.16°E) | Hourly | River stage ($W$ in meters) | Official Gov | **EXTERNAL BLOCKER**: Automated public REST API is unavailable. `river_stage_m` marked NaN in reanalysis feeds. |

---

## 3. Reanalysis Labeling Strategy Formulation

Because in-situ river stage is unavailable via open automated APIs, the Day 2 pipeline implements a **rainfall-dominant labeling strategy** grounded in documented disaster management standards for the Nepal Terai:

$$\text{Risk Tier} = \begin{cases}
\text{CRITICAL (3)}, & \text{if } R_{24\text{h}} \ge 150\text{ mm} \;\lor\; (Q \ge Q_{p95} \land R_{24\text{h}} \ge 100\text{ mm}) \\
\text{HIGH (2)}, & \text{if } R_{24\text{h}} \ge 100\text{ mm} \;\lor\; (Q \ge Q_{p90} \land R_{24\text{h}} \ge 25\text{ mm}) \;\lor\; (R_{1\text{h}} \ge 15\text{ mm} \land R_{3\text{h}} \ge 30\text{ mm}) \\
\text{MODERATE (1)}, & \text{if } R_{24\text{h}} \ge 25\text{ mm} \;\lor\; Q \ge Q_{p90} \\
\text{LOW (0)}, & \text{otherwise}
\end{cases}$$

### Physical and Regulatory Justification:
- **$150\text{ mm} / 24\text{h}$ Critical Threshold**: Aligned with the Nepal Risk Reduction Consortium (NRRC) Flash Flood Guidelines (2019) and NDRRMA extreme rainfall classification for southern Terai districts.
- **$100\text{ mm} / 24\text{h}$ High Threshold**: Aligned with NDRRMA orange alert criteria for severe waterlogging and tributary swelling.
- **$25\text{ mm} / 24\text{h}$ Moderate Threshold**: NDRRMA yellow alert advisory threshold for monsoon watch.
- **Relative Discharge Percentiles ($Q_{p90}, Q_{p95}$)**: Because GloFAS discharge values represent grid-cell model estimates rather than DHM Chatara gauge magnitudes, percentile thresholds computed strictly on the training partition are used rather than arbitrary fixed volume cutoffs.

---

## 4. Multi-Horizon Model Performance Comparison

The table below summarizes out-of-sample evaluation metrics on the held-out test split (August 1 to September 30, 2024, 1,464 hourly samples) for `era5-v1`:

| Metric | Horizon +1h | Horizon +3h | Horizon +6h | Reference Baseline (Dummy) |
|---|---|---|---|---|
| **Model Type** | Random Forest (`n=100, d=6`) | Random Forest (`n=100, d=6`) | Random Forest (`n=100, d=6`) | DummyClassifier (`strategy="prior"`) |
| **Macro-F1 Score** | **0.9095** | **0.8637** | **0.8096** | 0.2379 |
| **Balanced Accuracy** | **0.9080** | **0.8601** | **0.8038** | 0.2500 |
| **Low-Risk Class F1** | 0.9906 | 0.9857 | 0.9822 | 0.9515 |
| **Moderate-Risk Class F1** | 0.8525 | 0.8041 | 0.7200 | 0.0000 |
| **High-Risk Class F1** | 0.8421 | 0.7778 | 0.6897 | 0.0000 |
| **Critical-Risk Class F1** | 0.9529 | 0.8870 | 0.8468 | 0.0000 |
| **Test Sample Count** | 1,464 | 1,464 | 1,464 | 1,464 |
| **Training Sample Count** | 4,392 | 4,392 | 4,392 | 4,392 |

> [!NOTE]
> Macro-F1 decreases smoothly from 0.9095 at +1h to 0.8096 at +6h. This graceful performance decay over increasing lead times matches hydrological physical expectations: longer prediction horizons entail greater atmospheric and hydrological uncertainty.

---

## 5. Model Limitations & Safety Guarantees

1. **Reanalysis vs. Real In-Situ Observations**:
   - ERA5 and GloFAS are reanalysis products, not in-situ gauge telemetry.
   - All `era5-v1` artifacts are permanently flagged with `is_reanalysis_data: true` and labeled with:  
     `"RESEARCH PROTOTYPE: Model trained on open-access ERA5 reanalysis precipitation and GloFAS discharge proxy data. Not validated against in-situ Nepal DHM gauge observations."`
2. **Missing Input Fail-Safe**:
   - If critical hydrological feeds (`river_stage_m`, `rainfall_rolling_24h_mm`, `rainfall_mm`) drop out, `predict.py` emits `data_quality: "UNAVAILABLE"` and `risk_level: "unknown"`. Under no circumstances is a false low-risk result emitted.
3. **No Direct Citizen Alert Triggering**:
   - All prediction outputs default to `mode: "historical_demo"` and require authority approval before triggering alert dispatches.

---

## 6. External Blockers

| Blocker | Affected Scope | Root Cause | Workaround / Mitigation |
|---|---|---|---|
| **DHM Real-Time Gauge API** | Real river stage ($W_t$) in meters | Nepal DHM `hydrology.gov.np` operates web portal graphs but lacks an open authenticated REST API for machine ingestion. | Ingested open-access ERA5 hourly rainfall and GloFAS discharge as reanalysis proxies. In-situ gauge CSV import pipeline is ready as soon as historical station CSVs are released. |
| **Koshi Barrage Sluice Gate Telemetry** | Barrage backwater curve | India-Nepal Joint Water Commission operates Koshi Barrage; real-time gate logs are manual paper/phone records. | Structured schema accommodates gate count feature whenever manual authority logs are entered. |
