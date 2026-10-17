"""Location model for administrative units, settlements, and hazard regions."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import GeometryType, TimestampMixin, generate_uuid


class Location(Base, TimestampMixin):
    """Geographic location / administrative boundary / settlement entity."""
    __tablename__ = "locations"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    name = Column(String(255), index=True, nullable=False)
    admin_level = Column(Integer, default=3, nullable=False)  # 1=Prov, 2=Dist, 3=Municipality, 4=Ward/Village
    parent_id = Column(String(50), ForeignKey("locations.id"), nullable=True, index=True)
    geometry = Column(GeometryType("GEOMETRY", 4326), nullable=True)
    crs_source = Column(String(50), default="EPSG:4326", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    # Relationships
    children = relationship("Location", backref="parent", remote_side=[id])

    def __repr__(self) -> str:
        return f"<Location id={self.id} name={self.name} admin_level={self.admin_level}>"
