# Database, API & WebSocket Contracts — Implementation Draft

This file complements the detailed architecture. Team members should freeze field names on Day 1. Use consistent identifiers, UTC timestamps, GeoJSON geometry, and explicit provenance.

## Core records
- **User**: id, role (citizen/authority/admin), optional profile, created_at.
- **FloodEvent**: id, region_id, name, start_at, end_at, mode (historical_demo/live), source_refs.
- **Location**: id, name, geometry, CRS/source.
- **DataSource**: id, kind, provider, last_observed_at, status.
- **ForecastRun**: id, event_id, issued_at, model_version, input_data_cutoff_at, mode.
- **RiskPrediction**: forecast_run_id, location_id, valid_at, horizon_hours, risk_level, calibrated_probability (nullable), geometry_ref, data_quality.
- **SatelliteScene**: id, provider, modality, captured_at, cloud_quality, asset_ref.
- **FloodExtent**: id, event_id, observed_at, method, polygon/raster_ref, area_km2, source_scene_ids.
- **Asset**: id, type, geometry, data_source_id.
- **Facility**: id, type (shelter/hospital), location, verification_status, status_checked_at.
- **RoadHazard**: id, geometry, kind, status, source, observed_at.
- **Alert**: id, area_id, message, status, created_by, approved_by, issued_at.
- **AssistanceRequest**: id, citizen_id, location, category, status, created_at, updated_at.
- **Evaluation**: id, event_id, target_type, baseline_version, candidate_version, metrics, reference_id.

## REST routes — `/api/v1`
| Verb | Path | Purpose | Access |
|---|---|---|---|
| GET | `/health` | Service status | Public |
| GET | `/ready` | Database & PostGIS readiness | Public |
| POST | `/flood-events` | Create / import flood event | Authority / Admin |
| GET | `/flood-events` | List flood events | Public |
| GET | `/flood-events/{event_id}` | Flood event details | Public |
| POST | `/flood-events/{event_id}/extent` | Ingest georeferenced flood extent | Authority / Admin |
| GET | `/flood-events/{event_id}/extent` | Observed flood extent with GeoJSON | Public |
| GET | `/flood-events/{event_id}/extent/geojson` | Flood extent as RFC 7946 Feature | Public |
| GET | `/flood-events/{event_id}/settlements` | Affected settlement spatial intersections | Public |
| GET | `/flood-events/{event_id}/assets` | Asset exposure spatial intersections | Public |
| GET | `/flood-events/{event_id}/report` | Synthesized impact assessment report | Public |
| POST | `/satellite/scenes` | Register optical / SAR scene metadata | Authority / Admin |
| GET | `/satellite/scenes` | List stored satellite scenes | Public |
| GET | `/satellite/scenes/{scene_id}` | Satellite scene details | Public |
| POST | `/satellite/jobs` | Start authorized processing job | Authority / Admin |
| GET | `/satellite/jobs/{job_id}` | Job status | Public |
| POST | `/locations` | Register settlement / boundary | Authority / Admin |
| GET | `/locations` | List locations and settlements | Public |
| POST | `/predictions/ingest` | Ingest +1h, +3h, +6h risk forecast | Authority / Admin |
| GET | `/predictions/latest?location_id=...` | Latest available forecast | Public |
| GET | `/predictions/locations/{id}` | Forecast for one location | Public |
| GET | `/predictions/map` | Database-backed risk-zone vector layer | Public |
| GET | `/monitoring/weather` | Weather observations/forecasts | Public |
| GET | `/monitoring/rivers` | Available river observations | Public |
| GET | `/monitoring/dams` | Verified dam notices if any | Public |
| GET | `/facilities/shelters` | Verified shelter records | Public |
| GET | `/facilities/hospitals` | Known hospital records | Public |
| POST | `/routes/assess` | Route-hazard assessment | Public |
| POST | `/alerts` | Create authority draft | Authority / Admin |
| POST | `/alerts/{alert_id}/approve` | Approve test alert | Authority / Admin |
| POST | `/alerts/{alert_id}/dispatch` | Dispatch to authorized test targets | Authority / Admin |
| POST | `/assistance` | Citizen request | Authenticated Citizen |
| GET | `/assistance/mine` | Citizen's own requests | Authenticated Citizen |
| GET | `/assistance` | Authority queue | Authority / Admin |
| PATCH | `/assistance/{request_id}` | Authorized status update | Authority / Admin |
| GET | `/analytics/events/{event_id}` | Event evaluation | Public |
| POST | `/models/training-jobs` | Controlled candidate-training job | Authority / Admin |

## Example forecast JSON
```json
{
  "forecast_id": "demo-forecast-001",
  "location_id": "demo-village-01",
  "issued_at": "2026-10-17T06:00:00Z",
  "mode": "historical_demo",
  "model_version": "baseline-v1",
  "data_quality": "partial",
  "horizons": [
    {"hours": 1, "risk_level": "low"},
    {"hours": 3, "risk_level": "moderate"},
    {"hours": 6, "risk_level": "high"}
  ],
  "limitations": ["Upstream gauge unavailable"]
}
```

## WebSocket event format
Endpoint: `/ws/v1/events`

```json
{
  "event_id": "evt_001",
  "type": "risk.updated",
  "timestamp": "2026-10-17T06:10:00Z",
  "location_id": "demo-village-01",
  "resource_id": "demo-forecast-001",
  "version": 2
}
```

Types: `risk.updated`, `sensor.updated`, `flood_extent.updated`, `alert.published`, `assistance.created`, `assistance.updated`, `processing.completed`.

**Rule:** Durable database write → publish authorized WebSocket event → client fetches latest state via REST. Clients resynchronize after reconnect. Never broadcast private citizen coordinates to general subscribers.

## Error format
```json
{"error": {"code": "DATA_UNAVAILABLE", "message": "No verified gauge reading", "request_id": "req_001"}}
```

Protected resources require authentication/authorization; authority role creation cannot be open self-registration. Avoid exposing private location data in logs.
