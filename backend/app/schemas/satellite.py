"""Satellite scenes and processing job schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SatelliteSceneCreate(BaseModel):
    """Payload to register or import a raw or preprocessed satellite scene."""
    id: Optional[str] = Field(default=None, description="Custom scene ID (e.g. S2A_MSIL2A_...)")
    provider: str = Field(..., min_length=1, max_length=100, description="Imagery provider (ESA, Copernicus, USGS)")
    sensor: str = Field(..., min_length=1, max_length=50, description="Sensor name (Sentinel-2, Sentinel-1, Landsat-8)")
    modality: str = Field(..., min_length=1, max_length=50, description="Sensor modality: optical, sar")
    captured_at: datetime = Field(..., description="UTC acquisition timestamp of the imagery")
    cloud_quality: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Cloud cover fraction from 0.0 (cloudless) to 1.0 (fully obscured)"
    )
    asset_ref: str = Field(..., min_length=1, max_length=500, description="Storage URI or filesystem path to scene data")
    bbox_geojson: Optional[Dict[str, Any]] = Field(default=None, description="Bounding box or footprint GeoJSON polygon")


class SatelliteSceneResponse(BaseModel):
    """Satellite scene metadata schema."""
    id: str
    provider: str
    sensor: str
    modality: str
    captured_at: datetime
    cloud_quality: Optional[float] = None
    asset_ref: str
    bbox_geojson: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SatelliteJobCreate(BaseModel):
    """Job dispatch request for satellite extent processing."""
    event_id: str = Field(..., min_length=1, max_length=36, description="Target flood event ID (required)")
    scene_id: str = Field(..., min_length=1, max_length=100, description="Primary scene identifier to process (required)")
    baseline_scene_id: Optional[str] = Field(default=None, description="Pre-flood baseline scene for change detection")
    method: str = Field(default="NDWI", description="Index or method: NDWI, MNDWI, SAR_CHANGE")
    threshold: Optional[float] = Field(default=0.0, description="Water index decision threshold")


class SatelliteJobResponse(BaseModel):
    """Response after scheduling a satellite processing pipeline."""
    job_id: str
    status: str
    message: str
    requested_by: str
    created_at: datetime


class SatelliteJobDetailResponse(BaseModel):
    """Comprehensive job status and artifact provenance detail schema."""
    job_id: str
    status: str
    progress_percent: float = 0.0
    method: str
    threshold: Optional[float] = None
    event_id: Optional[str] = None
    scene_id: Optional[str] = None
    baseline_scene_id: Optional[str] = None
    requested_by: Optional[str] = None
    worker_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    heartbeat_at: Optional[datetime] = None
    output_extent_id: Optional[str] = None
    error_message: Optional[str] = None
    provenance: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
