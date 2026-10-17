"""Initial database schema with PostGIS extension and core records

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Enable PostGIS extension on PostgreSQL if available
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("citizen", "authority", "admin", name="userrole"),
            nullable=False,
            server_default="citizen",
        ),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("contact_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # 2. locations (with PostGIS Geometry column)
    op.create_table(
        "locations",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("admin_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("parent_id", sa.String(length=50), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column("crs_source", sa.String(length=50), nullable=False, server_default="EPSG:4326"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_locations_name", "locations", ["name"])
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])

    # 3. data_sources
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_data_sources_kind", "data_sources", ["kind"])

    # 4. flood_events
    op.create_table(
        "flood_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("region_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mode",
            sa.Enum("historical_demo", "test", "live_observation", "model_estimate", name="operationalmode"),
            nullable=False,
            server_default="historical_demo",
        ),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flood_events_region_id", "flood_events", ["region_id"])

    # 5. forecast_runs
    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("event_id", sa.String(length=36), sa.ForeignKey("flood_events.id"), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("input_data_cutoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mode",
            sa.Enum("historical_demo", "test", "live_observation", "model_estimate", name="operationalmode"),
            nullable=False,
            server_default="historical_demo",
        ),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="completed"),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_runs_event_id", "forecast_runs", ["event_id"])

    # 6. risk_predictions
    op.create_table(
        "risk_predictions",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("forecast_run_id", sa.String(length=50), sa.ForeignKey("forecast_runs.id"), nullable=False),
        sa.Column("location_id", sa.String(length=50), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("valid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MODERATE", "HIGH", "CRITICAL", name="risklevel"),
            nullable=False,
        ),
        sa.Column("calibrated_probability", sa.Float(), nullable=True),
        sa.Column("geometry_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "data_quality",
            sa.Enum("FULL", "PARTIAL", "DEGRADED", "UNAVAILABLE", name="dataquality"),
            nullable=False,
            server_default="PARTIAL",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_predictions_run_id", "risk_predictions", ["forecast_run_id"])
    op.create_index("ix_risk_predictions_loc_id", "risk_predictions", ["location_id"])

    # 7. satellite_scenes
    op.create_table(
        "satellite_scenes",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("sensor", sa.String(length=50), nullable=False),
        sa.Column("modality", sa.String(length=50), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_quality", sa.Float(), nullable=True),
        sa.Column("asset_ref", sa.String(length=500), nullable=False),
        sa.Column("bbox_geojson", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_satellite_scenes_captured_at", "satellite_scenes", ["captured_at"])

    # 8. flood_extents (with PostGIS MultiPolygon Geometry)
    op.create_table(
        "flood_extents",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("event_id", sa.String(length=36), sa.ForeignKey("flood_events.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("polygon_ref", sa.String(length=500), nullable=True),
        sa.Column("raster_ref", sa.String(length=500), nullable=True),
        sa.Column("area_km2", sa.Float(), nullable=False),
        sa.Column("source_scene_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flood_extents_event_id", "flood_extents", ["event_id"])

    # 9. assets (with PostGIS Geometry)
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column("data_source_id", sa.String(length=50), sa.ForeignKey("data_sources.id"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_type", "assets", ["asset_type"])

    # 10. facilities (with PostGIS Point Location)
    op.create_table(
        "facilities",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="unverified"),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("contact_info", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_facilities_type", "facilities", ["type"])

    # 11. road_hazards (with PostGIS Geometry)
    op.create_table(
        "road_hazards",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("road_id", sa.String(length=50), nullable=True),
        sa.Column("hazard_type", sa.String(length=50), nullable=False),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="satellite_inferred"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 12. alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("area_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "approved", "dispatched", "cancelled", name="alertstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "mode",
            sa.Enum("historical_demo", "test", "live_observation", "model_estimate", name="operationalmode"),
            nullable=False,
            server_default="historical_demo",
        ),
        sa.Column("target_channels", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_area_id", "alerts", ["area_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])

    # 13. assistance_requests (with PostGIS Point Location Geometry)
    op.create_table(
        "assistance_requests",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("citizen_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "location_geometry",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False).with_variant(sa.Text(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "category",
            sa.Enum("evacuation", "medical", "food_water", "shelter", "other", name="assistancecategory"),
            nullable=False,
            server_default="other",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "acknowledged", "in_progress", "resolved", "cancelled", name="assistancestatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("people_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assigned_to", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assistance_citizen_id", "assistance_requests", ["citizen_id"])
    op.create_index("ix_assistance_status", "assistance_requests", ["status"])

    # 14. evaluations
    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=50), primary_key=True),
        sa.Column("event_id", sa.String(length=36), sa.ForeignKey("flood_events.id"), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("baseline_version", sa.String(length=50), nullable=False),
        sa.Column("candidate_version", sa.String(length=50), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluations_event_id", "evaluations", ["event_id"])

    # PostGIS GIST Spatial Indexes (on PostgreSQL)
    if is_postgres:
        op.create_index("idx_locations_geometry", "locations", ["geometry"], postgresql_using="gist")
        op.create_index("idx_flood_extents_geometry", "flood_extents", ["geometry"], postgresql_using="gist")
        op.create_index("idx_assets_geometry", "assets", ["geometry"], postgresql_using="gist")
        op.create_index("idx_facilities_location", "facilities", ["location"], postgresql_using="gist")
        op.create_index("idx_road_hazards_geometry", "road_hazards", ["geometry"], postgresql_using="gist")
        op.create_index("idx_assistance_requests_location_geometry", "assistance_requests", ["location_geometry"], postgresql_using="gist")


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index("idx_assistance_requests_location_geometry", table_name="assistance_requests")
        op.drop_index("idx_road_hazards_geometry", table_name="road_hazards")
        op.drop_index("idx_facilities_location", table_name="facilities")
        op.drop_index("idx_assets_geometry", table_name="assets")
        op.drop_index("idx_flood_extents_geometry", table_name="flood_extents")
        op.drop_index("idx_locations_geometry", table_name="locations")

    op.drop_table("evaluations")
    op.drop_table("assistance_requests")
    op.drop_table("alerts")
    op.drop_table("road_hazards")
    op.drop_table("facilities")
    op.drop_table("assets")
    op.drop_table("flood_extents")
    op.drop_table("satellite_scenes")
    op.drop_table("risk_predictions")
    op.drop_table("forecast_runs")
    op.drop_table("flood_events")
    op.drop_table("data_sources")
    op.drop_table("locations")
    op.drop_table("users")

    if is_postgres:
        op.execute("DROP TYPE IF EXISTS userrole;")
        op.execute("DROP TYPE IF EXISTS operationalmode;")
        op.execute("DROP TYPE IF EXISTS risklevel;")
        op.execute("DROP TYPE IF EXISTS dataquality;")
        op.execute("DROP TYPE IF EXISTS alertstatus;")
        op.execute("DROP TYPE IF EXISTS assistancecategory;")
        op.execute("DROP TYPE IF EXISTS assistancestatus;")
