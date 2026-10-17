"""Infrastructure assets, emergency facilities, and road hazards."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from app.database import Base
from app.models.base import GeometryType, TimestampMixin, generate_uuid


class Asset(Base, TimestampMixin):
    """Critical infrastructure, buildings, roads, and agricultural assets."""
    __tablename__ = "assets"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    asset_type = Column(String(50), nullable=False, index=True)  # road, building, bridge, farmland
    geometry = Column(GeometryType("GEOMETRY", 4326), nullable=True)
    data_source_id = Column(String(50), ForeignKey("data_sources.id"), nullable=True)
    metadata_json = Column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<Asset id={self.id} type={self.asset_type}>"


class Facility(Base, TimestampMixin):
    """Verified and demo-labeled emergency shelters and hospitals."""
    __tablename__ = "facilities"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    type = Column(String(50), nullable=False, index=True)  # shelter, hospital
    name = Column(String(255), nullable=False)
    location = Column(GeometryType("POINT", 4326), nullable=True)
    verification_status = Column(String(50), default="unverified", nullable=False)  # verified, unverified, demo_labeled
    status_checked_at = Column(DateTime(timezone=True), nullable=True)
    capacity = Column(Integer, nullable=True)
    contact_info = Column(String(255), nullable=True)
    details = Column(JSON, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<Facility id={self.id} name={self.name} type={self.type} status={self.verification_status}>"


class RoadHazard(Base, TimestampMixin):
    """Identified road inundation or blockage hazards."""
    __tablename__ = "road_hazards"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    road_id = Column(String(50), nullable=True, index=True)
    hazard_type = Column(String(50), nullable=False)  # submerged, debris, bridge_closed
    geometry = Column(GeometryType("GEOMETRY", 4326), nullable=True)
    status = Column(String(50), default="active", nullable=False)  # active, cleared, unverified
    source = Column(String(100), default="satellite_inferred", nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    confidence = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<RoadHazard id={self.id} type={self.hazard_type} status={self.status}>"
