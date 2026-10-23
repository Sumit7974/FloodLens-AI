"""Seed database with historical demonstration datasets, benchmark locations, and users.

Idempotently populates:
1. Authority & Citizen demo users (passwords hashed with bcrypt)
2. Historical flood events (Nepal Terai July 2024 & Nepal Koshi August 2017)
3. Benchmark locations & settlements with population and vulnerability metadata
4. Critical infrastructure assets, shelters, and road hazards
5. Multi-horizon forecast runs (+1h, +3h, +6h)
6. Satellite scenes and observed flood extent records (SAR + Optical NDWI)
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure backend root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.core.spatial import to_wkt_element
from app.database import SessionLocal
from app.models.asset import Asset, Facility, RoadHazard
from app.models.enums import DataQuality, EventType, OperationalMode, RiskLevel, UserRole
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.models.satellite import FloodExtent, SatelliteScene
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("floodlens.seed")


def seed_database() -> None:
    db = SessionLocal()
    try:
        logger.info("[SEED] Starting idempotent database population...")

        # 1. Authority and Citizen Demo Users
        auth_user = db.query(User).filter(User.email == "authority_lead@floodlens.org").first()
        if not auth_user:
            auth_user = User(
                id="usr_auth_lead_demo",
                email="authority_lead@floodlens.org",
                hashed_password=hash_password("FloodLens2026!"),
                full_name="Disaster Management Authority Lead",
                role=UserRole.AUTHORITY,
                is_active=True,
            )
            db.add(auth_user)
            logger.info("  -> Added Authority user: authority_lead@floodlens.org")

        citizen_user = db.query(User).filter(User.email == "citizen_janakpur@example.com").first()
        if not citizen_user:
            citizen_user = User(
                id="usr_citizen_demo",
                email="citizen_janakpur@example.com",
                hashed_password=hash_password("Citizen2026!"),
                full_name="Janakpur Resident Citizen",
                role=UserRole.CITIZEN,
                is_active=True,
            )
            db.add(citizen_user)
            logger.info("  -> Added Citizen user: citizen_janakpur@example.com")

        db.commit()

        # 2. Historical Flood Events
        event_2024 = db.query(FloodEvent).filter(FloodEvent.id == "evt_2024_terai_monsoon").first()
        if not event_2024:
            event_2024 = FloodEvent(
                id="evt_2024_terai_monsoon",
                region_id="terai_dhanusha",
                name="Historical Nepal Terai Monsoon Inundation (July 2024 Episode)",
                mode=OperationalMode.HISTORICAL_DEMO,
                start_at=datetime(2024, 7, 8, 0, 0, tzinfo=timezone.utc),
                end_at=datetime(2024, 7, 12, 23, 59, 59, tzinfo=timezone.utc),
                source_refs={
                    "hydrology_source": "Nepal Department of Hydrology and Meteorology (DHM) Telemetry",
                    "satellite_sensor": "Copernicus Sentinel-1 SAR C-Band",
                    "curation": "FloodLens Historical Benchmark Dataset v1.0",
                },
                description="Historical monsoon surge causing river overtopping across Kamala basin and Dhanusha lowlands.",
            )
            db.add(event_2024)
            logger.info("  -> Added Event: evt_2024_terai_monsoon")

        event_2017 = db.query(FloodEvent).filter(FloodEvent.id == "event_nepal_koshi_2017").first()
        if not event_2017:
            event_2017 = FloodEvent(
                id="event_nepal_koshi_2017",
                region_id="nepal_terai",
                name="Nepal Koshi Historical Flood 2017",
                mode=OperationalMode.HISTORICAL_DEMO,
                start_at=datetime(2017, 8, 10, 0, 0, tzinfo=timezone.utc),
                end_at=datetime(2017, 8, 25, 23, 59, 59, tzinfo=timezone.utc),
                source_refs={
                    "satellite_sensor": "Copernicus Sentinel-2 Level-2A MSI",
                    "dataset": "Koshi Basin Historic Optical Inundation Benchmark",
                },
                description="Severe historic 2017 Koshi flood event in Eastern Nepal Terai.",
            )
            db.add(event_2017)
            logger.info("  -> Added Event: event_nepal_koshi_2017")

        db.commit()

        # 3. Locations & Settlements
        locs = [
            {
                "id": "settlement_janakpurdham",
                "name": "Janakpurdham Sub-Metropolitan",
                "admin_level": 3,
                "parent_id": "terai_dhanusha",
                "geom": {"type": "Point", "coordinates": [85.9244, 26.7288]},
                "meta": {"region_id": "terai_dhanusha", "population": 195438, "vulnerability_score": 0.82},
            },
            {
                "id": "settlement_sabaila",
                "name": "Sabaila Municipality",
                "admin_level": 3,
                "parent_id": "terai_dhanusha",
                "geom": {"type": "Point", "coordinates": [85.9620, 26.7980]},
                "meta": {"region_id": "terai_dhanusha", "population": 35870, "vulnerability_score": 0.65},
            },
            {
                "id": "loc_sunsari_chatara",
                "name": "Chatara Hydro-Station (Koshi Main)",
                "admin_level": 2,
                "parent_id": "nepal_terai",
                "geom": {"type": "Point", "coordinates": [87.1630, 26.8710]},
                "meta": {"station_id": "gauge-chatara", "river": "Saptakoshi Main Stem", "danger_level": 8.0},
            },
        ]
        for item in locs:
            if not db.query(Location).filter(Location.id == item["id"]).first():
                loc = Location(
                    id=item["id"],
                    name=item["name"],
                    admin_level=item["admin_level"],
                    parent_id=item["parent_id"],
                    geometry=to_wkt_element(item["geom"], expected_type="POINT"),
                    metadata_json=item["meta"],
                )
                db.add(loc)
                logger.info("  -> Added Location: %s", item["id"])

        db.commit()

        # 4. Critical Infrastructure Assets & Hazards
        if not db.query(Asset).filter(Asset.id == "asset_road_kamala_link").first():
            asset_road = Asset(
                id="asset_road_kamala_link",
                asset_type="road",
                geometry=to_wkt_element(
                    {"type": "LineString", "coordinates": [[85.9200, 26.7200], [85.9300, 26.7350]]},
                    expected_type="LINESTRING",
                ),
                metadata_json={"road_name": "Kamala River Access Road (Section 4)", "length_km": 4.8},
            )
            db.add(asset_road)

        if not db.query(Facility).filter(Facility.id == "facility_shelter_janakpur_school").first():
            shelter = Facility(
                id="facility_shelter_janakpur_school",
                type="shelter",
                name="Janakpur Community Higher Secondary School Shelter",
                verification_status="verified",
                capacity=600,
                location=to_wkt_element(
                    {"type": "Point", "coordinates": [85.9180, 26.7250]},
                    expected_type="POINT",
                ),
                details={"water_available": True},
            )
            db.add(shelter)

        if not db.query(RoadHazard).filter(RoadHazard.id == "rh_kamala_bridge_overtop").first():
            rh = RoadHazard(
                id="rh_kamala_bridge_overtop",
                road_id="Hulaki-Kamala-01",
                hazard_type="submerged",
                status="active",
                geometry=to_wkt_element(
                    {"type": "Point", "coordinates": [85.9280, 26.7320]},
                    expected_type="POINT",
                ),
                observed_at=datetime(2024, 7, 8, 9, 30, tzinfo=timezone.utc),
                source="DHM Field Telemetry",
                confidence=0.95,
            )
            db.add(rh)

        db.commit()

        # 5. Multi-Horizon Forecast Run (+1h, +3h, +6h)
        fc_run = db.query(ForecastRun).filter(ForecastRun.id == "fc_20240708_0800_kamala").first()
        if not fc_run:
            issue_t = datetime(2024, 7, 8, 8, 0, tzinfo=timezone.utc)
            fc_run = ForecastRun(
                id="fc_20240708_0800_kamala",
                event_id="evt_2024_terai_monsoon",
                issued_at=issue_t,
                input_data_cutoff_at=issue_t - timedelta(minutes=30),
                model_version="baseline-v1",
                mode=OperationalMode.HISTORICAL_DEMO,
                status="completed",
                limitations=[
                    "PIPELINE TEST ONLY: Model calibrated on synthetic historical proxy data.",
                    "Issued time strictly preserved: 2024-07-08T08:00:00Z.",
                ],
            )
            db.add(fc_run)
            db.commit()

            horizons = [
                RiskPrediction(
                    id="pred_fc_20240708_0800_1h",
                    forecast_run_id="fc_20240708_0800_kamala",
                    location_id="settlement_janakpurdham",
                    horizon_hours=1,
                    valid_at=issue_t + timedelta(hours=1),
                    risk_level=RiskLevel.MODERATE,
                    calibrated_probability=0.58,
                    data_quality=DataQuality.PARTIAL,
                ),
                RiskPrediction(
                    id="pred_fc_20240708_0800_3h",
                    forecast_run_id="fc_20240708_0800_kamala",
                    location_id="settlement_janakpurdham",
                    horizon_hours=3,
                    valid_at=issue_t + timedelta(hours=3),
                    risk_level=RiskLevel.HIGH,
                    calibrated_probability=0.82,
                    data_quality=DataQuality.PARTIAL,
                ),
                RiskPrediction(
                    id="pred_fc_20240708_0800_6h",
                    forecast_run_id="fc_20240708_0800_kamala",
                    location_id="settlement_janakpurdham",
                    horizon_hours=6,
                    valid_at=issue_t + timedelta(hours=6),
                    risk_level=RiskLevel.CRITICAL,
                    calibrated_probability=0.94,
                    data_quality=DataQuality.PARTIAL,
                ),
            ]
            db.add_all(horizons)
            db.commit()
            logger.info("  -> Added Forecast Run & 3 Risk Predictions (+1h, +3h, +6h)")

        # 6. Satellite Scenes & Extents
        scene_s1 = db.query(SatelliteScene).filter(SatelliteScene.id == "scene_s1_20240708_terai").first()
        if not scene_s1:
            scene_s1 = SatelliteScene(
                id="scene_s1_20240708_terai",
                provider="Copernicus",
                sensor="Sentinel-1 SAR",
                modality="sar",
                captured_at=datetime(2024, 7, 8, 10, 15, tzinfo=timezone.utc),
                cloud_quality=100.0,
                asset_ref="backend/tests/fixtures/synthetic_satellite_scene",
                bbox_geojson={
                    "type": "Polygon",
                    "coordinates": [[[85.8, 26.6], [86.1, 26.6], [86.1, 26.9], [85.8, 26.9], [85.8, 26.6]]],
                },
            )
            db.add(scene_s1)
            logger.info("  -> Added Scene: scene_s1_20240708_terai")

        scene_s2 = db.query(SatelliteScene).filter(SatelliteScene.id == "S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627").first()
        if not scene_s2:
            scene_s2 = SatelliteScene(
                id="S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627",
                provider="ESA Copernicus",
                sensor="Sentinel-2 MSI Level-2A",
                modality="optical",
                captured_at=datetime(2017, 8, 23, 4, 37, 1, tzinfo=timezone.utc),
                cloud_quality=88.5,
                asset_ref="data/historical_koshi_optical",
                bbox_geojson={
                    "type": "Polygon",
                    "coordinates": [[[86.5, 26.2], [87.5, 26.2], [87.5, 27.2], [86.5, 27.2], [86.5, 26.2]]],
                },
            )
            db.add(scene_s2)
            logger.info("  -> Added Scene: S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627")

        db.commit()

        # Observed Flood Extents
        ext_s1 = db.query(FloodExtent).filter(FloodExtent.id == "ext_s1_20240708_1015").first()
        if not ext_s1:
            poly_wkt = (
                "POLYGON(("
                "85.9100 26.7150, "
                "85.9450 26.7150, "
                "85.9450 26.7450, "
                "85.9100 26.7450, "
                "85.9100 26.7150"
                "))"
            )
            ext_s1 = FloodExtent(
                id="ext_s1_20240708_1015",
                event_id="evt_2024_terai_monsoon",
                observed_at=datetime(2024, 7, 8, 10, 15, tzinfo=timezone.utc),
                method="SAR_CHANGE",
                area_km2=42.6,
                source_scene_ids=["scene_s1_20240708_terai"],
                confidence=0.91,
                provenance="PROCESSED_SAR",
                geometry=to_wkt_element(poly_wkt, expected_type="POLYGON"),
            )
            db.add(ext_s1)
            logger.info("  -> Added Extent: ext_s1_20240708_1015")

        ext_s2 = db.query(FloodExtent).filter(FloodExtent.id == "ext_koshi_2017_optical").first()
        if not ext_s2:
            koshi_wkt = (
                "POLYGON(("
                "87.0500 26.7500, "
                "87.1800 26.7500, "
                "87.1800 26.8900, "
                "87.0500 26.8900, "
                "87.0500 26.7500"
                "))"
            )
            ext_s2 = FloodExtent(
                id="ext_koshi_2017_optical",
                event_id="event_nepal_koshi_2017",
                observed_at=datetime(2017, 8, 23, 4, 37, 1, tzinfo=timezone.utc),
                method="NDWI",
                area_km2=0.64,
                source_scene_ids=["S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627"],
                confidence=None,  # Honest uncalibrated null
                provenance="PROCESSED_OPTICAL",
                geometry=to_wkt_element(koshi_wkt, expected_type="POLYGON"),
            )
            db.add(ext_s2)
            logger.info("  -> Added Extent: ext_koshi_2017_optical")

        db.commit()
        logger.info("[SEED] Database seeding completed successfully!")

    except Exception as exc:
        db.rollback()
        logger.error("[SEED] Error seeding database: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
