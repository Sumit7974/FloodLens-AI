# Data Inventory and Historical Flood Audit — FloodLens AI

**Module**: Member 3: AI/ML  
**Study Case Area**: Sapta Koshi River Basin — Barahachhetra / Chatara, Sunsari District, Nepal Terai  
**Reference Flood Event**: August 2017 Terai Flood & August 2024 Monsoon High-Flow Episode  
**Coordinates**: Lat 26.55°N – 26.88°N, Lon 86.80°E – 87.30°E (WGS 84 / EPSG:4326)  
**Status**: Day 1 Audit Complete  

---

## 1. Study Area and Historical Event Selection Rationale

### Geographic Focus: The Koshi River Gorge-to-Plains Transition
The **Sapta Koshi River** represents Nepal's largest river basin, draining an area of approximately $60,400\text{ km}^2$ across eastern Nepal and southern Tibet. At **Chatara** (Barahachhetra Municipality, Sunsari District, Koshi Province), the river debouches from the steep Himalayan foothills into the flat, alluvial Nepal Terai floodplain. 

This location was selected for the FloodLens AI pilot because:
1. **Critical Hydrological Choke Point**: Chatara acts as the unified outflow point for seven major mountain tributaries (Sun Koshi, Dudh Koshi, Tama Koshi, Indravati, Likhu, Arun, and Tamor). Flood waves traveling down the Chatara gorge reach downstream Terai settlements within **1 to 6 hours**, making +1h, +3h, and +6h prediction horizons operationally vital.
2. **Benchmark Monitoring Infrastructure**: Chatara hosts Nepal DHM's flagship hydrological gauging station (Station ID: 695 / Chatara Gauge), providing established historical stage and discharge records.
3. **High Settlement Vulnerability**: Downstream areas including Barahachhetra Ward 2, Prakashpur, Mahendranagar, and the Koshi Tappu buffer zones experience chronic inundation, embankment scour, and flash flood surges.
4. **Alignment with Team Assets**: Member 2 (GIS/Satellite) and backend contracts specifically reference `evt_nepal_terai_koshi` and `loc_barahachhetra_w2` (`docs/INTEGRATION_CONTRACTS_DAY2.md`).

---

## 2. Authoritative Data Feeds Audit

### Summary Matrix of Audited Feeds

| # | Feed Name | Source / Provider | Temporal Coverage | Update Frequency | Data Quality Status | Ground-Truth Verification |
|---|---|---|---|---|---|---|
| **1** | River Water Level & Discharge | Nepal DHM Flood Forecasting Division (`hydrology.gov.np`) | Historical archives (1980–present); real-time telemetry | 10 to 60 minutes | **PARTIAL** | Verified benchmark station (Chatara 695); telemetry delays during cloudbursts. |
| **2** | Catchment Precipitation | Nepal DHM Rain Gauge Network (Chatara, Dharan, Biratnagar) | Historical daily/hourly; automated telemetry | 10 to 60 minutes | **PARTIAL** | High spatial sparsity in steep upstream terrain; localized convective cells missed. |
| **3** | Numerical Weather Prediction (NWP) | NOAA Global Forecast System (GFS) & ECMWF | Archived runs; 0.25° grid (~25 km) | 6-hourly cycles (out to 240h) | **AVAILABLE** | Readily accessible via Open-Meteo / NOAA archives; spatial resolution coarse for mountain valleys. |
| **4** | Dam & Barrage Control Notices | Koshi Barrage Control Room (Bhimnagar / Joint Indo-Nepal Committee) | Event-driven bulletins | Irregular / Event-driven | **UNAVAILABLE (Automated API)** | Only published as PDF/manual radio notices during emergencies; no public REST API. |
| **5** | Terrain & Drainage Elevation | Copernicus DEM GLO-30 / SRTM 30m | Static (2020 / 2000) | Static | **AVAILABLE** | High reliability, 30m vertical resolution; misses fine localized Terai drainage ditches. |
| **6** | Historical Inundation Labels | Dartmouth Flood Observatory (DFO) / Copernicus EMS | Episodic event activations | Per major disaster event | **PARTIAL** | Optical cloud occlusion frequently masks flood crest; radar SAR required. |
| **7** | Synthetic Demonstration Feed | FloodLens AI Pipeline Generator (`ml/src/label_builder.py`) | 240 hourly steps (10 days) | On-demand (deterministic seed) | **AVAILABLE (Synthetic Test)** | Physically consistent simulation for software testing; NOT real ground-truth. |

---

## 3. Detailed Data Inventory by Feed

### Feed 1: River Water Level and Discharge (Sapta Koshi at Chatara)
* **Agency**: Department of Hydrology and Meteorology (DHM), Government of Nepal
* **Official URL**: [https://hydrology.gov.np](https://hydrology.gov.np)
* **Benchmark Station**: Sapta Koshi at Chatara (Station ID: 695)
* **Coordinates**: Lat 26.87°N, Lon 87.16°E, Elevation ~140 m MSL
* **Available Columns & Units**:
  * `timestamp` (UTC / Nepal Standard Time +05:45)
  * `river_stage_m` (Water Level in meters above gauge datum)
  * `rate_of_rise_m_per_h` (Derived first derivative $\Delta \text{stage}/\Delta t$)
  * `upstream_discharge_m3s` (Discharge in cubic meters per second $\text{m}^3/\text{s}$, derived from DHM rating curve)
  * `flood_status` (Normal, Alert, Warning, Danger)
* **Official DHM Warning Thresholds**:
  * **Warning Level**: $6.0\text{ m}$ (advisory SMS alerts dispatched to Sunsari / Saptari districts)
  * **Danger Level**: $7.0\text{ m}$ (evacuation directives, coordination with Koshi Barrage)
  * **Critical Historical Peak**: $> 8.0\text{ m}$ (extreme discharge exceeding $9,000\text{ m}^3/\text{s}$)
* **Missing Data & Quality Issues**:
  * Telemetry dropout rate during severe monsoon storms: approximately $8\%\text{--}18\%$.
  * Riverbed aggradation: extreme annual sediment loads (~100 million tonnes) shift cross-sectional stage-discharge relationships, requiring periodic datum recalibration.
* **License & Access**: Public view via web portal; automated historical bulk extraction requires formal DHM research request or scraping.

### Feed 2: Surface Precipitation Observations
* **Agency**: Nepal DHM Automated Weather Station (AWS) Network
* **Stations**: Chatara (ID 1204), Dharan (ID 1206), Biratnagar Airport (ID 1211)
* **Available Columns & Units**:
  * `rainfall_mm` (Hourly rainfall accumulation in millimeters)
  * `rainfall_rolling_3h_mm`, `rainfall_rolling_6h_mm`, `rainfall_rolling_24h_mm` (Rolling sums)
  * `temperature_c` (Dry bulb temperature in Celsius)
  * `relative_humidity_pct` (Relative humidity $0\%\text{--}100\%$)
* **Data Quality Issues**:
  * Extreme rainfall events occasionally saturate tipping-bucket collectors, resulting in under-measurement.
  * Spatial sparsity: Convective cloudbursts in upstream mountain catchments often miss gauge footprints entirely.

### Feed 3: Weather Forecast Precipitation (Numerical Weather Prediction)
* **Provider**: ECMWF IFS / NOAA GFS via Open-Meteo Historical Forecast API
* **Grid Resolution**: $0.25^\circ \times 0.25^\circ$ (~28 km)
* **Available Columns**:
  * `forecast_precip_next_1h_mm`, `forecast_precip_next_3h_mm`, `forecast_precip_next_6h_mm`
  * `wind_speed_10m_kmh`, `surface_pressure_hpa`
* **Data Quality Issues**:
  * Coarse spatial resolution causes orographic precipitation in steep Terai foothills to be smoothed out.
  * Must be treated as a predictor with documented uncertainty, not ground truth.

### Feed 4: Koshi Barrage & Reservoir Operations
* **Responsible Authority**: Koshi Barrage Control (Joint Nepal–India Committee; Bihar Water Resources Department)
* **Location**: Bhimnagar (approx. 45 km downstream of Chatara, near Nepal-India border)
* **Infrastructure**: 56 radial gates across 1,150 m barrage structure.
* **Available Parameters**:
  * `gates_open_count` ($0\text{ to }56$)
  * `downstream_release_cusecs` / `downstream_release_m3s`
* **Current Status**: **UNAVAILABLE VIA AUTOMATED FEED**. Bulletins are communicated via telephone/VHF radio to District Administration Offices (DAO). Day 1 model must operate without live barrage gate telemetry.

---

## 4. Distinction Between Verified Historical Data and Synthetic Test Data

To prevent misleading claims or algorithmic hallucination:

1. **Synthetic Demonstration Data (`ml/data/synthetic/synthetic_koshi_event.csv`)**:
   - Generated by `ml/src/label_builder.py` using physical hydrological principles (baseflow + synthetic storm pulse + runoff convolution + rating curve).
   - Fully labeled with `is_synthetic = True` and `mode = "historical_demo"`.
   - Used strictly to validate data cleaning, feature engineering, pipeline orchestration, model serialization, and backend contract compliance.
   - **Metrics from this data represent pipeline execution tests, NOT real-world predictive skill.**

2. **Real-World Historical Data Requirements for Validation**:
   - Continuous 10-minute DHM Chatara gauge records spanning June–September 2017 and July–August 2024.
   - Sentinel-1 SAR backscatter difference water masks for cloud-occluded dates.
   - Inundation ground-truth surveyed by Sunsari District Emergency Operation Center (DEOC).
