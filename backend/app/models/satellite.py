"""Satellite scenes and observed flood extent records."""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
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
    provenance = Column(String(100), nullable=True)
    geometry = Column(GeometryType("MULTIPOLYGON", 4326), nullable=True)

    # Relationships
    event = relationship("FloodEvent", backref="flood_extents")

    def __repr__(self) -> str:
        return f"<FloodExtent id={self.id} event={self.event_id} area_km2={self.area_km2} method={self.method}>"


class SatelliteJob(Base, TimestampMixin):
    """Durable asynchronous satellite imagery processing job record."""
    __tablename__ = "satellite_jobs"

    id = Column(String(100), primary_key=True, default=lambda: f"sat_job_{generate_uuid()[:12]}", index=True)
    event_id = Column(String(36), ForeignKey("flood_events.id"), nullable=True, index=True)
    scene_id = Column(String(100), ForeignKey("satellite_scenes.id"), nullable=True, index=True)
    baseline_scene_id = Column(String(100), ForeignKey("satellite_scenes.id"), nullable=True)
    method = Column(String(50), nullable=False)     # NDWI, SAR_CHANGE
    threshold = Column(Float, nullable=True, default=0.0)
    status = Column(String(50), nullable=False, default="QUEUED", index=True)  # QUEUED, RUNNING, COMPLETED, FAILED
    progress_percent = Column(Float, nullable=False, default=0.0)
    requested_by = Column(String(100), nullable=False)
    worker_id = Column(String(100), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    output_extent_id = Column(String(100), ForeignKey("flood_extents.id"), nullable=True)
    error_message = Column(String(1000), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=2, nullable=False)
    parameters = Column(JSON, default=dict, nullable=True)
    provenance = Column(String(100), nullable=True)

    # Relationships
    event = relationship("FloodEvent", backref="satellite_jobs")
    scene = relationship("SatelliteScene", foreign_keys=[scene_id])
    baseline_scene = relationship("SatelliteScene", foreign_keys=[baseline_scene_id])
    output_extent = relationship("FloodExtent", foreign_keys=[output_extent_id])

    def __repr__(self) -> str:
        return f"<SatelliteJob id={self.id} method={self.method} status={self.status}>"
