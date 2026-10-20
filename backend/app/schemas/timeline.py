"""Schemas for Historical Event Replay Timeline (Task 4)."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TimelineEntry(BaseModel):
    """A single chronological event milestone in a historical flood event replay."""
    entry_id: str = Field(..., description="Unique entry identifier or resource ID")
    timestamp: datetime = Field(..., description="Chronological UTC ISO 8601 timestamp for sorting")
    entry_type: Literal[
        "event_start",
        "event_end",
        "forecast_issued",
        "flood_observation",
        "evaluation_recorded",
    ] = Field(
        ...,
        description="Type of timeline milestone",
    )
    title: str = Field(..., description="Human-readable title of the timeline entry")
    description: Optional[str] = Field(default=None, description="Descriptive summary of the event entry")
    resource_id: str = Field(..., description="Underlying database resource ID")
    resource_type: Literal[
        "flood_event",
        "forecast_run",
        "flood_extent",
        "evaluation",
    ] = Field(
        ...,
        description="Underlying database model table/resource type",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed record attributes (e.g. valid_at horizons, satellite method, area_km2, metrics)",
    )
    data_quality: Optional[str] = Field(default=None, description="Data quality indicator if applicable (e.g. FULL, PARTIAL)")
    limitations: List[str] = Field(
        default_factory=list,
        description="Caveats or missing data notes associated with this entry",
    )

    model_config = ConfigDict(from_attributes=True)


class EventTimelineCoverage(BaseModel):
    """Coverage summary of persisted historical records for this event."""
    has_forecasts: bool = Field(..., description="Whether forecast runs exist for this event")
    forecast_runs_count: int = Field(default=0, description="Total forecast runs linked to this event")
    has_flood_extents: bool = Field(..., description="Whether observed satellite flood extents exist")
    flood_extents_count: int = Field(default=0, description="Total satellite flood extents linked to this event")
    has_evaluations: bool = Field(..., description="Whether model evaluations exist for this event")
    evaluations_count: int = Field(default=0, description="Total evaluation records linked to this event")


class EventTimelineResponse(BaseModel):
    """Chronologically sorted timeline representation of a historical flood event."""
    event_id: str = Field(..., description="Flood event identifier")
    event_name: str = Field(..., description="Official flood event name")
    region_id: str = Field(..., description="Study area or watershed region ID")
    mode: str = Field(..., description="Operational mode (historical_demo or live)")
    start_at: datetime = Field(..., description="Event episode start time")
    end_at: Optional[datetime] = Field(default=None, description="Event episode end time if completed")
    timeline_generated_at: datetime = Field(..., description="UTC timestamp when this timeline API was invoked")
    total_entries: int = Field(..., description="Total milestones in the timeline")
    coverage: EventTimelineCoverage = Field(..., description="Summary of database records available for this event")
    entries: List[TimelineEntry] = Field(
        default_factory=list,
        description="Strictly sorted chronological entries (earliest to latest)",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Explanatory notes regarding event linkages and demonstration context",
    )
