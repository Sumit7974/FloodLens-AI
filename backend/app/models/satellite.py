"""Satellite scenes and observed flood extent records."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import GeometryType, TimestampMixin, generate_uuid


class SatelliteScene(Base, TimestampMixin):
    """Raw or preprocessed satellite scene metadata."""
    __tablename__ = "satellite_scenes"

    id = Column(String(100), primary_key=True, default=generate_uuid, index=True)
    provider = Column(String(100), nullable=False)  # ESA, Copernicus, USGS
    sensor = Column(String(50), nullable=False)     # Sentinel-2, Sentinel-1
    modality = Column(String(50), nullable=False)   # optical, sar
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    cloud_quality = Column(Float, nullable=True)    # Cloud cover percentage (0.0 to 1.0)
    asset_ref = Column(String(500), nullable=False) # File path or object store URI
    bbox_geojson = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<SatelliteScene id={self.id} sensor={self.sensor} captured_at={self.captured_at}>"


class FloodExtent(Base, TimestampMixin):
    """Derived flood extent mask / polygon layer from satellite imagery."""
    __tablename__ = "flood_extents"

    id = Column(String(100), primary_key=True, default=generate_uuid, index=True)
    event_id = Column(String(36), ForeignKey("flood_events.id"), nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    method = Column(String(50), nullable=False)     # NDWI, MNDWI, SAR_CHANGE
    polygon_ref = Column(String(500), nullable=True) # GeoJSON or shapefile reference
    raster_ref = Column(String(500), nullable=True)  # GeoTIFF raster path
    area_km2 = Column(Float, nullable=False)
    source_scene_ids = Column(JSON, default=list, nullable=False)
    confidence = Column(Float, nullable=True)
    geometry = Column(GeometryType("MULTIPOLYGON", 4326), nullable=True)

    # Relationships
    event = relationship("FloodEvent", backref="flood_extents")

    def __repr__(self) -> str:
        return f"<FloodExtent id={self.id} event={self.event_id} area_km2={self.area_km2} method={self.method}>"
