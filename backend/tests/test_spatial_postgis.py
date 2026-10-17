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

    # Insert test location
    loc_id = f"loc-pg-{uuid.uuid4().hex[:6]}"
    db_session.execute(
        text("""
            INSERT INTO locations (id, name, admin_level, geometry, created_at, updated_at)
            VALUES (:id, :name, :admin_level, ST_GeomFromText(:geom, 4326), :now, :now);
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
    fac_id = f"fac-pg-{uuid.uuid4().hex[:6]}"
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

    assert len(spatial_join) == 1
    assert spatial_join[0][0] == fac_id
    assert spatial_join[0][1] == "Live PostGIS Shelter"
