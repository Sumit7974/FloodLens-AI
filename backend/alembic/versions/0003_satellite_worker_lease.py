"""Add worker leasing, heartbeat columns and flood extent provenance

Revision ID: 0003_satellite_worker_lease
Revises: 0002_satellite_jobs
Create Date: 2026-10-23 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_satellite_worker_lease"
down_revision: Union[str, None] = "0002_satellite_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. SatelliteJob: worker identity, lease expiration timestamp, and heartbeat
    op.add_column("satellite_jobs", sa.Column("worker_id", sa.String(length=100), nullable=True))
    op.add_column("satellite_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("satellite_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_satellite_jobs_lease_expires_at", "satellite_jobs", ["lease_expires_at"])

    # 2. FloodExtent: provenance tracking (PROCESSED_OPTICAL, PROCESSED_SAR, IMPORTED_PRECOMPUTED, SYNTHETIC_TEST_FIXTURE)
    op.add_column("flood_extents", sa.Column("provenance", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("flood_extents", "provenance")
    op.drop_index("ix_satellite_jobs_lease_expires_at", table_name="satellite_jobs")
    op.drop_column("satellite_jobs", "heartbeat_at")
    op.drop_column("satellite_jobs", "lease_expires_at")
    op.drop_column("satellite_jobs", "worker_id")
