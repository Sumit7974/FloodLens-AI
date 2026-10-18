# FloodLens AI — Member 2, 3, 4 Integration Contracts (Day 2)

**Service Version**: `v1.0.0-day2`  
**Base REST URL**: `http://localhost:8000/api/v1`  
**WebSocket URL**: `ws://localhost:8000/ws/v1/events?token={jwt}`  
**Default Coordinate Reference System**: `EPSG:4326` (WGS 84, Longitude / Latitude)  
**Timestamp Standard**: ISO 8601 in UTC (`YYYY-MM-DDTHH:MM:SSZ` or `+00:00`)  

---

## Architecture Principles for the Team

1. **Durable Database Write First, Event Notification Second**:
   - Every satellite extent mask, scene metadata record, and AI risk forecast run is durably stored in PostgreSQL / PostGIS before emitting a real-time WebSocket event.
   - Frontends receive WebSocket notifications (`flood_extent.updated`, `risk.updated`) containing the `resource_id` and fetch the authoritative state via REST.
2. **Explicit Provenance & Demo Labeling**:
   - All historical Nepal Terai test data MUST be labeled with `mode: "historical_demo"`.
   - Never invent live flood alerts or live emergency data.
   - Limitations (such as offline gauges or uncalibrated runoff models) must be recorded in the `limitations` array.
3. **Role-Based Authorization**:
   - Write endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) require a Bearer token with `authority` or `admin` role.
   - Public inspection endpoints (`GET /predictions/latest`, `GET /predictions/map`, `GET /flood-events/{id}/extent`, `GET /flood-events/{id}/settlements`) are accessible to all authenticated and authorized clients.

---

## 1. Member 2 — Satellite & GIS Pipeline Integration Contract

Member 2 produces optical NDWI/MNDWI water masks from Sentinel-2, SAR change detection from Sentinel-1, georeferenced flood extent polygons, and settlement exposure intersections.

### 1.1 Satellite Scene Ingestion
**Endpoint**: `POST /api/v1/satellite/scenes`  
**Access**: Authority or Admin Bearer Token  
**Summary**: Ingests raw or preprocessed satellite scene metadata.

#### Request Headers
```http
Authorization: Bearer <AUTHORITY_JWT_TOKEN>
Content-Type: application/json
```

#### Request Payload Schema
```json
{
  "id": "S2A_MSIL2A_20240815_T45RVP",
  "provider": "Copernicus",
  "sensor": "Sentinel-2",
  "modality": "optical",
  "captured_at": "2024-08-15T04:45:30Z",
  "cloud_quality": 0.05,
  "asset_ref": "/storage/satellite/scenes/S2A_20240815_koshi.tif",
  "bbox_geojson": {
    "type": "Polygon",
    "coordinates": [
      [
        [86.80, 26.40],
        [87.30, 26.40],
        [87.30, 26.90],
        [86.80, 26.90],
        [86.80, 26.40]
      ]
    ]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Optional | Unique scene identifier. Auto-generated if omitted. |
| `provider` | string | Required | Imagery provider: `ESA`, `Copernicus`, `USGS`. |
| `sensor` | string | Required | Satellite sensor: `Sentinel-2`, `Sentinel-1`, `Landsat-8`. |
| `modality` | string | Required | Imaging modality: `optical` or `sar`. |
| `captured_at` | string (ISO 8601 UTC) | Required | Satellite overpass acquisition timestamp. |
| `cloud_quality` | float (0.0 to 1.0) | Optional | Cloud cover fraction (e.g. 0.05 = 5% cloud cover). |
| `asset_ref` | string | Required | Cloud storage URI or local filepath to raster asset. |
| `bbox_geojson` | object | Optional | GeoJSON Polygon bounding footprint. |

#### Response (`201 Created`)
```json
{
  "id": "S2A_MSIL2A_20240815_T45RVP",
  "provider": "Copernicus",
  "sensor": "Sentinel-2",
  "modality": "optical",
  "captured_at": "2024-08-15T04:45:30Z",
  "cloud_quality": 0.05,
  "asset_ref": "/storage/satellite/scenes/S2A_20240815_koshi.tif",
  "bbox_geojson": { ... },
  "created_at": "2026-10-18T12:00:00Z"
}
```

---

### 1.2 Georeferenced Flood Extent Ingestion
**Endpoint**: `POST /api/v1/flood-events/{event_id}/extent`  
**Access**: Authority or Admin Bearer Token  
**Summary**: Stores satellite-derived flood extent polygons in PostGIS and broadcasts `flood_extent.updated`.

#### Request Payload Schema
```json
{
  "id": "ext_koshi_20240815_opt",
  "observed_at": "2024-08-15T04:45:30Z",
  "method": "MNDWI",
  "area_km2": 38.45,
  "source_scene_ids": ["S2A_MSIL2A_20240815_T45RVP"],
  "confidence": 0.93,
  "polygon_ref": "/storage/extents/koshi_20240815_mndwi.geojson",
  "raster_ref": "/storage/extents/koshi_20240815_mask.tif",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [87.00, 26.55],
        [87.18, 26.55],
        [87.18, 26.78],
        [87.00, 26.78],
        [87.00, 26.55]
      ]
    ]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Optional | Custom extent ID or generated UUID. |
| `observed_at` | string (ISO 8601 UTC) | Required | Satellite observation timestamp. |
| `method` | string | Required | Extraction algorithm: `NDWI`, `MNDWI`, `SAR_CHANGE`. |
| `area_km2` | float (> 0.0) | Required | Inundated surface area in square kilometers. |
| `source_scene_ids`| array[string] | Required | List of source satellite scene IDs used. |
| `confidence` | float (0.0 to 1.0) | Optional | Confidence score of the classification. |
| `polygon_ref` | string | Optional | URI/path to vector artifact. |
| `raster_ref` | string | Optional | URI/path to GeoTIFF raster artifact. |
| `geometry` | GeoJSON object or WKT | Optional | Georeferenced MultiPolygon/Polygon in EPSG:4326. Stored directly in PostGIS. |

#### Response (`201 Created`)
Returns `FloodExtentResponse` including the parsed `geometry` as an RFC 7946 GeoJSON dictionary.

---

### 1.3 Settlement Boundary & Point Ingestion
**Endpoint**: `POST /api/v1/locations`  
**Access**: Authority or Admin Bearer Token  
**Summary**: Ingests mapped settlement points or polygon boundaries for administrative spatial intersection.

#### Request Payload Schema
```json
{
  "id": "loc_barahachhetra_w2",
  "name": "Barahachhetra Ward 2",
  "admin_level": 4,
  "crs_source": "EPSG:4326",
  "metadata_json": {
    "population": 3850,
    "district": "Sunsari",
    "vulnerability_index": 0.78
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [87.05, 26.65],
        [87.12, 26.65],
        [87.12, 26.72],
        [87.05, 26.72],
        [87.05, 26.65]
      ]
    ]
  }
}
```

---

### 1.4 Geospatial Query Endpoints Produced for Clients
Member 2's outputs are instantly queryable through these backend endpoints:

| Method | Path | Output |
|---|---|---|
| `GET` | `/api/v1/flood-events/{event_id}/extent` | Full extent metadata with actual GeoJSON MultiPolygon |
| `GET` | `/api/v1/flood-events/{event_id}/extent/geojson` | Direct RFC 7946 GeoJSON Feature for web maps |
| `GET` | `/api/v1/flood-events/{event_id}/settlements` | Live spatial intersection returning exposed settlements, area, and population |
| `GET` | `/api/v1/flood-events/{event_id}/assets` | Critical asset intersection (exposed roads km, structures count, cropland ha) |
| `GET` | `/api/v1/flood-events/{event_id}/report` | Synthesized flood impact assessment report |

---

## 2. Member 3 — AI / ML & Risk Forecasting Integration Contract

Member 3 implements hydrological risk baselines, processes weather forecast grids, river gauge precursors, and produces multi-horizon predictions for +1h, +3h, and +6h intervals.

### 2.1 Multi-Horizon Forecast Ingestion
**Endpoint**: `POST /api/v1/predictions/ingest`  
**Alias**: `POST /api/v1/predictions/forecasts`  
**Access**: Authority or Admin Bearer Token  
**Summary**: Ingests multi-horizon risk predictions, registers the forecast run, and broadcasts `risk.updated`.

#### Request Payload Schema
```json
{
  "forecast_id": "fc_koshi_20240815_0600",
  "event_id": "evt_nepal_terai_koshi",
  "location_id": "loc_barahachhetra_w2",
  "issued_at": "2024-08-15T06:00:00Z",
  "mode": "historical_demo",
  "model_version": "baseline-v1",
  "input_data_cutoff_at": "2024-08-15T05:30:00Z",
  "data_quality": "partial",
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

| Field | Type | Required | Description |
|---|---|---|---|
| `forecast_id` | string | Optional | Unique forecast run ID. Auto-generated if omitted. |
| `event_id` | string | Optional | Associated flood event ID if tied to an episode. |
| `location_id` | string | Required | Target location / settlement ID. Auto-registers if not yet stored. |
| `issued_at` | string (ISO 8601 UTC) | Required | Model issue timestamp in UTC. |
| `mode` | string | Required | `historical_demo`, `test`, `live_observation`, `model_estimate`. |
| `model_version`| string | Required | Model identifier, e.g. `baseline-v1` or `xgboost-terai-v2`. |
| `data_quality` | string | Required | `full`, `partial`, `degraded`, `unavailable`. |
| `horizons` | array[object] | Required | Must contain at least one core horizon (`1`, `3`, `6` hours). |
| `limitations` | array[string] | Optional | Caveats, missing sensor feeds, or uncertainty notes. |

#### Horizon Item Fields
- `hours`: integer (`1`, `3`, `6`).
- `risk_level`: string (`low`, `moderate`, `high`, `critical`).
- `calibrated_probability`: float (0.0 to 1.0) or null if uncalibrated.

#### Response (`201 Created`)
Conforms to the exact schema defined in `DATABASE_API_EVENT_CONTRACTS.md`:
```json
{
  "forecast_id": "fc_koshi_20240815_0600",
  "location_id": "loc_barahachhetra_w2",
  "issued_at": "2024-08-15T06:00:00Z",
  "mode": "historical_demo",
  "model_version": "baseline-v1",
  "data_quality": "partial",
  "horizons": [
    {"hours": 1, "risk_level": "low", "calibrated_probability": 0.18},
    {"hours": 3, "risk_level": "moderate", "calibrated_probability": 0.52},
    {"hours": 6, "risk_level": "high", "calibrated_probability": 0.85}
  ],
  "limitations": [
    "Upstream Koshi Chatara DHM gauge telemetry delayed by 45 minutes",
    "Precipitation input derived from GFS 0.25-deg ensemble run"
  ]
}
```

---

### 2.2 Database-backed Risk Map Layer API
**Endpoint**: `GET /api/v1/predictions/map`  
**Access**: Public  
**Summary**: Returns synthesized risk zones with multi-horizon predictions and location boundary geometries for map overlays.

#### Response (`200 OK`)
```json
{
  "layer_id": "risk_zones_fc_koshi_20240815_0600",
  "layer_type": "risk_zones",
  "description": "Multi-horizon predicted flood risk zones",
  "crs": "EPSG:4326",
  "active_horizons": [1, 3, 6],
  "issued_at": "2024-08-15T06:00:00Z",
  "model_version": "baseline-v1",
  "mode": "historical_demo",
  "data_quality": "partial",
  "status": "active",
  "total_zones": 1,
  "features": [
    {
      "type": "Feature",
      "id": "loc_barahachhetra_w2",
      "properties": {
        "location_id": "loc_barahachhetra_w2",
        "location_name": "Barahachhetra Ward 2",
        "admin_level": 4,
        "forecast_id": "fc_koshi_20240815_0600",
        "model_version": "baseline-v1",
        "mode": "historical_demo",
        "data_quality": "partial",
        "horizons": {
          "+1h": {"risk_level": "low", "calibrated_probability": 0.18},
          "+3h": {"risk_level": "moderate", "calibrated_probability": 0.52},
          "+6h": {"risk_level": "high", "calibrated_probability": 0.85}
        },
        "max_risk_level": "high"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [ ... ]
      }
    }
  ]
}
```
*Note: If no forecasts have been ingested, this returns `status: "no_data"` and `features: []` rather than a misleading placeholder.*

---

## 3. Member 4 — Web Dashboard & Android App Integration Contract

Member 4 builds the React Authority Command Dashboard and the React Native / Expo Citizen Android application.

### 3.1 Authority Web Application Screens & API Mapping

| Screen | Required Backend API | Description |
|---|---|---|
| **Command Centre** | `GET /api/v1/predictions/map`<br>`GET /api/v1/flood-events` | Active risk layer overlay and ongoing flood event selection. |
| **Prediction Centre** | `GET /api/v1/predictions/latest?location_id={id}`<br>`GET /api/v1/predictions/locations/{id}` | Inspect multi-horizon risk curves (+1h, +3h, +6h) and limitations. |
| **Satellite Intelligence** | `GET /api/v1/satellite/scenes`<br>`GET /api/v1/flood-events/{id}/extent`<br>`POST /api/v1/satellite/jobs` | Before/after imagery comparison and NDWI/MNDWI water extraction job triggers. |
| **Impact Assessment** | `GET /api/v1/flood-events/{id}/settlements`<br>`GET /api/v1/flood-events/{id}/assets`<br>`GET /api/v1/flood-events/{id}/report` | List exposed settlements, inundated roads, cropland damage, and export summary. |

### 3.2 Citizen Android Application Screens & API Mapping

| Screen | Required Backend API | Description |
|---|---|---|
| **My Area** | `GET /api/v1/predictions/latest?location_id={user_loc}` | Shows local risk level, horizon badges (+1h/+3h/+6h), and last update time. |
| **Risk Map** | `GET /api/v1/predictions/map`<br>`GET /api/v1/flood-events/{id}/extent/geojson` | Visual 2D/3D map displaying flood extent and risk boundaries. |
| **Alerts** | `GET /api/v1/alerts?area_id={user_loc}` | Lists officially dispatched authority alerts (drafts are never exposed). |
| **Request Help**| `POST /api/v1/assistance` | Submit emergency assistance request (GPS, category, description). |

---

## 4. Real-Time WebSocket Event Contract

**Connection Endpoint**: `/ws/v1/events?token=<JWT_TOKEN>`

### 4.1 Wire Event Format
```json
{
  "event_id": "evt_extent_ext_koshi_001",
  "type": "flood_extent.updated",
  "timestamp": "2026-10-18T12:05:00Z",
  "location_id": "nepal_terai_koshi",
  "resource_id": "ext_koshi_001",
  "version": 1
}
```

### 4.2 Standard Event Types
- `flood_extent.updated`: Emitted when Member 2 ingests new optical/radar flood extent.
  *Client Action*: Web/Android fetches `GET /api/v1/flood-events/{event_id}/extent` and `/settlements`.
- `risk.updated`: Emitted when Member 3 ingests a new forecast run.
  *Client Action*: Android updates home screen risk banner via `GET /api/v1/predictions/latest?location_id=...`.
- `alert.approved`: Emitted to `authority_queue` channel when officer approves warning.
- `alert.published`: Emitted to public subscribers when test alert is dispatched.
- `assistance.created`: Emitted to authority responders when citizen requests help.

---

## 5. Standard Error Envelope Contract
All client errors (400, 401, 403, 404, 422, 500) strictly conform to the format:
```json
{
  "error": {
    "code": "FORECAST_UNAVAILABLE",
    "message": "No forecast records currently available for location 'loc_xyz'",
    "request_id": "req_a1b2c3d4",
    "details": {}
  }
}
```
Client apps should check `error.code` to render human-friendly fallback UI states (e.g. `DATA_UNAVAILABLE` shows offline/demo banner).
