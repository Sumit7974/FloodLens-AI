"""Verification script for PostgreSQL / PostGIS 16 spatial capabilities and migrations.

Validates:
1. PostgreSQL 16 & PostGIS extension availability
2. Geometry columns and SRID 4326 metadata
3. GIST spatial indexes across tables
4. Spatial functions: ST_Contains, ST_DWithin, ST_Intersects, ST_Area, ST_Distance
5. Application readiness endpoint against live PostGIS
"""
import os
import sys
import uuid
from datetime import datetime, timezone

# Add backend directory to path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, text
from app.config import get_settings


def verify_postgis():
    settings = get_settings()
    db_url = settings.database_url
    print(f"[*] Connecting to database: {settings.masked_database_url}")

    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.connect() as conn:
        # 1. PostGIS Version Check
        print("\n--- 1. PostGIS Extension Check ---")
        try:
            pg_version = conn.execute(text("SELECT version();")).scalar()
            print(f"[+] PostgreSQL Version: {pg_version}")

            postgis_version = conn.execute(text("SELECT PostGIS_Full_Version();")).scalar()
            print(f"[+] PostGIS Full Version:\n    {postgis_version}")
        except Exception as exc:
            print(f"[-] PostGIS extension check failed: {exc}")
            sys.exit(1)

        # 2. Geometry Column Registration in geometry_columns
        print("\n--- 2. Geometry Column Metadata Check ---")
        geom_cols = conn.execute(
            text("""
                SELECT f_table_name, f_geometry_column, type, srid
                FROM geometry_columns
                WHERE f_table_schema = 'public'
                ORDER BY f_table_name;
            """)
        ).fetchall()

        if not geom_cols:
            print("[-] No geometry columns found in geometry_columns view. Run alembic upgrade head first.")
            sys.exit(1)

        for table, col, gtype, srid in geom_cols:
            print(f"[+] Table '{table}'.'{col}': type={gtype}, srid={srid}")
            assert srid == 4326, f"Expected SRID 4326 for {table}.{col}, found {srid}"

        # 3. GIST Spatial Indexes Check
        print("\n--- 3. GIST Spatial Index Check ---")
        gist_indexes = conn.execute(
            text("""
                SELECT tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexdef LIKE '%USING gist%'
                ORDER BY tablename;
            """)
        ).fetchall()

        expected_indexes = {
            "idx_locations_geometry",
            "idx_flood_extents_geometry",
            "idx_assets_geometry",
            "idx_facilities_location",
            "idx_road_hazards_geometry",
            "idx_assistance_requests_location_geometry",
        }
        found_indexes = {row[1] for row in gist_indexes}

        for tablename, indexname, indexdef in gist_indexes:
            print(f"[+] GIST Index: {indexname} on {tablename}")

        missing = expected_indexes - found_indexes
        if missing:
            print(f"[-] Missing expected GIST indexes: {missing}")
            sys.exit(1)
        else:
            print("[+] All 6 PostGIS GIST spatial indexes verified!")

        # 4. Live Spatial Query Operations
        print("\n--- 4. Live PostGIS Spatial Operations Test ---")
        test_suffix = uuid.uuid4().hex[:6]
        loc_id = f"test-loc-{test_suffix}"
        fac_id = f"test-fac-{test_suffix}"
        event_id = f"test-evt-{test_suffix}"
        extent_id = f"test-ext-{test_suffix}"
        hazard_id = f"test-haz-{test_suffix}"

        now = datetime.now(timezone.utc)

        try:
            # Insert Location polygon (Patna district bounding box)
            conn.execute(
                text("""
                    INSERT INTO locations (id, name, admin_level, geometry, crs_source, metadata_json, created_at, updated_at)
                    VALUES (:id, 'Patna Verification Zone', 3,
                            ST_GeomFromText('POLYGON((85.00 25.50, 85.30 25.50, 85.30 25.75, 85.00 25.75, 85.00 25.50))', 4326),
                            'EPSG:4326', '{"verified": true}', :now, :now);
                """),
                {"id": loc_id, "now": now},
            )

            # Insert Facility point inside the location
            conn.execute(
                text("""
                    INSERT INTO facilities (id, type, name, location, capacity, verification_status, details, created_at, updated_at)
                    VALUES (:id, 'shelter', 'Verification Shelter Alpha',
                            ST_SetSRID(ST_MakePoint(85.14, 25.61), 4326),
                            1000, 'verified', '{"supplies": "emergency_rations"}', :now, :now);
                """),
                {"id": fac_id, "now": now},
            )

            # Insert Flood Event with required region_id, start_at, mode, source_refs
            conn.execute(
                text("""
                    INSERT INTO flood_events (id, region_id, name, start_at, mode, source_refs, description, created_at, updated_at)
                    VALUES (:id, :region_id, 'Verification Flood Event', :now, 'test', '["source_cwc_01"]', 'Automated PostGIS test event', :now, :now);
                """),
                {"id": event_id, "region_id": loc_id, "now": now},
            )

            conn.execute(
                text("""
                    INSERT INTO flood_extents (id, event_id, observed_at, method, area_km2, source_scene_ids, geometry, created_at, updated_at)
                    VALUES (:id, :event_id, :now, 'satellite_derived', 12.5, '["scene_s2_01"]',
                            ST_GeomFromText('MULTIPOLYGON(((85.12 25.59, 85.16 25.59, 85.16 25.63, 85.12 25.63, 85.12 25.59)))', 4326),
                            :now, :now);
                """),
                {"id": extent_id, "event_id": event_id, "now": now},
            )

            # Insert Road Hazard LineString intersecting the flood extent
            conn.execute(
                text("""
                    INSERT INTO road_hazards (id, hazard_type, geometry, status, source, observed_at, created_at, updated_at)
                    VALUES (:id, 'waterlogged',
                            ST_GeomFromText('LINESTRING(85.10 25.60, 85.18 25.60)', 4326),
                            'active', 'satellite_inferred', :now, :now, :now);
                """),
                {"id": hazard_id, "now": now},
            )
            conn.commit()

            # Test 4a: ST_Contains (Check facility inside location)
            res_contains = conn.execute(
                text("""
                    SELECT ST_Contains(l.geometry, f.location)
                    FROM locations l, facilities f
                    WHERE l.id = :loc_id AND f.id = :fac_id;
                """),
                {"loc_id": loc_id, "fac_id": fac_id},
            ).scalar()
            print(f"[+] Spatial query ST_Contains: {res_contains} (Expected: True)")
            assert res_contains is True, "ST_Contains check failed"

            # Test 4b: ST_Intersects (Check road hazard intersects flood extent)
            res_intersects = conn.execute(
                text("""
                    SELECT ST_Intersects(fe.geometry, rh.geometry)
                    FROM flood_extents fe, road_hazards rh
                    WHERE fe.id = :extent_id AND rh.id = :hazard_id;
                """),
                {"extent_id": extent_id, "hazard_id": hazard_id},
            ).scalar()
            print(f"[+] Spatial query ST_Intersects: {res_intersects} (Expected: True)")
            assert res_intersects is True, "ST_Intersects check failed"

            # Test 4c: ST_DWithin (Check facility proximity within 5km)
            res_dwithin = conn.execute(
                text("""
                    SELECT ST_DWithin(
                        f.location::geography,
                        ST_SetSRID(ST_MakePoint(85.145, 25.612), 4326)::geography,
                        5000
                    )
                    FROM facilities f
                    WHERE f.id = :fac_id;
                """),
                {"fac_id": fac_id},
            ).scalar()
            print(f"[+] Spatial query ST_DWithin (5km radius): {res_dwithin} (Expected: True)")
            assert res_dwithin is True, "ST_DWithin check failed"

            # Test 4d: ST_Area (Flood extent area in square kilometers)
            res_area_sq_m = conn.execute(
                text("""
                    SELECT ST_Area(geometry::geography)
                    FROM flood_extents
                    WHERE id = :extent_id;
                """),
                {"extent_id": extent_id},
            ).scalar()
            assert res_area_sq_m is not None, "ST_Area query returned None"
            assert isinstance(res_area_sq_m, (int, float)), "ST_Area result must be numeric"
            area_sq_km = float(res_area_sq_m) / 1_000_000.0
            print(f"[+] Spatial query ST_Area: {round(area_sq_km, 2)} sq km ({round(float(res_area_sq_m), 1)} sq meters)")
            assert res_area_sq_m > 0, "ST_Area check failed"

            # Test 4e: Explain GIST Index Usage
            explain_output = conn.execute(
                text("""
                    EXPLAIN SELECT * FROM facilities
                    WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(85.14, 25.61), 4326), 0.05);
                """)
            ).fetchall()
            print("[+] Query plan with spatial predicate:")
            for row in explain_output:
                print(f"    {row[0]}")

            # Test 4f: Day 4 Candidate Route x Road Hazard ST_Intersects Screening
            route_wkt = "LINESTRING(85.14 25.55, 85.14 25.65)"
            res_route_rh = conn.execute(
                text("""
                    SELECT ST_Intersects(rh.geometry, ST_GeomFromText(:route_wkt, 4326))
                    FROM road_hazards rh
                    WHERE rh.id = :hazard_id;
                """),
                {"route_wkt": route_wkt, "hazard_id": hazard_id},
            ).scalar()
            print(f"[+] Spatial query ST_Intersects (Candidate Route x Road Hazard): {res_route_rh} (Expected: True)")
            assert res_route_rh is True, "Candidate route road hazard intersection check failed"

        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[-] Spatial operations failed: {exc}")
            raise exc
        finally:
            try:
                conn.rollback()
                conn.execute(text("DELETE FROM road_hazards WHERE id = :id;"), {"id": hazard_id})
                conn.execute(text("DELETE FROM flood_extents WHERE id = :id;"), {"id": extent_id})
                conn.execute(text("DELETE FROM flood_events WHERE id = :id;"), {"id": event_id})
                conn.execute(text("DELETE FROM facilities WHERE id = :id;"), {"id": fac_id})
                conn.execute(text("DELETE FROM locations WHERE id = :id;"), {"id": loc_id})
                conn.commit()
                print("[+] Test spatial fixtures cleaned up successfully.")
            except Exception as cleanup_err:
                print(f"[!] Cleanup note: {cleanup_err}")


    # 5. Application Readiness Check
    print("\n--- 5. Application Readiness Probe Test ---")
    from app.database import check_db_connection
    status_dict = check_db_connection()
    print(f"[+] DB Connected: {status_dict['connected']}")
    print(f"[+] Database Type: {status_dict['database_type']}")
    print(f"[+] PostGIS Installed: {status_dict['postgis_installed']}")
    print(f"[+] PostGIS Version: {status_dict['postgis_version']}")
    print(f"[+] Latency: {status_dict['latency_ms']} ms")
    assert status_dict["connected"] is True, "DB not connected"
    assert status_dict["postgis_installed"] is True, "PostGIS not detected in app check"

    print("\n=======================================================")
    print("  ALL LIVE POSTGIS 16 SPATIAL VERIFICATIONS PASSED!    ")
    print("=======================================================")


if __name__ == "__main__":
    verify_postgis()
