"""Add satellite_jobs table for asynchronous satellite processing pipeline

Revision ID: 0002_satellite_jobs
Revises: 0001_initial_schema
Create Date: 2026-10-23 03:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_satellite_jobs"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satellite_jobs",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("event_id", sa.String(length=36), sa.ForeignKey("flood_events.id"), nullable=True),
        sa.Column("scene_id", sa.String(length=100), sa.ForeignKey("satellite_scenes.id"), nullable=True),
        sa.Column("baseline_scene_id", sa.String(length=100), sa.ForeignKey("satellite_scenes.id"), nullable=True),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="QUEUED"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("requested_by", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_extent_id", sa.String(length=100), sa.ForeignKey("flood_extents.id"), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_satellite_jobs_id", "satellite_jobs", ["id"])
    op.create_index("ix_satellite_jobs_status", "satellite_jobs", ["status"])
    op.create_index("ix_satellite_jobs_event_id", "satellite_jobs", ["event_id"])
    op.create_index("ix_satellite_jobs_scene_id", "satellite_jobs", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_satellite_jobs_scene_id", table_name="satellite_jobs")
    op.drop_index("ix_satellite_jobs_event_id", table_name="satellite_jobs")
    op.drop_index("ix_satellite_jobs_status", table_name="satellite_jobs")
    op.drop_index("ix_satellite_jobs_id", table_name="satellite_jobs")
    op.drop_table("satellite_jobs")
