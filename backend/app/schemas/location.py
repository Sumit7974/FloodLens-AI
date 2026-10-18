"""Location and settlement schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    """Payload to register a new administrative unit, settlement, or hazard boundary."""
    id: Optional[str] = Field(default=None, description="Custom location ID (e.g. loc-nepal-terai-01)")
    name: str = Field(..., min_length=1, max_length=255, description="Settlement or administrative name")
    admin_level: int = Field(default=3, ge=1, le=5, description="1=Prov, 2=Dist, 3=Municipality, 4=Ward/Village")
    parent_id: Optional[str] = Field(default=None, description="Parent administrative unit ID")
    geometry: Optional[Union[Dict[str, Any], str]] = Field(
        default=None, description="GeoJSON Polygon/Point or WKT string in EPSG:4326"
    )
    crs_source: str = Field(default="EPSG:4326", description="Coordinate reference system")
    metadata_json: Dict[str, Any] = Field(default_factory=dict, description="Population, vulnerability, tags")


class LocationResponse(BaseModel):
    """Location entity response."""
    id: str
    name: str
    admin_level: int
    parent_id: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    crs_source: str
    metadata_json: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
