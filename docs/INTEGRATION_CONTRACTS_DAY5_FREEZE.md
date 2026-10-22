# FloodLens AI — Day 5 API Contract Freeze & Integration Specification

**Document Version:** 1.0.0 (Release Candidate Freeze)  
**Author:** Member 1 (Backend & Integration Lead)  
**Branch:** `feature/backend-day5`  
**Target Consumers:** Member 2 (GIS / Satellite Lead), Member 3 (AI/ML Lead), Member 4 (Frontend / Mobile Lead), Operational Authorities  
**Validation Status:** Fully Verified via Pytest Regression Suite, Pyrefly Type Checker (0 errors), Day 3 Demo, and Day 5 Release Candidate Demo (`scripts/demo_day5_backend.py`)

---

## 1. Executive Summary & Core Responsibility Boundary

FloodLens AI is an evidence-based flood intelligence and decision-support platform tailored for Nepal's Terai river basins (focusing on Kamala and Bagmati basins in Dhanusha and Rautahat districts).

> [!IMPORTANT]
> **CRITICAL RESPONSIBILITY BOUNDARY**:
> FloodLens AI collects, organizes, simulates, and communicates flood intelligence to authorities.
> **FloodLens does NOT command, assign, or deploy rescue forces, personnel, or emergency units.**
> All operational dispatch and disaster response actions remain under the sole authority and discretion of government disaster management agencies (National Disaster Risk Reduction and Management Authority - NDRRMA, DHM, Armed Police Force, and local municipal emergency cells).
>
> All alert dispatches in this release are **strictly restricted to historical demonstrations and test sandbox simulations**. Operational public alerts are prohibited by backend software safeguards.

---

## 2. Stable Endpoint Inventory (Frozen Contracts)

All endpoints below are frozen as of Member 1 Day 5. No breaking schema changes, parameter removals, or status code alterations will occur without a formal version bump to `/api/v2`.

| Method | Endpoint Path | Auth Required | Allowed Roles | Description |
|---|---|---|---|---|
| `GET` | `/api/v1/health` | No | Any | System liveness probe & component status |
| `GET` | `/api/v1/ready` | No | Any | Readiness probe checking database connectivity & latency |
| `POST` | `/api/v1/auth/register` | No | Any | Citizen registration with contact consent flag |
| `POST` | `/api/v1/auth/login` | No | Any | User authentication returning JWT bearer token & role |
| `POST` | `/api/v1/auth/refresh` | Yes | Any | Token refresh endpoint |
| `GET` | `/api/v1/auth/me` | Yes | Any | Profile of currently authenticated user |
| `POST` | `/api/v1/locations` | Yes | Authority, Admin | Register/import administrative unit, settlement, or study area |
| `GET` | `/api/v1/locations` | No | Any | List registered locations and administrative boundaries |
| `GET` | `/api/v1/locations/{location_id}` | No | Any | Get single location metadata |
| `POST` | `/api/v1/predictions/ingest` | Yes | Authority, Admin | Ingest ML forecast run with multi-horizon risk predictions |
| `GET` | `/api/v1/predictions/latest` | No | Any | Get latest multi-horizon forecast run for a location |
| `GET` | `/api/v1/predictions/locations/{location_id}` | No | Any | Alias for latest forecast by path parameter |
| `GET` | `/api/v1/predictions/map` | No | Any | Get database-backed GeoJSON risk-zone map layer |
| `POST` | `/api/v1/flood-events` | Yes | Authority, Admin | Register verified historical or active flood event episode |
| `GET` | `/api/v1/flood-events` | No | Any | List flood events filtered by region or mode |
| `GET` | `/api/v1/flood-events/{event_id}` | No | Any | Get specific flood event episode details |
| `POST` | `/api/v1/flood-events/{event_id}/extent` | Yes | Authority, Admin | Ingest satellite-derived flood extent mask polygon |
| `GET` | `/api/v1/flood-events/{event_id}/extent` | No | Any | Get metadata of latest observed flood extent |
| `GET` | `/api/v1/flood-events/{event_id}/extent/geojson`| No | Any | Direct RFC 7946 GeoJSON Feature of observed flood extent |
| `GET` | `/api/v1/flood-events/{event_id}/settlements` | No | Any | Spatial intersection of flood extent and mapped settlements |
| `GET` | `/api/v1/flood-events/{event_id}/assets` | No | Any | Spatial exposure metrics for critical infrastructure |
| `GET` | `/api/v1/flood-events/{event_id}/report` | No | Any | Synthesized impact assessment summary metadata |
| `GET` | `/api/v1/flood-events/{event_id}/report/export` | No | Any | Downloadable physical report export artifact (JSON or CSV) |
| `GET` | `/api/v1/flood-events/{event_id}/timeline` | No | Any | Chronological event replay milestones and coverage |
| `POST` | `/api/v1/alerts` | Yes | Authority, Admin | Create draft alert requiring second-tier review |
| `GET` | `/api/v1/alerts` | Optional | Authority/Admin (full), Public (dispatched only) | List accessible alerts (drafts and demo alerts isolated) |
| `GET` | `/api/v1/alerts/{alert_id}` | Optional | Authority/Admin (full), Public (dispatched only) | Get specific alert by ID with permission checks |
| `POST` | `/api/v1/alerts/{alert_id}/approve` | Yes | Authority, Admin | Review and approve draft alert |
| `POST` | `/api/v1/alerts/{alert_id}/dispatch` | Yes | Authority, Admin | Execute test-only / simulated alert dispatch |
| `POST` | `/api/v1/assistance` | Yes | Any Authenticated | Submit citizen emergency assistance request |
| `GET` | `/api/v1/assistance/mine` | Yes | Any Authenticated | Citizen-specific personal submitted assistance requests |
| `GET` | `/api/v1/assistance` | Yes | Authority, Admin | Authority triage and dispatch review queue |
| `GET` | `/api/v1/assistance/{request_id}` | Yes | Owner Citizen, Authority, Admin | Get single assistance request |
| `PATCH`| `/api/v1/assistance/{request_id}` | Yes | Authority, Admin | Update assistance triage status and assign responder |
| `GET` | `/api/v1/facilities/shelters` | No | Any | Emergency shelters with capacity & verification status |
| `GET` | `/api/v1/facilities/hospitals` | No | Any | Hospitals & clinics with emergency contact & status |
| `POST` | `/api/v1/routes/assess` | No | Any | Spatial hazard intersection screening for candidate route |
| `GET` | `/api/v1/satellite/scenes` | No | Any | List ingested Copernicus Sentinel-1/2 satellite scenes |
| `POST` | `/api/v1/satellite/scenes` | Yes | Authority, Admin | Register raw satellite scene metadata |
| `POST` | `/api/v1/satellite/jobs` | Yes | Authority, Admin | Queue satellite extent processing job |
| `GET` | `/api/v1/satellite/jobs/{job_id}` | No | Any | Status of satellite extent processing job |
| `GET` | `/api/v1/analytics/events/{event_id}` | No | Any | Event evaluation metrics (forecast vs observation) |
| `GET` | `/api/v1/models` | No | Any | List AI/ML models with calibrated status and caveats |
| `POST` | `/api/v1/models/training-jobs` | Yes | Authority, Admin | Truthfully returns 501 Not Implemented (offline training) |
| `WS` | `/ws/v1/events` | Query Param | Any Authenticated | Real-time WebSocket event bus for push notifications |

---

## 3. Authentication & RBAC Contracts

- **Header Format:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
- **Token Algorithm:** HS256
- **Token Claims:** `sub` (user UUID), `role` (`citizen`, `authority`, `admin`), `exp` (UTC timestamp), `iat` (UTC timestamp).
- **Error Status Codes:**
  - `401 Unauthorized`: Token missing, malformed, or expired.
    ```json
    {
      "error": {
        "code": "INVALID_TOKEN",
        "message": "Invalid or expired access token",
        "request_id": "req-1792506899"
      }
    }
    ```
  - `403 Forbidden`: Authenticated user lacks required role (e.g. citizen calling alert creation or authority assistance queue).
    ```json
    {
      "error": {
        "code": "INSUFFICIENT_ROLE",
        "message": "Access restricted to roles: ['authority', 'admin']",
        "request_id": "req-1792506900"
      }
    }
    ```

---

## 4. GIS Data Ingestion Contract (Member 2 Deliverables)

### 4.1 Settlement / Location Ingestion (`POST /api/v1/locations`)
```json
{
  "id": "settlement_janakpurdham",
  "name": "Janakpurdham Sub-Metropolitan",
  "admin_level": 3,
  "parent_id": "terai_dhanusha",
  "crs_source": "EPSG:4326",
  "geometry": {
    "type": "Point",
    "coordinates": [85.9244, 26.7288]
  },
  "metadata_json": {
    "region_id": "terai_dhanusha",
    "population": 195438,
    "vulnerability_score": 0.82
  }
}
```

### 4.2 Observed Flood Extent Ingestion (`POST /api/v1/flood-events/{event_id}/extent`)
- Coordinates must conform to RFC 7946 GeoJSON format: `[longitude, latitude]` in EPSG:4326.
- May provide either GeoJSON dictionary or WKT string (`POLYGON(...)` or `MULTIPOLYGON(...)`).
```json
{
  "observed_at": "2024-07-08T10:15:00Z",
  "method": "SAR_CHANGE",
  "area_km2": 42.6,
  "source_scene_ids": ["S1A_IW_GRDH_1SDV_20240708T1015_NEPAL_TERAI"],
  "confidence": 0.91,
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [85.9100, 26.7150],
        [85.9450, 26.7150],
        [85.9450, 26.7450],
        [85.9100, 26.7450],
        [85.9100, 26.7150]
      ]
    ]
  }
}
```

---

## 5. ML Forecast Ingestion Contract (Member 3 Deliverables)

### 5.1 Multi-Horizon Risk Ingestion (`POST /api/v1/predictions/ingest`)
```json
{
  "forecast_id": "fc_20240708_0800_kamala",
  "event_id": "evt_2024_terai_monsoon",
  "location_id": "settlement_janakpurdham",
  "issued_at": "2024-07-08T08:00:00Z",
  "input_data_cutoff_at": "2024-07-08T07:30:00Z",
  "mode": "historical_demo",
  "model_version": "baseline-v1",
  "data_quality": "PARTIAL",
  "horizons": [
    {
      "hours": 1,
      "risk_level": "moderate",
      "calibrated_probability": 0.58,
      "valid_at": "2024-07-08T09:00:00Z"
    },
    {
      "hours": 3,
      "risk_level": "high",
      "calibrated_probability": 0.82,
      "valid_at": "2024-07-08T11:00:00Z"
    },
    {
      "hours": 6,
      "risk_level": "critical",
      "calibrated_probability": 0.94,
      "valid_at": "2024-07-08T14:00:00Z"
    }
  ],
  "limitations": [
    "PIPELINE TEST ONLY: Model calibrated on synthetic historical proxy data.",
    "Issued time strictly preserved: 2024-07-08T08:00:00Z."
  ]
}
```

> [!NOTE]
> `issued_at` and `valid_at` are strictly distinct timestamps. `issued_at` represents the model run timestamp; `valid_at` represents the target forecast horizon.

---

## 6. Spatial Analysis Contracts

### 6.1 Affected Settlements (`GET /api/v1/flood-events/{event_id}/settlements`)
- Returns `status="completed"` when settlements in the study area were evaluated and spatial intersection was computed.
- Returns `status="no_settlement_data"` when no mapped settlement layers exist in the region.
- Returns `status="no_extent_available"` when no flood extent has been imported for the event.

### 6.2 Exposed Assets (`GET /api/v1/flood-events/{event_id}/assets`)
- Returns `roads_exposed_km`, `structures_exposed_count`, and `cropland_exposed_ha`.
- When an asset inventory exists and zero intersection occurs, returns `status="completed"` with zeroed counts.
- When no mapped asset records exist in the database, returns `status="no_assets_available"`.

### 6.3 Route Hazard Screening (`POST /api/v1/routes/assess`)
- Input is candidate route GeoJSON LineString:
  ```json
  {
    "route": {
      "type": "LineString",
      "coordinates": [[85.918, 26.725], [85.928, 26.732], [85.940, 26.745]]
    },
    "event_id": "evt_2024_terai_monsoon",
    "buffer_meters": 100.0
  }
  ```
- Overall `route_status` is either `hazards_detected` or `conditional` (when no intersections are found).
- **CRITICAL**: The backend will NEVER return a status of "safe", adhering strictly to safety decision-support guidelines.

---

## 7. Alert Lifecycle & Simulation Safeguards

### State Machine:
$$\text{DRAFT} \xrightarrow{\text{POST /alerts/\{id\}/approve}} \text{APPROVED} \xrightarrow{\text{POST /alerts/\{id\}/dispatch}} \text{DISPATCHED}$$

1. **Mandatory Labeling**: All demo and test alerts are automatically prefixed with `[DEMO / TEST ONLY]`.
2. **Operational Prohibition**: Any dispatch request with `simulated: false` is rejected with `HTTP 400 Bad Request` (`OPERATIONAL_DISPATCH_PROHIBITED`).
3. **Double Dispatch Prevention**: Re-dispatching an already dispatched alert returns `HTTP 400 Bad Request` (`INVALID_STATE`).
4. **Public Feed Isolation**: Demo alerts are isolated from the public general alerts feed. Public calls require `include_demo=true`, which is strictly restricted to authorized demonstration participants and authorities.

---

## 8. Citizen Assistance & Privacy Contracts

1. **Submission**: Authenticated citizen submits GPS coordinates (`POST /api/v1/assistance`).
2. **Privacy Boundary**:
   - `GET /api/v1/assistance/mine` returns only requests submitted by the calling user.
   - Citizens querying other citizens' request IDs via `GET /api/v1/assistance/{id}` receive `HTTP 403 Forbidden` (`FORBIDDEN_REQUEST_ACCESS`).
3. **No Coordinate Leakage**: Real-time WebSocket broadcasts for `assistance.created` emit only high-level categorization (`category`, `people_count`) to the `authority_queue` channel; raw coordinates and citizen IDs are strictly excluded.

---

## 9. Historical Replay Workflow & Reporting

### 9.1 Chronological Timeline (`GET /api/v1/flood-events/{event_id}/timeline`)
Synthesizes all linked milestones in strict chronological order:
1. `event_start`: Event episode declared.
2. `forecast_issued`: Ingested model forecasts.
3. `flood_observation`: Observed satellite flood extents.
4. `evaluation_recorded`: Benchmark evaluations against reference data.
5. `event_end`: Conclusion of historical flood episode.

### 9.2 Synthesized Impact Report (`GET /api/v1/flood-events/{event_id}/report`)
Combines observed satellite extent, settlement intersections, and critical asset exposures.
Downloadable exports available via `GET /api/v1/flood-events/{event_id}/report/export?format=json` and `format=csv`.

---

## 10. WebSocket Real-Time Bus Specification

- **Endpoint:** `/ws/v1/events?token=<JWT_TOKEN>`
- **Security Notice:** Query parameter authentication is permitted for local and demonstration environments. Production ingress must terminate or mask credentials in query logs.
- **Default Subscribed Channels:**
  - Citizen: `public`, `alerts`, `risk_updates`, `user:<USER_ID>`
  - Authority: Above + `authority_queue`
- **Reconnection REST Resync Pattern:**
  Because the backend operates on an ephemeral in-memory broadcast model without persistent offline replay queues, reconnecting clients must send `{"action": "resync"}` and perform REST synchronization:
  - Fetch alerts: `GET /api/v1/alerts`
  - Fetch assistance: `GET /api/v1/assistance/mine` (citizen) or `GET /api/v1/assistance` (authority)
  - Fetch predictions: `GET /api/v1/predictions/latest`

---

## 11. Frontend Integration Checklist (Member 4)

- [ ] Connect auth state to `Authorization: Bearer <token>`.
- [ ] Implement token refresh via `POST /api/v1/auth/refresh`.
- [ ] For map layers, render `GET /api/v1/predictions/map` GeoJSON risk polygons.
- [ ] On satellite view, overlay GeoJSON Feature from `GET /api/v1/flood-events/{event_id}/extent/geojson`.
- [ ] Display prominent `[DEMO / TEST ONLY]` badge on all demo alert cards.
- [ ] Show route screening results as `Conditional` (yellow) or `Hazards Intersected` (red), never "Safe".
- [ ] Ensure assistance requests display status chips (`pending`, `in_progress`, `resolved`).
- [ ] Handle WebSocket disconnection gracefully and trigger REST resynchronization on reconnect.

---

## 12. Known Limitations & Unimplemented Capabilities

1. **Online Model Training (`POST /api/v1/models/training-jobs`)**:
   - Status: Truthful `501 Not Implemented`.
   - Reason: AI/ML model training is executed offline via research scripts (`ml/src/train_baseline.py`). No online background GPU training executor exists in backend infrastructure.
2. **PostgreSQL/PostGIS vs SQLite**:
   - Live PostGIS: Full spatial index (`GIST`), `ST_Intersects`, `ST_Buffer` in meters.
   - SQLite Fallback: In-memory Shapely operations with Euclidean approximations.
3. **No Operational Warning Dispatch**:
   - Real-world SMS gateways, WhatsApp APIs, or cell broadcasts are intentionally not configured. All push notifications run through sandbox opt-in mocking adapters.
