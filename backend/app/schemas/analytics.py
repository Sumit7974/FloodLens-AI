"""Schemas for model evaluations, benchmark metrics, and model version listings."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class EvaluationItem(BaseModel):
    """Detailed evaluation benchmark record for a historical flood event."""
    id: str = Field(..., description="Unique evaluation identifier")
    event_id: str = Field(..., description="Referenced flood event identifier")
    target_type: str = Field(..., description="Evaluation target: flood_extent, risk_forecast, etc.")
    baseline_version: str = Field(..., description="Baseline model version benchmarked")
    candidate_version: Optional[str] = Field(default=None, description="Candidate model version if comparative benchmark")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Numerical evaluation metrics (IOU, F1, precision, MAE)")
    reference_id: Optional[str] = Field(default=None, description="Ground truth or reference scene/mask ID")
    notes: Optional[str] = Field(default=None, description="Methodological notes and limitations")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="UTC modification timestamp")

    model_config = ConfigDict(from_attributes=True)


class EventAnalyticsResponse(BaseModel):
    """Event-scoped analytics response consolidating all model evaluations for an event."""
    event_id: str = Field(..., description="Target flood event identifier")
    event_name: Optional[str] = Field(default=None, description="Human readable name of the flood event")
    mode: Optional[str] = Field(default=None, description="Operational or historical demo mode of the event")
    evaluations_count: int = Field(..., description="Number of evaluations recorded for this event")
    results: List[EvaluationItem] = Field(default_factory=list, description="List of evaluation benchmark records")
    status: str = Field(
        ...,
        description="Data status: evaluations_available or no_evaluations_recorded",
    )
    data_limitations: List[str] = Field(
        default_factory=list,
        description="Methodological limitations regarding ground truth availability or comparison bounds",
    )


class ModelVersionItem(BaseModel):
    """Information regarding an AI/ML hydrological or spatial model version."""
    version: str = Field(..., description="Model version tag e.g. baseline-v1")
    type: str = Field(..., description="Model architecture type e.g. hydrological_baseline")
    status: str = Field(..., description="Deployment or research status: active, research_prototype, deprecated")
    horizons: List[int] = Field(default_factory=list, description="Supported forecast horizons in hours (e.g. [1, 3, 6])")
    description: str = Field(..., description="Model description and operational scope")
    limitations: List[str] = Field(default_factory=list, description="Known operational limitations and assumptions")
