"""Automated tests for database models and schema relationships."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.alert import Alert
from app.models.asset import Asset, Facility, RoadHazard
from app.models.assistance import AssistanceRequest
from app.models.data_source import DataSource
from app.models.enums import (
    AlertStatus,
    AssistanceCategory,
    AssistanceStatus,
    DataQuality,
    OperationalMode,
    RiskLevel,
    UserRole,
)
from app.models.evaluation import Evaluation
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.models.satellite import FloodExtent, SatelliteScene
from app.models.user import User


def test_core_models_lifecycle(db_session: Session, test_authority_user: User):
    """Test full relational persistence lifecycle across all core model entities."""
    now = datetime.now(timezone.utc)

    # 1. Location
    loc = Location(
        name="Janakpur Ward 04",
        admin_level=4,
        crs_source="EPSG:4326",
        metadata_json={"district": "Dhanusha", "province": "Madhesh"},
    )
    db_session.add(loc)
    db_session.commit()
    db_session.refresh(loc)
    assert loc.id is not None
    assert loc.name == "Janakpur Ward 04"

    # 2. DataSource
    source = DataSource(
        kind="river_gauge",
        provider="DHM Nepal",
        last_observed_at=now,
        status="active",
        config={"station_code": "RIV_004"},
    )
    db_session.add(source)
    db_session.commit()

    # 3. FloodEvent
    event = FloodEvent(
        region_id="terai_dhanusha_01",
        name="Terai Monsoon Inundation 2026",
        start_at=now,
        mode=OperationalMode.HISTORICAL_DEMO,
        source_refs={"satellite": "Sentinel-2", "gauge": "DHM"},
        description="Historical benchmark test scene",
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    assert event.mode == OperationalMode.HISTORICAL_DEMO

    # 4. ForecastRun and RiskPredictions
    run = ForecastRun(
        event_id=event.id,
        issued_at=now,
        model_version="baseline-v1",
        mode=OperationalMode.HISTORICAL_DEMO,
        status="completed",
        limitations=["Upstream tributary gauge offline"],
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    pred = RiskPrediction(
        forecast_run_id=run.id,
        location_id=loc.id,
        valid_at=now,
        horizon_hours=3,
        risk_level=RiskLevel.HIGH,
        calibrated_probability=0.78,
        data_quality=DataQuality.PARTIAL,
    )
    db_session.add(pred)
    db_session.commit()
    db_session.refresh(pred)
    assert pred.horizon_hours == 3
    assert pred.risk_level == RiskLevel.HIGH

    # 5. SatelliteScene and FloodExtent
    scene = SatelliteScene(
        provider="ESA",
        sensor="Sentinel-2",
        modality="optical",
        captured_at=now,
        cloud_quality=0.08,
        asset_ref="/data/rasters/S2_20261017.tif",
    )
    db_session.add(scene)
    db_session.commit()

    extent = FloodExtent(
        event_id=event.id,
        observed_at=now,
        method="MNDWI",
        area_km2=42.5,
        source_scene_ids=[scene.id],
        confidence=0.91,
    )
    db_session.add(extent)
    db_session.commit()
    db_session.refresh(extent)
    assert extent.area_km2 == 42.5

    # 6. Facility & RoadHazard
    shelter = Facility(
        type="shelter",
        name="Janakpur High School Shelter",
        verification_status="verified",
        capacity=350,
        contact_info="+977-41-520000",
    )
    hazard = RoadHazard(
        road_id="H01_JANAKPUR_RD",
        hazard_type="submerged",
        status="active",
        source="satellite_inferred",
        observed_at=now,
        confidence=0.88,
    )
    db_session.add_all([shelter, hazard])
    db_session.commit()

    # 7. Alert
    alert = Alert(
        area_id=loc.id,
        title="High Flood Inundation Warning",
        message="Move valuable property and livestock to higher ground.",
        status=AlertStatus.DRAFT,
        created_by=test_authority_user.id,
        mode=OperationalMode.HISTORICAL_DEMO,
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)
    assert alert.status == AlertStatus.DRAFT

    # 8. Evaluation
    eval_record = Evaluation(
        event_id=event.id,
        target_type="flood_extent",
        baseline_version="baseline-v1",
        metrics={"iou": 0.84, "precision": 0.88, "recall": 0.81},
        reference_id="copernicus_ems_ref_01",
    )
    db_session.add(eval_record)
    db_session.commit()
    db_session.refresh(eval_record)
    assert eval_record.metrics["iou"] == 0.84
