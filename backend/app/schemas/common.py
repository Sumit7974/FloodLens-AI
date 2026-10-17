"""Common base schemas, error representations, and GeoJSON shapes."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error object matching contract format."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    request_id: str = Field(..., description="Correlation request ID")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional extra error details")


class ErrorResponse(BaseModel):
    """Standard error response envelope."""
    error: ErrorDetail


class GeoJSONGeometry(BaseModel):
    """Standard RFC 7946 GeoJSON geometry representation."""
    type: str = Field(..., description="Geometry type: Point, MultiPolygon, etc.")
    coordinates: Any = Field(..., description="Coordinates array conforming to geometry type")


class GeoJSONFeature(BaseModel):
    """Standard RFC 7946 GeoJSON feature representation."""
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: Dict[str, Any] = Field(default_factory=dict)
