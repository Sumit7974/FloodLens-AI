"""Data source tracking model for weather, hydrological, and satellite providers."""
from sqlalchemy import Column, DateTime, JSON, String
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class DataSource(Base, TimestampMixin):
    """External data provider tracking with observation freshness status."""
    __tablename__ = "data_sources"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    kind = Column(String(50), nullable=False, index=True)  # weather, river_gauge, dam, satellite, osm
    provider = Column(String(100), nullable=False)
    last_observed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="active", nullable=False)  # active, degraded, unavailable
    config = Column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<DataSource id={self.id} kind={self.kind} provider={self.provider} status={self.status}>"
