# Model Limitations, Missing Feeds, and Operational Safeguards — FloodLens AI

**Module**: Member 3: AI/ML  
**Document**: Model Limitations & Operational Safeguards  
**Status**: Day 1 Complete  

---

## 1. Physical and Hydrological Limitations

### 1.1 Lumped Statistical Baseline vs. 2D Hydrodynamic Modeling
The Day 1 baseline model (`baseline-v1`) is a point-based supervised machine-learning classifier (Random Forest) trained on lumped hydrometeorological features at Chatara. 
* **Lack of Hydrodynamic Wave Routing**: The model does not solve the 2D Saint-Venant shallow water equations. It does not account for backwater effects, hydraulic jump dynamics, or localized levee breaches downstream of Chatara.
* **Embankment Breach Vulnerability**: In the Nepal Terai, devastating flood events (such as the infamous August 18, 2008 Koshi breach at Kushaha) can occur at moderate discharge levels ($4,270\text{ m}^3/\text{s}$) due to bank erosion, sediment choking, and structural failure, rather than overtopping alone. Point-based stage prediction cannot detect geotechnical embankment weakening.

### 1.2 Extreme Sediment Transport and Riverbed Aggradation
The Koshi River carries over 100 million tonnes of coarse sediment annually.
* **Datum Instability**: Severe sedimentation alters the cross-sectional geometry of the riverbed between monsoon seasons. A stage reading of $6.0\text{ m}$ in 2017 may correspond to a substantially different volume of discharge than $6.0\text{ m}$ in 2024.
* **Rating Curve Drift**: Static stage-to-discharge equations drift over time and require continuous bathymetric recalibration by DHM technicians.

---

## 2. Missing Data Feeds and Upstream Information Gaps

| Feed | Status on Day 1 | Operational Impact & Blocker | Required Mitigation for Day 2+ |
|---|---|---|---|
| **Koshi Barrage Gate Telemetry** | **UNAVAILABLE** (Manual VHF notices only) | Downstream ponding and backwater levels depend heavily on how many of the 56 gates are open. Lack of automated gate feed causes uncertainty in water elevation downstream of Chatara. | Integrate manual authority override or batch ingestion for barrage gate counts. |
| **Transboundary Upstream Telemetry (Tibet / China)** | **UNAVAILABLE** (No real-time API) | The Arun River, Sun Koshi, and Bhote Koshi have large glaciated catchments in Tibet. Glacial Lake Outburst Floods (GLOFs) or upstream cloudbursts cannot be detected until they reach Nepal border gauges. | Incorporate satellite SAR change detection and regional ICIMOD hydro-meteorological feeds. |
| **Mountain Rain Gauge Sparsity** | **PARTIAL** (Coarse network) | Convective monsoon cloudbursts in the Mahabharat Range often miss rain gauges located in valleys. | Assimilate satellite GPM IMERG precipitation grids alongside surface gauges. |
| **Sub-Daily Inundation Polygons** | **PARTIAL** (Episodic) | Optical satellites (Sentinel-2, Landsat) are blind during monsoon storms due to 100% cloud cover. | Member 2 Sentinel-1 SAR radar water extraction pipeline is mandatory for cloudy periods. |

---

## 3. Statistical Assumptions and Probability Calibration Risks

### 3.1 Uncalibrated Decision Tree Probabilities
* `RandomForestClassifier.predict_proba()` computes the fraction of decision trees voting for a given class. This reflects ensemble margin, not real-world frequentist probability.
* **Risk**: Presenting a raw probability of $0.85$ to disaster managers gives a false impression of mathematical precision. Until isotonic regression or Platt scaling is performed on an independent historical test set, probabilities are marked uncalibrated.

### 3.2 Time-Series Non-Stationarity
* Climate change has intensified high-intensity, short-duration cloudbursts in the eastern Terai. Historical training distributions may underestimate future peak rainfall rates.

---

## 4. Operational Safety Directives

To uphold human safety and avoid panic or liability:

1. **PROHIBITION OF AUTOMATED CITIZEN ALERTS**:
   Under no circumstances shall the Day 1 baseline ML model directly trigger automated push notifications, SMS alerts, or sirens to the public. All alerts must pass through the authority approval gate (`POST /api/v1/alerts/{id}/approve`) defined by Member 1.

2. **PROHIBITION OF FALSE LOW-RISK EMISSION**:
   When upstream gauge telemetry or catchment rainfall feeds drop out, the model must return `data_quality: "UNAVAILABLE"` and `risk_level: "unknown"`. It is forbidden to output `low` risk as a fallback for missing data.

3. **CLEAR DEMO PROVENANCE**:
   All outputs produced from synthetic demonstration datasets must be explicitly flagged with `mode: "historical_demo"`.
