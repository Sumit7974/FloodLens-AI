"""Spatial tests for PostGIS integration and geometry queries."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models.asset import Facility
from app.models.location import Location


def test_geometry_models_instantiation(db_session: Session):
    """Verify geometry models can store and retrieve spatial coordinates across backends."""
    loc_id = f"loc-{uuid.uuid4().hex[:8]}"
    location = Location(
        id=loc_id,
        name="Patna Central Zone",
        admin_level=3,
        geometry="SRID=4326;POLYGON((85.10 25.58, 85.18 25.58, 85.18 25.65, 85.10 25.65, 85.10 25.58))",
        crs_source="EPSG:4326",
        metadata_json={"zone": "central"},
    )
    db_session.add(location)

    facility_id = f"fac-{uuid.uuid4().hex[:8]}"
    facility = Facility(
        id=facility_id,
        name="Gandhi Maidan Relief Camp",
        type="shelter",
        location="SRID=4326;POINT(85.14 25.61)",
        capacity=1500,
        verification_status="verified",
        contact_info="+91-612-2200001",
        details={"supplies": "food, water, blankets"},
    )
    db_session.add(facility)
    db_session.commit()

    saved_loc = db_session.execute(select(Location).filter_by(id=loc_id)).scalar_one()
    saved_fac = db_session.execute(select(Facility).filter_by(id=facility_id)).scalar_one()

    assert saved_loc.name == "Patna Central Zone"
    assert saved_loc.geometry is not None
    assert saved_fac.name == "Gandhi Maidan Relief Camp"
    assert saved_fac.location is not None


def test_postgis_live_spatial_queries(db_session: Session, is_postgres: bool):
    """Execute live PostGIS spatial functions (ST_Contains, ST_DWithin, ST_Intersects, ST_Area).

    Skipped on SQLite; executes when running against real PostgreSQL/PostGIS.
    """
    if not is_postgres:
        pytest.skip("Live PostGIS queries require PostgreSQL with PostGIS extension")

    # 1. Verify PostGIS version
    version_result = db_session.execute(text("SELECT PostGIS_Version();")).scalar()
    assert version_result is not None
    assert "3." in version_result or "2." in version_result

    # 2. Point-in-polygon containment (ST_Contains)
    containment_query = text("""
        SELECT ST_Contains(
            ST_GeomFromText('POLYGON((85.10 25.58, 85.20 25.58, 85.20 25.66, 85.10 25.66, 85.10 25.58))', 4326),
            ST_SetSRID(ST_MakePoint(85.14, 25.61), 4326)
        ) AS contains_point;
    """)
    result = db_session.execute(containment_query).scalar()
    assert result is True

    # 3. Proximity query (ST_DWithin on geography for accurate meter distance)
    proximity_query = text("""
        SELECT ST_DWithin(
            ST_SetSRID(ST_MakePoint(85.14, 25.61), 4326)::geography,
            ST_SetSRID(ST_MakePoint(85.145, 25.612), 4326)::geography,
            2000  -- within 2,000 meters (2km)
        ) AS within_range;
    """)
    within_range = db_session.execute(proximity_query).scalar()
    assert within_range is True

    # 4. Far distance should be False
    far_proximity_query = text("""
        SELECT ST_DWithin(
            ST_SetSRID(ST_MakePoint(85.14, 25.61), 4326)::geography,
            ST_SetSRID(ST_MakePoint(85.50, 25.90), 4326)::geography,
            2000
        ) AS within_range;
    """)
    assert db_session.execute(far_proximity_query).scalar() is False

    # 5. Polygon and line intersection (ST_Intersects)
    intersect_query = text("""
        SELECT ST_Intersects(
            ST_GeomFromText('POLYGON((85.10 25.58, 85.20 25.58, 85.20 25.66, 85.10 25.66, 85.10 25.58))', 4326),
            ST_GeomFromText('LINESTRING(85.05 25.60, 85.25 25.60)', 4326)
        ) AS intersects;
    """)
    assert db_session.execute(intersect_query).scalar() is True

    # 6. Area calculation (ST_Area in square meters)
    area_query = text("""
        SELECT ST_Area(
            ST_GeomFromText('POLYGON((85.10 25.58, 85.11 25.58, 85.11 25.59, 85.10 25.59, 85.10 25.58))', 4326)::geography
        ) AS area_sq_m;
    """)
    area = db_session.execute(area_query).scalar()
    assert area is not None
    assert area > 0


def test_postgis_spatial_index_and_table_queries(db_session: Session, is_postgres: bool):
    """Test inserting live spatial records into tables and executing spatial queries with GIST indexes."""
    if not is_postgres:
        pytest.skip("Spatial index verification requires PostgreSQL with PostGIS extension")

    now = datetime.now(timezone.utc)

    # Insert test location with required metadata_json and crs_source
    loc_id = f"loc-pg-{uuid.uuid4().hex[:6]}"
    fac_id = f"fac-pg-{uuid.uuid4().hex[:6]}"

    try:
        db_session.execute(
            text("""
                INSERT INTO locations (id, name, admin_level, geometry, crs_source, metadata_json, created_at, updated_at)
                VALUES (:id, :name, :admin_level, ST_GeomFromText(:geom, 4326), 'EPSG:4326', '{}', :now, :now);
            """),
            {
                "id": loc_id,
                "name": "Live PostGIS Ward 1",
                "admin_level": 4,
                "geom": "POLYGON((85.10 25.58, 85.15 25.58, 85.15 25.63, 85.10 25.63, 85.10 25.58))",
                "now": now,
            },
        )

        # Insert test shelter facility
        db_session.execute(
            text("""
                INSERT INTO facilities (id, type, name, location, capacity, verification_status, details, created_at, updated_at)
                VALUES (:id, 'shelter', :name, ST_SetSRID(ST_MakePoint(85.12, 25.60), 4326), 1000, 'verified', '{}', :now, :now);
            """),
            {"id": fac_id, "name": "Live PostGIS Shelter", "now": now},
        )
        db_session.commit()

        # Query facilities contained in the ward location
        spatial_join = db_session.execute(
            text("""
                SELECT f.id, f.name
                FROM facilities f
                JOIN locations l ON ST_Contains(l.geometry, f.location)
                WHERE l.id = :loc_id;
            """),
            {"loc_id": loc_id},
        ).fetchall()

        matched_fac = next((row for row in spatial_join if row[0] == fac_id), None)
        assert matched_fac is not None, f"Expected facility {fac_id} to be contained in location {loc_id}"
        assert matched_fac[1] == "Live PostGIS Shelter"

    finally:
        try:
            db_session.rollback()
            db_session.execute(text("DELETE FROM facilities WHERE id = :id"), {"id": fac_id})
            db_session.execute(text("DELETE FROM locations WHERE id = :id"), {"id": loc_id})
            db_session.commit()
        except Exception:
            pass


def test_postgis_live_flood_extent_settlements_intersection(db_session: Session, is_postgres: bool):
    """Test live PostGIS spatial intersection between flood_extents and locations using ST_Intersects & ST_AsGeoJSON."""
    if not is_postgres:
        pytest.skip("Spatial extent intersection test requires PostgreSQL with PostGIS extension")

    import json
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:6]
    event_id = f"evt-live-{suffix}"
    extent_id = f"ext-live-{suffix}"
    loc_inside_id = f"loc-in-{suffix}"
    loc_outside_id = f"loc-out-{suffix}"

    try:
        # 1. Insert flood event
        db_session.execute(
            text("""
                INSERT INTO flood_events (id, region_id, name, start_at, mode, source_refs, description, created_at, updated_at)
                VALUES (:id, 'nepal_terai_koshi', 'Live PostGIS Nepal Terai Flood', :now, 'historical_demo', '{}', 'Test event', :now, :now);
            """),
            {"id": event_id, "now": now},
        )

        # 2. Insert flood extent MultiPolygon
        db_session.execute(
            text("""
                INSERT INTO flood_extents (id, event_id, observed_at, method, area_km2, source_scene_ids, geometry, created_at, updated_at)
                VALUES (:id, :event_id, :now, 'MNDWI', 18.75, '["scene_s2_terai"]',
                        ST_GeomFromText('MULTIPOLYGON(((86.90 26.50, 87.10 26.50, 87.10 26.70, 86.90 26.70, 86.90 26.50)))', 4326),
                        :now, :now);
            """),
            {"id": extent_id, "event_id": event_id, "now": now},
        )

        # 3. Insert inside settlement location (Barahachhetra village, inside bounding box)
        db_session.execute(
            text("""
                INSERT INTO locations (id, name, admin_level, geometry, crs_source, metadata_json, created_at, updated_at)
                VALUES (:id, 'Barahachhetra Inundated Settlement', 4,
                        ST_SetSRID(ST_MakePoint(87.00, 26.60), 4326),
                        'EPSG:4326', '{"population": 4200}', :now, :now);
            """),
            {"id": loc_inside_id, "now": now},
        )

        # 4. Insert outside settlement location (Kathmandu valley, far away)
        db_session.execute(
            text("""
                INSERT INTO locations (id, name, admin_level, geometry, crs_source, metadata_json, created_at, updated_at)
                VALUES (:id, 'Kathmandu Outside Settlement', 4,
                        ST_SetSRID(ST_MakePoint(85.32, 27.71), 4326),
                        'EPSG:4326', '{"population": 800000}', :now, :now);
            """),
            {"id": loc_outside_id, "now": now},
        )
        db_session.commit()

        # 5. Query spatial intersection with ST_Intersects and ST_AsGeoJSON
        intersected = db_session.execute(
            text("""
                SELECT l.id, l.name, ST_AsGeoJSON(l.geometry) AS geojson
                FROM locations l
                JOIN flood_extents fe ON fe.id = :extent_id
                WHERE ST_Intersects(l.geometry, fe.geometry);
            """),
            {"extent_id": extent_id},
        ).fetchall()

        matched_ids = [row[0] for row in intersected]
        assert loc_inside_id in matched_ids, f"Expected {loc_inside_id} to intersect flood extent {extent_id}"
        assert loc_outside_id not in matched_ids, f"Expected {loc_outside_id} to NOT intersect flood extent"

        # Verify ST_AsGeoJSON returns valid GeoJSON point
        for row in intersected:
            if row[0] == loc_inside_id:
                gj = json.loads(row[2])
                assert gj["type"] == "Point"
                assert gj["coordinates"] == [87.00, 26.60]

    finally:
        try:
            db_session.rollback()
            db_session.execute(text("DELETE FROM flood_extents WHERE id = :id"), {"id": extent_id})
            db_session.execute(text("DELETE FROM flood_events WHERE id = :id"), {"id": event_id})
            db_session.execute(text("DELETE FROM locations WHERE id = :id"), {"id": loc_inside_id})
            db_session.execute(text("DELETE FROM locations WHERE id = :id"), {"id": loc_outside_id})
            db_session.commit()
        except Exception:
            pass


def test_postgis_live_candidate_route_hazard_screening(db_session: Session, is_postgres: bool):
    """Test candidate route hazard screening against live PostGIS ST_Intersects and ST_DWithin."""
    if not is_postgres:
        pytest.skip("Live PostGIS queries require PostgreSQL with PostGIS extension")

    from app.core.spatial import assess_route_spatial
    from app.models.asset import RoadHazard
    now = datetime.now(timezone.utc)
    uid = uuid.uuid4().hex[:6]
    rh_id = f"rh_pg_{uid}"
    rh = RoadHazard(
        id=rh_id,
        hazard_type="submerged",
        geometry="SRID=4326;LINESTRING(85.10 25.60, 85.20 25.60)",
        status="active",
        source="postgis_test",
        observed_at=now,
    )
    db_session.add(rh)
    db_session.commit()

    try:
        route_crossing = {
            "type": "LineString",
            "coordinates": [[85.15, 25.55], [85.15, 25.65]],
        }
        res = assess_route_spatial(db=db_session, route_geojson=route_crossing, buffer_meters=25.0)
        assert res["assessment_status"] == "HAZARDS_INTERSECTED"
        assert res["hazards_intersected_count"] >= 1
        assert res["provenance"]["spatial_engine"] == "PostGIS (native)"
    finally:
        try:
            db_session.rollback()
            db_session.execute(text("DELETE FROM road_hazards WHERE id = :id"), {"id": rh_id})
            db_session.commit()
        except Exception:
            pass

