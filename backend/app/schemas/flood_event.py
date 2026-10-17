"""Flood event and flood extent API schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import OperationalMode


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

