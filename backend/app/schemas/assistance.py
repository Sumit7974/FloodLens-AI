"""Citizen assistance request schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import AssistanceCategory, AssistanceStatus


class AssistanceCreateRequest(BaseModel):
    """Citizen emergency assistance request schema."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    category: AssistanceCategory = Field(default=AssistanceCategory.OTHER, description="evacuation, medical, food_water, etc.")
    details: Optional[str] = Field(default=None, description="Optional description of immediate needs")
    people_count: int = Field(default=1, ge=1, le=100, description="Number of individuals needing help")


class AssistanceUpdateRequest(BaseModel):
    """Authority status update request schema."""
    status: AssistanceStatus = Field(..., description="Updated status: acknowledged, in_progress, resolved")
    assigned_to: Optional[str] = Field(default=None, description="Responder user ID")
    status_notes: Optional[str] = Field(default=None, description="Operational notes")


class AssistanceResponse(BaseModel):
    """Assistance request response schema."""
    id: str
    citizen_id: str
    latitude: float
    longitude: float
    category: AssistanceCategory
    status: AssistanceStatus
    details: Optional[str] = None
    people_count: int
    assigned_to: Optional[str] = None
    status_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

