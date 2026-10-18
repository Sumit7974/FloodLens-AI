"""Comprehensive test suite for Member 1, Day 2 deliverables.

Covers:
1. Validated satellite scene and flood event import APIs
2. Georeferenced flood extent storage in PostGIS
3. Actual flood extent GeoJSON responses
4. Affected-settlement spatial intersections
5. +1h, +3h, +6h multi-horizon forecast ingestion
6. Database-backed forecasts for locations
7. Replacement of misleading placeholder map responses with real database-backed risk zones
8. Preservation of timestamps, sources, model versions, uncertainty, and historical-demo labels
9. Role-based authorization on write endpoints (Authority/Admin allowed, Citizen forbidden, Unauthenticated rejected)
"""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import OperationalMode, UserRole
from app.models.flood_event import FloodEvent
from app.models.location import Location
from app.models.satellite import FloodExtent, SatelliteScene
from app.models.user import User


# ==============================================================================
# 1. Flood Event Import & Management APIs
# ==============================================================================
def test_create_flood_event_authorized(client: TestClient, authority_token: str):
    """Authority can create/import a validated flood event with mode and source refs."""
    event_id = f"evt_nepal_terai_{uuid.uuid4().hex[:6]}"
    start_time = datetime.now(timezone.utc) - timedelta(days=2)
    end_time = datetime.now(timezone.utc) + timedelta(days=2)

    payload = {
        "id": event_id,
        "region_id": "nepal_terai_koshi",
        "name": "August 2024 Koshi Basin Monsoon Flood",
        "start_at": start_time.isoformat(),
        "end_at": end_time.isoformat(),
        "mode": "historical_demo",
        "source_refs": {
            "dhm_nepal_station": "Koshi_Chatara_0550",
            "sentinel_scene": "S2A_MSIL2A_20240815",
            "cwc_gauge": "Birpur_Gauge_01",
        },
        "description": "Historical demonstration event across Koshi river plains in eastern Nepal Terai.",
    }

    response = client.post(
        "/api/v1/flood-events",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    data = response.json()
    assert data["id"] == event_id
    assert data["region_id"] == "nepal_terai_koshi"
    assert data["name"] == "August 2024 Koshi Basin Monsoon Flood"
    assert data["mode"] == "historical_demo"
    assert "dhm_nepal_station" in data["source_refs"]


def test_create_flood_event_citizen_forbidden(client: TestClient, citizen_token: str):
    """Citizen role is forbidden from creating or modifying flood events."""
    payload = {
        "region_id": "nepal_terai",
        "name": "Unauthorized Citizen Event",
        "start_at": datetime.now(timezone.utc).isoformat(),
        "mode": "historical_demo",
    }
    response = client.post(
        "/api/v1/flood-events",
        json=payload,
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_flood_event_unauthenticated_rejected(client: TestClient):
    """Unauthenticated requests cannot create flood events."""
    payload = {
        "region_id": "nepal_terai",
        "name": "Anonymous Event",
        "start_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/v1/flood-events", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_flood_event_validation_date_order(client: TestClient, authority_token: str):
    """Event start_at cannot be later than end_at."""
    start_time = datetime.now(timezone.utc)
    end_time = start_time - timedelta(days=1)  # invalid order

    payload = {
        "region_id": "nepal_terai",
        "name": "Invalid Date Event",
        "start_at": start_time.isoformat(),
        "end_at": end_time.isoformat(),
    }
    response = client.post(
        "/api/v1/flood-events",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_flood_events_and_get_details(client: TestClient, authority_token: str):
    """GET /flood-events lists events and allows filtering by mode."""
    # Create an event first
    evt_id = f"evt_list_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "nepal_bagmati",
            "name": "Bagmati Flood Replay",
            "start_at": datetime.now(timezone.utc).isoformat(),
            "mode": "historical_demo",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    response = client.get("/api/v1/flood-events?mode=historical_demo")
    assert response.status_code == status.HTTP_200_OK
    events = response.json()
    assert isinstance(events, list)
    assert any(e["id"] == evt_id for e in events)

    # Get single event
    detail_res = client.get(f"/api/v1/flood-events/{evt_id}")
    assert detail_res.status_code == status.HTTP_200_OK
    assert detail_res.json()["name"] == "Bagmati Flood Replay"


# ==============================================================================
# 2. Satellite Scene Ingestion & Job APIs
# ==============================================================================
def test_register_satellite_scene_authorized(client: TestClient, authority_token: str):
    """Authority can register a Sentinel-2 optical scene with cloud quality and metadata."""
    scene_id = f"S2A_MSIL2A_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": scene_id,
        "provider": "Copernicus",
        "sensor": "Sentinel-2",
        "modality": "optical",
        "captured_at": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
        "cloud_quality": 0.08,  # 8% cloud cover
        "asset_ref": f"/data/satellite/scenes/{scene_id}.tif",
        "bbox_geojson": {
            "type": "Polygon",
            "coordinates": [[[86.8, 26.4], [87.2, 26.4], [87.2, 26.8], [86.8, 26.8], [86.8, 26.4]]],
        },
    }

    response = client.post(
        "/api/v1/satellite/scenes",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    data = response.json()
    assert data["id"] == scene_id
    assert data["sensor"] == "Sentinel-2"
    assert data["cloud_quality"] == 0.08
    assert data["modality"] == "optical"


def test_register_satellite_scene_citizen_forbidden(client: TestClient, citizen_token: str):
    """Citizens cannot register satellite scenes."""
    payload = {
        "provider": "ESA",
        "sensor": "Sentinel-1",
        "modality": "sar",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "asset_ref": "/data/sar.tif",
    }
    response = client.post(
        "/api/v1/satellite/scenes",
        json=payload,
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_register_satellite_scene_invalid_cloud_quality(client: TestClient, authority_token: str):
    """Cloud quality outside 0.0 to 1.0 is rejected."""
    payload = {
        "provider": "ESA",
        "sensor": "Sentinel-2",
        "modality": "optical",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cloud_quality": 1.5,  # Invalid: > 1.0
        "asset_ref": "/data/test.tif",
    }
    response = client.post(
        "/api/v1/satellite/scenes",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_list_and_get_satellite_scenes(client: TestClient, authority_token: str):
    """List scenes with modality filtering and fetch single scene."""
    scene_id = f"S1A_IW_GRDH_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/satellite/scenes",
        json={
            "id": scene_id,
            "provider": "ESA",
            "sensor": "Sentinel-1",
            "modality": "sar",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "asset_ref": "/data/s1.tif",
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    list_res = client.get("/api/v1/satellite/scenes?modality=sar")
    assert list_res.status_code == status.HTTP_200_OK
    scenes = list_res.json()
    assert any(s["id"] == scene_id for s in scenes)

    single_res = client.get(f"/api/v1/satellite/scenes/{scene_id}")
    assert single_res.status_code == status.HTTP_200_OK
    assert single_res.json()["modality"] == "sar"


def test_satellite_job_workflow(client: TestClient, authority_token: str):
    """Authority can trigger NDWI processing job and track its state."""
    job_payload = {
        "method": "MNDWI",
        "scene_id": "scene_s2_001",
        "baseline_scene_id": "scene_s2_pre",
        "threshold": 0.12,
    }
    create_res = client.post(
        "/api/v1/satellite/jobs",
        json=job_payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert create_res.status_code == status.HTTP_202_ACCEPTED
    job_id = create_res.json()["job_id"]
    assert job_id.startswith("sat_job_")

    # Poll status
    status_res = client.get(f"/api/v1/satellite/jobs/{job_id}")
    assert status_res.status_code == status.HTTP_200_OK
    assert status_res.json()["job_id"] == job_id


# ==============================================================================
# 3. Flood Extent Ingestion & Actual GeoJSON Response
# ==============================================================================
def test_import_flood_extent_with_geojson_and_postgis(client: TestClient, authority_token: str):
    """Import flood extent polygon in EPSG:4326 GeoJSON and verify persistence."""
    evt_id = f"evt_extent_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "nepal_terai",
            "name": "Koshi Flood Extent Test",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    extent_id = f"ext_{uuid.uuid4().hex[:6]}"
    extent_payload = {
        "id": extent_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "method": "MNDWI",
        "area_km2": 24.65,
        "source_scene_ids": ["scene_s2_post_01"],
        "confidence": 0.94,
        "polygon_ref": "/data/extents/koshi_2024.geojson",
        "raster_ref": "/data/extents/koshi_2024_mask.tif",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [86.95, 26.55],
                    [87.15, 26.55],
                    [87.15, 26.75],
                    [86.95, 26.75],
                    [86.95, 26.55],
                ]
            ],
        },
    }

    res = client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json=extent_payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert res.status_code == status.HTTP_201_CREATED, res.text
    data = res.json()
    assert data["id"] == extent_id
    assert data["area_km2"] == 24.65
    assert data["confidence"] == 0.94
    assert data["geometry"] is not None
    assert data["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_get_flood_extent_returns_actual_geojson(client: TestClient, authority_token: str):
    """GET /flood-events/{event_id}/extent returns non-null RFC 7946 GeoJSON geometry."""
    evt_id = f"evt_actual_gj_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "nepal_terai",
            "name": "GeoJSON Return Test",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json={
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "NDWI",
            "area_km2": 15.2,
            "confidence": 0.91,
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [
                        [
                            [86.90, 26.50],
                            [87.05, 26.50],
                            [87.05, 26.65],
                            [86.90, 26.65],
                            [86.90, 26.50],
                        ]
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    extent_res = client.get(f"/api/v1/flood-events/{evt_id}/extent")
    assert extent_res.status_code == status.HTTP_200_OK
    extent_data = extent_res.json()
    assert extent_data["geometry"] is not None
    assert extent_data["geometry"]["type"] == "MultiPolygon"
    assert len(extent_data["geometry"]["coordinates"]) > 0

    # Test GeoJSON Feature endpoint
    feat_res = client.get(f"/api/v1/flood-events/{evt_id}/extent/geojson")
    assert feat_res.status_code == status.HTTP_200_OK
    feat = feat_res.json()
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "MultiPolygon"
    assert feat["properties"]["method"] == "NDWI"


# ==============================================================================
# 4. Spatial Intersections: Settlements & Assets
# ==============================================================================
def test_affected_settlements_spatial_intersection(client: TestClient, authority_token: str):
    """Settlements inside flood extent are detected as inundated; outside settlements are excluded."""
    evt_id = f"evt_spatial_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "nepal_terai_sunsari",
            "name": "Sunsari District Flood",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 1. Register settlement 1 (INSIDE extent: Barahachhetra, 87.10, 26.70)
    loc_inside_id = f"loc_in_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/locations",
        json={
            "id": loc_inside_id,
            "name": "Barahachhetra Ward 2",
            "admin_level": 4,
            "crs_source": "EPSG:4326",
            "metadata_json": {"population": 3850, "vulnerability": "high"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [87.05, 26.65],
                        [87.12, 26.65],
                        [87.12, 26.72],
                        [87.05, 26.72],
                        [87.05, 26.65],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 2. Register settlement 2 (OUTSIDE extent: Pokhara, 83.98, 28.20)
    loc_outside_id = f"loc_out_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/locations",
        json={
            "id": loc_outside_id,
            "name": "Pokhara Hill Ward",
            "admin_level": 4,
            "crs_source": "EPSG:4326",
            "metadata_json": {"population": 12000, "vulnerability": "low"},
            "geometry": {
                "type": "Point",
                "coordinates": [83.98, 28.20],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 3. Ingest flood extent covering [87.00, 26.60] to [87.20, 26.80]
    client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json={
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "MNDWI",
            "area_km2": 32.5,
            "confidence": 0.95,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [87.00, 26.60],
                        [87.20, 26.60],
                        [87.20, 26.80],
                        [87.00, 26.80],
                        [87.00, 26.60],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # 4. Query affected settlements
    res = client.get(f"/api/v1/flood-events/{evt_id}/settlements")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "completed"
    assert data["total_settlements_affected"] >= 1

    settlement_ids = [s["settlement_id"] for s in data["affected_settlements"]]
    assert loc_inside_id in settlement_ids
    assert loc_outside_id not in settlement_ids

    # Verify settlement metadata and exposure details
    inside_match = next(s for s in data["affected_settlements"] if s["settlement_id"] == loc_inside_id)
    assert inside_match["name"] == "Barahachhetra Ward 2"
    assert inside_match["population_exposed"] == 3850
    assert "inundated" in inside_match["exposure_status"]


def test_exposed_assets_and_flood_report(client: TestClient, authority_token: str, db_session: Session):
    """Exposed assets and overall synthesized impact report are calculated."""
    evt_id = f"evt_report_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/flood-events",
        json={
            "id": evt_id,
            "region_id": "nepal_terai",
            "name": "Impact Report Test Event",
            "start_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    client.post(
        f"/api/v1/flood-events/{evt_id}/extent",
        json={
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "method": "MNDWI",
            "area_km2": 45.0,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [87.0, 26.5],
                        [87.3, 26.5],
                        [87.3, 26.8],
                        [87.0, 26.8],
                        [87.0, 26.5],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Check assets endpoint
    asset_res = client.get(f"/api/v1/flood-events/{evt_id}/assets")
    assert asset_res.status_code == status.HTTP_200_OK
    asset_data = asset_res.json()
    assert asset_data["status"] == "completed"

    # Check report endpoint
    report_res = client.get(f"/api/v1/flood-events/{evt_id}/report")
    assert report_res.status_code == status.HTTP_200_OK
    report = report_res.json()
    assert report["event_id"] == evt_id
    assert report["extent_area_km2"] == 45.0
    assert report["status"] == "generated"
    assert report["report_generated_at"] is not None


# ==============================================================================
# 5. Multi-Horizon Forecast Ingestion (+1h, +3h, +6h)
# ==============================================================================
def test_forecast_ingestion_and_retrieval(client: TestClient, authority_token: str):
    """Ingest +1h, +3h, +6h forecast and verify retrieval by location."""
    loc_id = f"loc_fc_{uuid.uuid4().hex[:6]}"
    # Register location first
    client.post(
        "/api/v1/locations",
        json={
            "id": loc_id,
            "name": "Koshi Riverbank Settlement",
            "admin_level": 4,
            "geometry": {"type": "Point", "coordinates": [87.08, 26.68]},
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    issued_time = datetime.now(timezone.utc)
    forecast_id = f"fc_run_{uuid.uuid4().hex[:6]}"

    payload = {
        "forecast_id": forecast_id,
        "location_id": loc_id,
        "issued_at": issued_time.isoformat(),
        "mode": "historical_demo",
        "model_version": "baseline-v1",
        "data_quality": "partial",
        "horizons": [
            {"hours": 1, "risk_level": "low", "calibrated_probability": 0.15},
            {"hours": 3, "risk_level": "moderate", "calibrated_probability": 0.48},
            {"hours": 6, "risk_level": "high", "calibrated_probability": 0.82},
        ],
        "limitations": ["Upstream gauge gauge_0550 offline", "Rainfall extrapolation uncalibrated"],
    }

    # Ingest forecast
    ingest_res = client.post(
        "/api/v1/predictions/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert ingest_res.status_code == status.HTTP_201_CREATED, ingest_res.text
    ingest_data = ingest_res.json()
    assert ingest_data["forecast_id"] == forecast_id
    assert ingest_data["location_id"] == loc_id
    assert len(ingest_data["horizons"]) == 3
    assert ingest_data["horizons"][0]["hours"] == 1
    assert ingest_data["horizons"][0]["risk_level"] == "low"
    assert ingest_data["horizons"][2]["hours"] == 6
    assert ingest_data["horizons"][2]["risk_level"] == "high"

    # Query latest forecast via GET /predictions/latest?location_id=...
    latest_res = client.get(f"/api/v1/predictions/latest?location_id={loc_id}")
    assert latest_res.status_code == status.HTTP_200_OK
    latest_data = latest_res.json()
    assert latest_data["forecast_id"] == forecast_id
    assert latest_data["model_version"] == "baseline-v1"
    assert latest_data["mode"] == "historical_demo"
    assert len(latest_data["limitations"]) == 2

    # Query latest forecast via GET /predictions/locations/{location_id}
    loc_res = client.get(f"/api/v1/predictions/locations/{loc_id}")
    assert loc_res.status_code == status.HTTP_200_OK
    assert loc_res.json()["forecast_id"] == forecast_id


def test_forecast_ingest_citizen_forbidden(client: TestClient, citizen_token: str):
    """Citizens cannot ingest forecast runs."""
    payload = {
        "location_id": "loc_dummy",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "baseline-v1",
        "horizons": [{"hours": 1, "risk_level": "low"}],
    }
    res = client.post(
        "/api/v1/predictions/ingest",
        json=payload,
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN


def test_forecast_unknown_location_returns_unavailable(client: TestClient):
    """Querying forecast for non-existent location returns 404 DATA_UNAVAILABLE."""
    res = client.get("/api/v1/predictions/latest?location_id=loc_nonexistent_9999")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] in ("FORECAST_UNAVAILABLE", "DATA_UNAVAILABLE")


# ==============================================================================
# 6. Database-backed Risk Map Layer (Replacing Misleading Placeholder)
# ==============================================================================
def test_predictions_map_replaces_misleading_placeholder(client: TestClient, authority_token: str):
    """GET /predictions/map returns active database-backed GeoJSON features rather than static placeholder."""
    # Seed a location with geometry and a multi-horizon forecast
    map_loc_id = f"loc_map_{uuid.uuid4().hex[:6]}"
    client.post(
        "/api/v1/locations",
        json={
            "id": map_loc_id,
            "name": "Map Test Village",
            "admin_level": 4,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [87.10, 26.60],
                        [87.15, 26.60],
                        [87.15, 26.65],
                        [87.10, 26.65],
                        [87.10, 26.60],
                    ]
                ],
            },
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Ingest forecast for this location
    client.post(
        "/api/v1/predictions/ingest",
        json={
            "location_id": map_loc_id,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "mode": "historical_demo",
            "model_version": "baseline-v1",
            "data_quality": "full",
            "horizons": [
                {"hours": 1, "risk_level": "low", "calibrated_probability": 0.10},
                {"hours": 3, "risk_level": "moderate", "calibrated_probability": 0.40},
                {"hours": 6, "risk_level": "high", "calibrated_probability": 0.75},
            ],
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )

    # Query /predictions/map
    map_res = client.get("/api/v1/predictions/map")
    assert map_res.status_code == status.HTTP_200_OK
    map_data = map_res.json()

    # Verify it is no longer the static {"status": "ready"} placeholder
    assert map_data["layer_type"] == "risk_zones"
    assert map_data["status"] == "active"
    assert map_data["total_zones"] >= 1
    assert len(map_data["features"]) >= 1

    target_feature = next((f for f in map_data["features"] if f["id"] == map_loc_id), None)
    assert target_feature is not None, f"Feature for {map_loc_id} should be present in map features"
    assert target_feature["properties"]["location_name"] == "Map Test Village"
    assert target_feature["properties"]["max_risk_level"] == "high"
    assert "+1h" in target_feature["properties"]["horizons"]
    assert "+3h" in target_feature["properties"]["horizons"]
    assert "+6h" in target_feature["properties"]["horizons"]
    assert target_feature["geometry"] is not None
    assert target_feature["geometry"]["type"] == "Polygon"


# ==============================================================================
# 7. Location Entity Management
# ==============================================================================
def test_create_and_list_locations(client: TestClient, authority_token: str):
    """Authority can create administrative units and query them."""
    loc_id = f"loc_admin_{uuid.uuid4().hex[:6]}"
    create_res = client.post(
        "/api/v1/locations",
        json={
            "id": loc_id,
            "name": "Koshi Province Sector A",
            "admin_level": 3,
            "geometry": {"type": "Point", "coordinates": [87.27, 26.65]},
            "crs_source": "EPSG:4326",
            "metadata_json": {"sector": "eastern_plains"},
        },
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    data = create_res.json()
    assert data["id"] == loc_id
    assert data["geometry"]["type"] == "Point"

    list_res = client.get("/api/v1/locations?admin_level=3")
    assert list_res.status_code == status.HTTP_200_OK
    assert any(l["id"] == loc_id for l in list_res.json())
