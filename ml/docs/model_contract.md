# Model Prediction Interface & Backend Contract — FloodLens AI

**Module**: Member 3: AI/ML  
**Service Version**: `v1.0.0-day1`  
**Contract Alignment**: Synchronized with `backend/app/schemas/forecast.py` and `docs/DATABASE_API_EVENT_CONTRACTS.md`  
**Status**: Frozen & Verified  

---

## 1. Overview and Architectural Role

The FloodLens AI ML prediction module exposes an isolated, stateless prediction interface that consumes hydrological, meteorological, and geospatial feature vectors at time $t$ and produces structured, multi-horizon flood-risk predictions for horizons **+1h, +3h, and +6h**.

Predictions are designed for durable ingestion into the backend via `POST /api/v1/predictions/ingest`, enabling the backend to store predictions in PostgreSQL/PostGIS and emit WebSocket notifications (`risk.updated`) to authority dashboards and citizen applications.

---

## 2. Ingestion Request Contract (Payload from Member 3 to Backend)

### REST Endpoint
* **Path**: `POST /api/v1/predictions/ingest`
* **Alias**: `POST /api/v1/predictions/forecasts`
* **Content-Type**: `application/json`

### JSON Schema

```json
{
  "forecast_id": "fc_koshi_20240815_0600",
  "event_id": "evt_nepal_terai_koshi",
  "location_id": "loc_barahachhetra_w2",
  "issued_at": "2024-08-15T06:00:00Z",
  "mode": "historical_demo",
  "model_version": "baseline-v1",
  "input_data_cutoff_at": "2024-08-15T05:30:00Z",
  "data_quality": "PARTIAL",
  "horizons": [
    {
      "hours": 1,
      "risk_level": "low",
      "calibrated_probability": 0.18
    },
    {
      "hours": 3,
      "risk_level": "moderate",
      "calibrated_probability": 0.52
    },
    {
      "hours": 6,
      "risk_level": "high",
      "calibrated_probability": 0.85
    }
  ],
  "limitations": [
    "Upstream Koshi Chatara DHM gauge telemetry delayed by 45 minutes",
    "Precipitation input derived from GFS 0.25-deg ensemble run"
  ]
}
```

### Field Definitions

| Field Name | Type | Required | Allowed Values / Format | Description |
|---|---|---|---|---|
| `forecast_id` | `string` | Optional | `fc_[a-z0-9_]+` | Unique forecast run ID. Auto-generated as UUID if omitted. |
| `event_id` | `string` | Optional | E.g. `evt_nepal_terai_koshi` | Associated flood event identifier. |
| `location_id` | `string` | **Required** | E.g. `loc_barahachhetra_w2` | Target settlement or administrative ward ID. |
| `issued_at` | `string` | **Required** | ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | Timestamp when the model issued the forecast. |
| `mode` | `string` | **Required** | `historical_demo`, `test`, `live_observation`, `model_estimate` | Operational provenance indicator. Prevents simulated data from appearing as real alerts. |
| `model_version` | `string` | **Required** | E.g. `baseline-v1`, `rf-terai-v1` | Identifier of the fitted ML pipeline artifact. |
| `input_data_cutoff_at` | `string` | Optional | ISO 8601 UTC | Timestamp of the latest sensor reading ingested into the feature vector. |
| `data_quality` | `string` | **Required** | `FULL`, `PARTIAL`, `DEGRADED`, `UNAVAILABLE` | Quality indicator reflecting missingness or telemetry delays. |
| `horizons` | `array[object]`| **Required** | Min items: 1 | Multi-horizon risk items. Must cover at least one of `1`, `3`, `6`. |
| `limitations` | `array[string]`| Optional | Text strings | Documented sensor failures, assumptions, or operational caveats. |

### Horizon Item Schema (`horizons[*]`)

| Field Name | Type | Required | Allowed Values | Description |
|---|---|---|---|---|
| `hours` | `integer` | **Required** | `1`, `3`, `6` (extended: `12`, `24`) | Forecast horizon duration in hours. |
| `risk_level` | `string` | **Required** | `low`, `moderate`, `high`, `critical`, `unknown` | Categorical flood risk severity level. |
| `calibrated_probability` | `float` | Optional | $0.0\text{ to }1.0$ (or `null`) | Model confidence or empirical probability. Set to `null` if uncalibrated. |

---

## 3. Input Feature Schema for Inference (`ml/src/predict.py`)

The inference function `FloodRiskPredictor.predict(features, ...)` accepts a Python dictionary with the following standard features:

```json
{
  "rainfall_mm": 28.5,
  "rainfall_rolling_3h_mm": 64.0,
  "rainfall_rolling_6h_mm": 110.2,
  "rainfall_rolling_24h_mm": 165.4,
  "river_stage_m": 6.85,
  "river_stage_rate_of_rise_m_per_h": 0.35,
  "upstream_discharge_m3s": 7800.0,
  "forecast_precip_next_3h_mm": 35.0,
  "temperature_c": 24.5,
  "relative_humidity_pct": 96.0,
  "season": "monsoon",
  "catchment_saturation_class": "saturated"
}
```

---

## 4. Safety Constraints & Edge-Case Protocols

### 4.1 Strict Prevention of False Low-Risk Outputs
In flood warning systems, **a false negative (falsely predicting `low` risk when data is missing) can lead to loss of life**.
* If critical hydrological inputs (`river_stage_m`, `rainfall_rolling_24h_mm`, `rainfall_mm`) are missing, the predictor **refuses to predict `low`**.
* Instead, it returns:
  * `data_quality: "UNAVAILABLE"`
  * `risk_level: "unknown"`
  * `calibrated_probability: null`
  * `limitations: ["All critical hydrological feeds missing... Cannot infer risk safely."]`

### 4.2 Uncalibrated Probability Safeguard
* Raw classification probabilities from uncalibrated random forests or neural networks reflect decision-tree voting splits, NOT real-world frequentist flood probabilities.
* The system preserves `calibrated_probability: null` unless explicit Platt scaling or isotonic regression has been verified against historical empirical frequencies.

### 4.3 Prohibition of Direct Citizen Actuation
* Experimental baseline predictions must never trigger live sirens, SMS dispatches, or emergency evacuations.
* Predictions in `historical_demo` mode are tagged with `mode: "historical_demo"` and displayed strictly in research/audit views.
