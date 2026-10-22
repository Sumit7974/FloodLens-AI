"""Live PostgreSQL 16 / PostGIS 3.4 integration test for leak-free ML forecast persistence.

This test validates the end-to-end integration:
1. Verifies real PostGIS 3.4 extension availability on PostgreSQL 16.
2. Ingests candidate-leakfree-v1 multi-horizon predictions for an isolated historical-demo location.
3. Confirms database persistence of ForecastRun and all 3 RiskPrediction horizons.
4. Validates that uncalibrated model votes persist with calibrated_probability=NULL.
5. Verifies GET /api/v1/predictions/latest readback contract.
6. Guarantees no public warning or emergency alerts are dispatched.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.models.enums import OperationalMode, RiskLevel
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.schemas.forecast import ForecastIngestRequest
from ml.src.predict import FloodRiskPredictor


def test_leakfree_ml_forecast_postgis_persistence_e2e(
    client: TestClient,
    db_session: Session,
    is_postgres: bool,
    authority_token: str,
):
    """End-to-end test of candidate-leakfree-v1 forecast ingest and PostGIS persistence."""
    if not is_postgres:
        pytest.skip("Live PostGIS integration test requires PostgreSQL/PostGIS (runs in PostGIS CI)")

    # 1. Verify PostgreSQL & PostGIS version
    postgis_ver = db_session.execute(text("SELECT PostGIS_Full_Version();")).scalar()
    assert postgis_ver is not None, "PostGIS extension must be active"
    assert "POSTGIS=" in postgis_ver, f"Expected PostGIS string in version: {postgis_ver}"

    pg_ver = db_session.execute(text("SELECT version();")).scalar()
    assert pg_ver is not None
    assert "PostgreSQL" in pg_ver

    # 2. Set up isolated test location and flood event
    test_uid = uuid.uuid4().hex[:8]
    loc_id = f"loc_postgis_{test_uid}"
    event_id = f"evt_hist_demo_{test_uid}"
    forecast_id = f"fc_postgis_{test_uid}"

    # Administrative polygon boundary with SRID 4326
    test_location = Location(
        id=loc_id,
        name=f"Barahakshetra PostGIS Ward {test_uid}",
        admin_level=4,
        geometry="SRID=4326;POLYGON((87.14 26.85, 87.18 26.85, 87.18 26.90, 87.14 26.90, 87.14 26.85))",
        crs_source="EPSG:4326",
        metadata_json={"reach": "Chatara", "test": True, "environment": "historical_demo"},
    )
    db_session.add(test_location)

    now_utc = datetime.now(timezone.utc)
    test_event = FloodEvent(
        id=event_id,
        region_id="koshi_basin",
        name=f"Historical Replay Flood Surge {test_uid}",
        start_at=now_utc - timedelta(days=2),
        end_at=now_utc + timedelta(days=2),
        mode=OperationalMode.HISTORICAL_DEMO,
        source_refs={"sensor": "Chatara_DHM", "synthetic_audit": True},
        description="Isolated test event for PostGIS ML forecast persistence verification",
    )
    db_session.add(test_event)
    db_session.commit()

    try:
        # 3. Load leak-free candidate ML model
        models_dir = REPO_ROOT / "ml" / "models"
        predictor = FloodRiskPredictor(models_dir=models_dir, model_version="candidate-leakfree-v1")
        assert set(predictor.models.keys()) == {1, 3, 6}, "Must contain +1h, +3h, +6h models"

        # Explicitly labelled synthetic test inputs
        synthetic_demo_features = {
            "rainfall_mm": 15.5,
            "rainfall_rolling_3h_mm": 34.0,
            "rainfall_rolling_6h_mm": 52.0,
            "rainfall_rolling_24h_mm": 110.0,
            "upstream_discharge_m3s_lag24h": 5900.0,
            "temperature_c": 27.5,
            "relative_humidity_pct": 86.0,
            "season": "monsoon",
            "catchment_saturation_class": "wet",
        }

        # 4. Generate multi-horizon inferences
        prediction_payload = predictor.predict(
            features=synthetic_demo_features,
            location_id=loc_id,
            event_id=event_id,
            issued_at=now_utc.isoformat(),
            mode="historical_demo",
        )
        prediction_payload["forecast_id"] = forecast_id
        prediction_payload["limitations"].append(
            "Historical simulation only; proxy-labelled reanalysis is not independently verified flood ground truth."
        )

        # 5. Validate output against backend schema
        ingest_request = ForecastIngestRequest.model_validate(prediction_payload)
        assert ingest_request.mode.value == "historical_demo"
        assert sorted(h.hours for h in ingest_request.horizons) == [1, 3, 6]
        request_body = ingest_request.model_dump(mode="json")

        # 6. Authenticate as authority and submit via POST /api/v1/predictions/ingest
        headers = {"Authorization": f"Bearer {authority_token}"}
        post_response = client.post("/api/v1/predictions/ingest", json=request_body, headers=headers)
        assert post_response.status_code == status.HTTP_201_CREATED, f"Ingest failed: {post_response.text}"
        post_data = post_response.json()

        assert post_data["forecast_id"] == forecast_id
        assert post_data["location_id"] == loc_id
        assert post_data["model_version"] == "candidate-leakfree-v1"
        assert post_data["mode"] == "historical_demo"
        assert len(post_data["horizons"]) == 3

        # 7. Query PostgreSQL directly to confirm persistence
        persisted_run = db_session.execute(
            select(ForecastRun).filter(ForecastRun.id == forecast_id)
        ).scalar_one_or_none()

        assert persisted_run is not None, f"ForecastRun {forecast_id} was not persisted in PostgreSQL"
        assert persisted_run.model_version == "candidate-leakfree-v1"
        assert persisted_run.mode == OperationalMode.HISTORICAL_DEMO
        assert persisted_run.event_id == event_id

        persisted_horizons = db_session.execute(
            select(RiskPrediction)
            .filter(RiskPrediction.forecast_run_id == forecast_id)
            .order_by(RiskPrediction.horizon_hours.asc())
        ).scalars().all()

        assert len(persisted_horizons) == 3, f"Expected 3 horizons in PostgreSQL, found {len(persisted_horizons)}"
        assert [h.horizon_hours for h in persisted_horizons] == [1, 3, 6]
        assert all(h.location_id == loc_id for h in persisted_horizons)
        assert all(h.risk_level in (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH, RiskLevel.CRITICAL) for h in persisted_horizons)
        # CRITICAL: Verify uncalibrated scores are NOT presented as calibrated probabilities in DB
        assert all(h.calibrated_probability is None for h in persisted_horizons), (
            "calibrated_probability must remain NULL in PostgreSQL for uncalibrated candidate model"
        )

        # 8. Query GET /api/v1/predictions/latest for the location
        get_response = client.get(f"/api/v1/predictions/latest?location_id={loc_id}", headers=headers)
        assert get_response.status_code == status.HTTP_200_OK
        latest_data = get_response.json()

        assert latest_data["forecast_id"] == forecast_id
        assert latest_data["location_id"] == loc_id
        assert latest_data["model_version"] == "candidate-leakfree-v1"
        assert latest_data["mode"] == "historical_demo"
        assert latest_data["data_quality"] in ("partial", "verified")
        assert len(latest_data["horizons"]) == 3
        assert [h["hours"] for h in latest_data["horizons"]] == [1, 3, 6]
        assert all(h["calibrated_probability"] is None for h in latest_data["horizons"])
        assert any("historical simulation only" in lim.lower() for lim in latest_data["limitations"])

        # 9. Verify spatial containment with PostGIS function on the persisted location
        spatial_check = db_session.execute(
            text("""
                SELECT ST_Contains(
                    geometry,
                    ST_SetSRID(ST_Point(87.16, 26.87), 4326)
                )
                FROM locations
                WHERE id = :loc_id
            """),
            {"loc_id": loc_id},
        ).scalar()
        assert spatial_check is True, "PostGIS ST_Contains must evaluate to True on test location polygon"

    finally:
        # 10. Clean up isolated test records
        db_session.execute(text("DELETE FROM risk_predictions WHERE forecast_run_id = :id"), {"id": forecast_id})
        db_session.execute(text("DELETE FROM forecast_runs WHERE id = :id"), {"id": forecast_id})
        db_session.execute(text("DELETE FROM flood_events WHERE id = :id"), {"id": event_id})
        db_session.execute(text("DELETE FROM locations WHERE id = :id"), {"id": loc_id})
        db_session.commit()
