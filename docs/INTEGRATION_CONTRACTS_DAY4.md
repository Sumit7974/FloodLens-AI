# FloodLens AI — Day 4 Integration Contracts & API Specifications

**Author:** Member 1 (Backend & Integration Lead)  
**Branch:** `feature/backend-day4`  
**Target Consumers:** Member 3 (AI/ML Lead), Member 4 (Frontend/Android Lead), Member 2 (Satellite & GIS Lead)  
**Status:** Verified via Integration Test Suite (98 tests passing, 0 regressions, 0 Pyrefly type errors)

---

## Executive Overview & Responsibility Boundary

FloodLens AI is a historical simulation and decision-support platform for Nepal's Terai region.

> **CRITICAL RESPONSIBILITY BOUNDARY**:
> FloodLens collects, analyzes, organizes, and communicates flood intelligence to authorities.
> FloodLens does **NOT** assign rescue forces, deploy personnel, or command emergency units.
> Government authorities make all operational decisions independently.

---

## 1. Facilities API (`/api/v1/facilities`)

Map-ready endpoints for emergency shelters and hospitals providing RFC 7946 GeoJSON Point geometry in EPSG:4326 (`[longitude, latitude]`), operational status check freshness, verified vs unverified distinctions, and explicit data limitations.

### 1.1 Verified Shelters Endpoint
- **URL:** `GET /api/v1/facilities/shelters`
- **Query Parameters:**
  - `verification_status` (optional, string): Filter by `verified`, `unverified`, or `demo_labeled`.
- **Access:** Public

#### Response Schema (`200 OK`)
```json
{
  "count": 2,
  "shelters": [
    {
      "id": "fac_sh_01",
      "type": "shelter",
      "name": "Janakpur Community Emergency Shelter",
      "verification_status": "verified",
      "capacity": 500,
      "contact_info": "+977-41-520111",
      "status_checked_at": "2026-10-20T10:00:00Z",
      "location": {
        "type": "Point",
        "coordinates": [85.924, 26.728]
      },
      "longitude": 85.924,
      "latitude": 26.728,
      "source": "DHM Nepal",
      "details": {
        "amenities": ["generator", "potable_water"]
      },
      "limitations": []
    },
    {
      "id": "fac_sh_02",
      "type": "shelter",
      "name": "Jaleshwar High School Hall",
      "verification_status": "unverified",
      "capacity": null,
      "contact_info": null,
      "status_checked_at": null,
      "location": {
        "type": "Point",
        "coordinates": [85.801, 26.647]
      },
      "longitude": 85.801,
      "latitude": 26.647,
      "source": null,
      "details": {},
      "limitations": [
        "Facility operational readiness and flood safety have not been verified by local authorities; presence in database does not guarantee safety.",
        "Capacity unknown or unrecorded in local administrative database.",
        "Public contact information is not on file."
      ]
    }
  ],
  "data_notes": "Presence in database does NOT guarantee physical safety, structural integrity, or active staffing. Emergency authorities make all operational shelter activation decisions."
}
```

### 1.2 Hospitals & Health Posts Endpoint
- **URL:** `GET /api/v1/facilities/hospitals`
- **Query Parameters:**
  - `verification_status` (optional, string): Filter by `verified`, `unverified`, or `demo_labeled`.
- **Access:** Public

---

## 2. Route Hazard Assessment API (`/api/v1/routes/assess`)

Evidence-based spatial hazard screening between a candidate route corridor and active database hazards.

> **Safety Notice:** This endpoint is designed for authority assessment of candidate corridors. It does **NOT** provide automated citizen navigation or autonomous evacuation routing. Route absence of hazard intersections is returned as `conditional`, **never** "safe".

- **URL:** `POST /api/v1/routes/assess`
- **Access:** Public / Authority

### 2.1 Request Payload
```json
{
  "route": {
    "type": "LineString",
    "coordinates": [
      [85.80, 26.70],
      [85.90, 26.70]
    ]
  },
  "event_id": "evt_koshi_2024",
  "evaluation_time": "2026-10-20T12:00:00Z",
  "buffer_meters": 50.0,
  "evaluation_context": {
    "agency": "District Disaster Management Committee",
    "purpose": "Supply delivery route screening"
  }
}
```

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `route` | GeoJSON dict | Required | RFC 7946 LineString in EPSG:4326 with >= 2 vertices in `[lon, lat]` format. Max 10,000 points. |
| `event_id` | string | Optional | Historical flood event ID to screen against observed satellite flood extent polygons. Returns 404 if invalid. |
| `evaluation_time` | ISO 8601 UTC | Optional | Observation cutoff timestamp; hazards observed after this time are excluded from retrospective analysis. |
| `buffer_meters` | float (0.0 to 5000.0) | Optional (default 25.0) | Proximity screening buffer in meters around route corridor. |
| `evaluation_context` | object | Optional | Operational metadata and mission context. |

### 2.2 Response Schema (`200 OK`)
```json
{
  "route_status": "hazards_detected",
  "assessment_status": "HAZARDS_INTERSECTED",
  "hazards_detected": [
    {
      "hazard_id": "rh_act_101",
      "hazard_type": "submerged",
      "source_layer": "road_hazard",
      "status": "active",
      "observed_at": "2026-10-20T08:30:00Z",
      "source": "Copernicus_Emergency_Management",
      "confidence": 0.92,
      "match_type": "direct_intersection",
      "proximity_distance_meters": 0.0,
      "intersection_details": {
        "type": "Point",
        "coordinates": [85.85, 26.70]
      },
      "notes": "Active road hazard of type 'submerged' directly intersects candidate route corridor."
    },
    {
      "hazard_id": "rh_prox_102",
      "hazard_type": "debris",
      "source_layer": "road_hazard",
      "status": "active",
      "observed_at": "2026-10-20T09:15:00Z",
      "source": "Local_Authority",
      "confidence": 0.85,
      "match_type": "proximity_warning",
      "proximity_distance_meters": 18.4,
      "intersection_details": null,
      "notes": "Active road hazard of type 'debris' is located within 18.4m buffer corridor (buffer=50.0m)."
    }
  ],
  "event_id": "evt_koshi_2024",
  "evaluation_time": "2026-10-20T12:05:00Z",
  "cutoff_time_applied": "2026-10-20T12:00:00Z",
  "total_hazards_screened": 14,
  "hazards_intersected_count": 2,
  "limitations": [
    "Demonstration decision-support prototype only: route hazard assessment does NOT command emergency deployments or guarantee alternative paths.",
    "Always follow official directives from emergency authorities.",
    "NEVER classify an unverified route as safe; absence of recorded hazards does NOT guarantee road passability or structural stability.",
    "Identified 2 hazard intersection(s) / proximity warning(s) along candidate corridor; route may be submerged, blocked, or impassable."
  ],
  "provenance": {
    "spatial_engine": "PostGIS (native) or Shapely / pyproj (fallback)",
    "road_hazards_screened": 12,
    "flood_extents_screened": 2,
    "buffer_meters": 50.0,
    "event_id": "evt_koshi_2024",
    "temporal_window_start": "2024-08-14T02:00:00Z",
    "temporal_window_end": "2026-10-20T12:00:00Z",
    "evaluation_context": { ... }
  }
}
```

### 2.3 Status Categories & Methodological Guarantees
- **Temporal Event Scoping:** Road hazards are scoped to the historical event window (`event.start_at - 24h` through `min(cutoff_time, event.end_at)`). Hazards outside this window are excluded to prevent temporally mismatched historical records from contaminating event evaluation.
- **Metric Spatial Projection:** For non-PostGIS fallback, exact geodesic distances in meters are computed using `pyproj` Azimuthal Equidistant (AEQD) projection centered at the route centroid, avoiding spherical distortion.
- **Match Distinction:** Detected hazards distinguish `match_type: "direct_intersection"` (0.0m) from `match_type: "proximity_warning"` with `proximity_distance_meters`.
- `HAZARDS_INTERSECTED` (`route_status: "hazards_detected"`): Intersecting road blockages, submerged sections, or flood extents detected.
- `NO_KNOWN_INTERSECTIONS` (`route_status: "conditional"`): No intersections among active records; limitations explicitly remind authorities that unmapped hazards or recent changes may exist. Candidate routes are **never** classified as "safe".
- `NOT_EVALUATED` (`route_status: "not_evaluated"`): No active road hazards or satellite extents exist within the event window for screening.

---

## 3. Event Analytics (`/api/v1/analytics/events/{event_id}`)

Corrected event-scoped model benchmark analytics filtering strictly on `Evaluation.event_id == event_id`.

- **URL:** `GET /api/v1/analytics/events/{event_id}`
- **Access:** Public

### 3.1 Response Schema (`200 OK`)
```json
{
  "event_id": "evt_koshi_2024",
  "event_name": "August 2024 Koshi Historical Episode",
  "mode": "historical_demo",
  "evaluations_count": 2,
  "status": "evaluations_available",
  "data_limitations": [
    "Evaluation metrics reflect benchmark comparison between model predictions and reference observations.",
    "Performance metrics should not be extrapolated outside the validated historical study area."
  ],
  "results": [
    {
      "id": "ev_001",
      "event_id": "evt_koshi_2024",
      "target_type": "flood_extent",
      "baseline_version": "baseline-v1",
      "candidate_version": "candidate-v2",
      "metrics": {
        "iou": 0.84,
        "f1_score": 0.91,
        "precision": 0.89
      },
      "reference_id": "ref_copernicus_ground_truth",
      "notes": "Evaluated against Copernicus EMS rapid mapping post-event mask",
      "created_at": "2026-10-20T08:00:00Z",
      "updated_at": "2026-10-20T08:00:00Z"
    }
  ]
}
```

### 3.2 Model Versions Listing (`GET /api/v1/models`)
Truthfully lists verified baseline models and offline research benchmarks matching Member 3 artifacts:
- `baseline-v1`: `type: "demo_prototype"`, `status: "demo_ready"` (Demonstration pipeline baseline model trained on synthetic historical data for pipeline testing and software integration verification; pipeline test only, not for real-world alerts).
- `era5-v1`: `type: "offline_benchmark"`, `status: "offline_research"` (Research benchmark model trained on open-access ERA5 reanalysis precipitation and GloFAS discharge proxy data; not validated against in-situ Nepal DHM gauge observations).

### 3.3 Training Jobs (`POST /api/v1/models/training-jobs`)
Responds with **`501 Not Implemented`** (`code: "TRAINING_NOT_IMPLEMENTED"`). Model training is executed strictly offline via research scripts and notebooks (`ml/src/train_models.py`). No background online training executor is configured, preserving truthful API semantics without claiming phantom queue execution.

---

## 4. Historical Event Replay Timeline (`/api/v1/flood-events/{event_id}/timeline`)

Chronological replay service presenting real persisted database records for a historical flood event.

- **URL:** `GET /api/v1/flood-events/{event_id}/timeline`
- **Access:** Public

### 4.1 Chronological Entries Sequence
Entries are strictly sorted by UTC timestamp (`timestamp` ascending):
1. `event_start`: Event episode registration boundary
2. `forecast_issued`: Issue of AI risk forecast run (`issued_at`), with inner `prediction_horizons` detailing valid targets (+1h, +3h, +6h)
3. `flood_observation`: Satellite sensor overpass observation (`observed_at`) with inundation area and source scene IDs
4. `evaluation_recorded`: Benchmark calculation (`created_at`) comparing prediction vs observation
5. `event_end`: Official episode conclusion boundary (if closed)

### 4.2 Response Schema (`200 OK`)
```json
{
  "event_id": "evt_koshi_2024",
  "event_name": "August 2024 Koshi Historical Episode",
  "region_id": "koshi_basin",
  "mode": "historical_demo",
  "start_at": "2024-08-15T02:00:00Z",
  "end_at": "2024-08-15T12:00:00Z",
  "timeline_generated_at": "2026-10-20T17:15:00Z",
  "total_entries": 5,
  "coverage": {
    "has_forecasts": true,
    "forecast_runs_count": 1,
    "has_flood_extents": true,
    "flood_extents_count": 1,
    "has_evaluations": true,
    "evaluations_count": 1
  },
  "entries": [
    {
      "entry_id": "evt_start_evt_koshi_2024",
      "timestamp": "2024-08-15T02:00:00Z",
      "entry_type": "event_start",
      "title": "Event Initiated: August 2024 Koshi Historical Episode",
      "description": "Historical monsoon flood episode in Koshi basin",
      "resource_id": "evt_koshi_2024",
      "resource_type": "flood_event",
      "details": { "region_id": "koshi_basin", "mode": "historical_demo" },
      "data_quality": null,
      "limitations": ["Historical dataset start boundary milestone."]
    },
    {
      "entry_id": "fc_run_01",
      "timestamp": "2024-08-15T04:00:00Z",
      "entry_type": "forecast_issued",
      "title": "Risk Forecast Issued (baseline-v1)",
      "description": "Hydrological forecast issued with 3 horizon prediction(s)",
      "resource_id": "fc_run_01",
      "resource_type": "forecast_run",
      "details": {
        "model_version": "baseline-v1",
        "issued_at": "2024-08-15T04:00:00Z",
        "prediction_horizons": [
          { "hours": 1, "valid_at": "2024-08-15T05:00:00Z", "risk_level": "LOW" },
          { "hours": 3, "valid_at": "2024-08-15T07:00:00Z", "risk_level": "HIGH" },
          { "hours": 6, "valid_at": "2024-08-15T10:00:00Z", "risk_level": "CRITICAL" }
        ]
      },
      "data_quality": "PARTIAL",
      "limitations": ["Upstream gauge offline"]
    },
    {
      "entry_id": "ext_koshi_01",
      "timestamp": "2024-08-15T06:00:00Z",
      "entry_type": "flood_observation",
      "title": "Satellite Flood Extent Observed (MNDWI)",
      "description": "Satellite sensor mapped 28.4 km2 inundated surface area",
      "resource_id": "ext_koshi_01",
      "resource_type": "flood_extent",
      "details": {
        "method": "MNDWI",
        "area_km2": 28.4,
        "observed_at": "2024-08-15T06:00:00Z",
        "confidence": 0.94,
        "source_scene_ids": ["S2A_20240815_T45RVP"]
      },
      "data_quality": "SATELLITE_DERIVED",
      "limitations": ["Derived via MNDWI satellite processing; surface extent accuracy subject to sensor resolution and canopy penetration limitations."]
    },
    {
      "entry_id": "eval_01",
      "timestamp": "2024-08-15T08:00:00Z",
      "entry_type": "evaluation_recorded",
      "title": "Model Evaluation Benchmark: flood_extent",
      "description": "Retrospective performance benchmark against reference ground_truth_mask_v1",
      "resource_id": "eval_01",
      "resource_type": "evaluation",
      "details": {
        "target_type": "flood_extent",
        "baseline_version": "baseline-v1",
        "metrics": { "iou": 0.81, "f1": 0.89 }
      },
      "data_quality": "BENCHMARK_DERIVED",
      "limitations": ["Post-flood retrospective benchmark"]
    },
    {
      "entry_id": "evt_end_evt_koshi_2024",
      "timestamp": "2024-08-15T12:00:00Z",
      "entry_type": "event_end",
      "title": "Historical Episode End: August 2024 Koshi Historical Episode",
      "description": "Recorded end timestamp of the historical flood episode dataset",
      "resource_id": "evt_koshi_2024",
      "resource_type": "flood_event",
      "details": { "duration_hours": 10.0 },
      "data_quality": null,
      "limitations": ["Recorded dataset conclusion; does not represent an official government conclusion without external verification."]
    }
  ],
  "notes": [
    "Timeline reconstructed strictly from database records durably associated with event 'evt_koshi_2024'.",
    "Alert dispatches and citizen assistance requests are handled via decoupled authority queues and are excluded from event timeline."
  ]
}
```

---

## 5. Historical Impact Reports & Downloadable Exports

### 5.1 Impact Summary Report
- **URL:** `GET /api/v1/flood-events/{event_id}/report`
- **Access:** Public

Returns synthesized historical impact assessment metrics (`extent_area_km2`, `total_settlements_affected`, `roads_exposed_km`, `structures_exposed_count`, `cropland_exposed_ha`), along with `data_provenance`, `data_limitations`, and consistent status (`summary_available`, `incomplete_evidence`, or `pending_data`).

### 5.2 Downloadable File Export Endpoint
- **URL:** `GET /api/v1/flood-events/{event_id}/report/export`
- **Query Parameters:**
  - `format` (optional, string): `json` (default) or `csv`.
- **Response Headers:**
  - `Content-Disposition: attachment; filename="floodlens_impact_report_{event_id}.{format}"`
  - `Content-Type: application/json` or `text/csv`

---

## 6. Frontend & Map Integration Guidelines

1. **MapLibre / Cesium 3D Layer Ingestion:**
   - Shelter & Hospital coordinates use RFC 7946 GeoJSON format: `[longitude, latitude]`. When styling symbols, render verified facilities with standard symbology, and unverified/demo facilities with a dashed or flagged badge.
2. **Route Hazard Rendering:**
   - Candidate routes submitted to `/api/v1/routes/assess` will return `hazards_detected`. For any hazard intersecting, the backend includes `intersection_details` as GeoJSON geometry for instant map overlay.
3. **Event Replay Scrubbing:**
   - The timeline response `/timeline` entries are pre-sorted chronologically. Frontend timeline sliders can step through entries using `entry.timestamp`, updating the map state according to `entry.resource_type` (displaying forecast cones on `forecast_issued` and flood polygons on `flood_observation`).

---

## 7. Deferred Integrations

- **Multichannel SMS / WhatsApp Adapters:**
  As configured sandbox credentials for commercial aggregators (Twilio/Infobip/Meta Cloud) are absent in the local development environment, external cellular SMS/WhatsApp dispatch is **explicitly deferred**. No simulated delivery receipts are falsified as real telecommunications delivery, preserving safety guarantees.
