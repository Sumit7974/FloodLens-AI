"""Flood event and flood extent API schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.enums import OperationalMode


class FloodEventCreate(BaseModel):
    """Payload to create or import a verified flood event."""
    id: Optional[str] = Field(default=None, description="Optional custom ID; generated if omitted")
    region_id: str = Field(..., min_length=1, max_length=100, description="Target region/watershed identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Human readable event name")
    start_at: datetime = Field(..., description="UTC start datetime of the event episode")
    end_at: Optional[datetime] = Field(default=None, description="UTC end datetime if completed")
    mode: OperationalMode = Field(default=OperationalMode.HISTORICAL_DEMO, description="Operational or demo mode")
    source_refs: Dict[str, Any] = Field(default_factory=dict, description="Provenance data sources (CWC, DHM, etc.)")
    description: Optional[str] = Field(default=None, description="Detailed context or terrain description")

    @model_validator(mode="after")
    def validate_date_range(self) -> "FloodEventCreate":
        if self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at cannot be earlier than start_at")
        return self


class FloodEventResponse(BaseModel):
    """Flood event metadata schema."""
    id: str
    region_id: str
    name: str
    start_at: datetime
    end_at: Optional[datetime] = None
    mode: OperationalMode
    source_refs: Dict[str, Any]
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FloodExtentCreate(BaseModel):
    """Payload to ingest an observed flood extent derived from satellite scenes."""
    id: Optional[str] = Field(default=None, description="Extent ID or UUID")
    observed_at: datetime = Field(..., description="UTC timestamp of satellite observation")
    method: str = Field(..., min_length=1, max_length=50, description="Mapping method (NDWI, MNDWI, SAR_CHANGE)")
    area_km2: float = Field(..., gt=0.0, description="Derived inundated surface area in square kilometers")
    source_scene_ids: List[str] = Field(default_factory=list, description="IDs of input satellite scenes")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Detection confidence score (0.0 to 1.0)")
    polygon_ref: Optional[str] = Field(default=None, description="GeoJSON or Shapefile artifact storage path")
    raster_ref: Optional[str] = Field(default=None, description="GeoTIFF cloud-optimized raster storage path")
    geometry: Optional[Union[Dict[str, Any], str]] = Field(
        default=None,
        description="GeoJSON MultiPolygon/Polygon dict or WKT string georeferenced in EPSG:4326",
    )


class FloodExtentResponse(BaseModel):
    """Observed flood extent response matching GET /flood-events/{event_id}/extent."""
    id: str
    event_id: str
    observed_at: datetime
    method: str
    polygon_ref: Optional[str] = None
    raster_ref: Optional[str] = None
    area_km2: float
    source_scene_ids: List[str]
    confidence: Optional[float] = None
    geometry: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AffectedSettlementItem(BaseModel):
    """Settlement exposed or inundated by observed flood extent."""
    settlement_id: str
    name: str
    admin_level: int
    exposure_status: str = Field(..., description="inundated, partially_inundated, or exposed")
    intersection_area_km2: Optional[float] = None
    population_exposed: Optional[int] = None
    crs_source: Optional[str] = "EPSG:4326"
    geometry: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AffectedSettlementsResponse(BaseModel):
    """Response schema for GET /flood-events/{event_id}/settlements."""
    event_id: str
    region_id: str
    extent_id: Optional[str] = None
    observed_at: Optional[datetime] = None
    total_settlements_affected: int
    affected_settlements: List[AffectedSettlementItem]
    status: str = Field(..., description="completed, no_extent_available, or empty")


class ExposedAssetsResponse(BaseModel):
    """Response schema for GET /flood-events/{event_id}/assets."""
    event_id: str
    roads_exposed_km: float
    structures_exposed_count: int
    cropland_exposed_ha: float
    exposed_assets: List[Dict[str, Any]] = Field(default_factory=list)
    status: str


class FloodReportResponse(BaseModel):
    """Downloadable impact assessment report metadata schema."""
    event_id: str
    event_name: str
    region_id: str
    mode: str
    extent_observed_at: Optional[datetime] = None
    extent_area_km2: Optional[float] = None
    total_settlements_affected: int
    roads_exposed_km: float
    structures_exposed_count: int
    cropland_exposed_ha: float
    report_generated_at: datetime
    status: str
    download_url: Optional[str] = None
