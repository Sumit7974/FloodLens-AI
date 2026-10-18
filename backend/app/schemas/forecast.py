"""Forecast and risk prediction API contract schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import DataQuality, OperationalMode, RiskLevel


class HorizonRisk(BaseModel):
    """Horizon specific risk prediction item (e.g. +1h, +3h, +6h)."""
    hours: int = Field(..., description="Horizon duration in hours (1, 3, 6)")
    risk_level: str = Field(..., description="Risk severity: low, moderate, high, critical")
    calibrated_probability: Optional[float] = Field(default=None, description="Calibrated probability if evidence-backed")

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk_level(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class HorizonRiskInput(BaseModel):
    """Input payload for a single horizon risk prediction (+1h, +3h, +6h)."""
    hours: int = Field(..., description="Horizon duration in hours (1, 3, 6)")
    risk_level: str = Field(..., description="Risk severity: low, moderate, high, critical")
    calibrated_probability: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Calibrated probability if evidence-backed"
    )
    valid_at: Optional[datetime] = Field(default=None, description="Target valid UTC timestamp")
    geometry_ref: Optional[str] = Field(default=None, description="Optional spatial geometry reference")
    data_quality: Optional[str] = Field(default=None, description="Optional override data quality indicator")

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: int) -> int:
        if v not in (1, 3, 6, 12, 24):
            raise ValueError(f"Forecast horizon must be a recognized hour increment (1, 3, 6), got {v}")
        return v

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_input_risk_level(cls, v: str) -> str:
        if isinstance(v, str):
            clean = v.strip().lower()
            valid_levels = {"low", "moderate", "high", "critical"}
            if clean not in valid_levels:
                raise ValueError(f"Invalid risk_level '{v}'. Expected one of: {valid_levels}")
            return clean
        return v


class ForecastIngestRequest(BaseModel):
    """Ingestion payload from Member 3 (AI/ML risk baseline pipeline)."""
    forecast_id: Optional[str] = Field(default=None, description="Custom forecast run ID or generated UUID")
    event_id: Optional[str] = Field(default=None, description="Associated flood event ID if known")
    location_id: str = Field(..., min_length=1, description="Associated location or village ID")
    issued_at: datetime = Field(..., description="UTC timestamp when forecast was issued")
    mode: OperationalMode = Field(default=OperationalMode.HISTORICAL_DEMO, description="historical_demo, test, live_observation")
    model_version: str = Field(..., min_length=1, max_length=50, description="Model version identifier, e.g. baseline-v1")
    input_data_cutoff_at: Optional[datetime] = Field(default=None, description="Data cutoff UTC timestamp")
    data_quality: DataQuality = Field(default=DataQuality.PARTIAL, description="Data quality: FULL, PARTIAL, DEGRADED, UNAVAILABLE")
    horizons: List[HorizonRiskInput] = Field(
        ...,
        min_length=1,
        description="Horizon risk predictions (e.g. +1h, +3h, +6h)",
    )
    limitations: List[str] = Field(default_factory=list, description="Documented limitations, missing gauges, or caveats")

    @field_validator("data_quality", mode="before")
    @classmethod
    def normalize_data_quality(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def validate_horizons_coverage(self) -> "ForecastIngestRequest":
        hours_present = {h.hours for h in self.horizons}
        # Verify at least one of the standard core horizons (+1h, +3h, or +6h) is provided
        if not (hours_present & {1, 3, 6}):
            raise ValueError("Forecast must contain predictions for at least one core horizon (+1h, +3h, or +6h)")
        return self


class ForecastResponse(BaseModel):
    """Latest forecast response matching the contract in DATABASE_API_EVENT_CONTRACTS.md."""
    forecast_id: str = Field(..., description="Unique forecast run identifier")
    location_id: str = Field(..., description="Associated location or village ID")
    issued_at: datetime = Field(..., description="UTC timestamp when forecast was issued")
    mode: str = Field(default="historical_demo", description="historical_demo, test, live_observation")
    model_version: str = Field(..., description="Model version identifier, e.g. baseline-v1")
    data_quality: str = Field(default="partial", description="Data quality status: full, partial, degraded, unavailable")
    horizons: List[HorizonRisk] = Field(..., description="1-hour, 3-hour, and 6-hour risk horizon forecasts")
    limitations: List[str] = Field(default_factory=list, description="Documented limitations, missing gauges, or caveats")

    @field_validator("data_quality", mode="before")
    @classmethod
    def normalize_data_quality(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value).lower()
        if isinstance(v, str):
            return v.strip().lower()
        return str(v).lower()

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)

    model_config = ConfigDict(from_attributes=True)


class PredictionMapFeature(BaseModel):
    """GeoJSON Feature for a predicted flood risk zone."""
    type: str = "Feature"
    id: str
    properties: Dict[str, Any]
    geometry: Optional[Dict[str, Any]] = None


class PredictionMapResponse(BaseModel):
    """Database-backed risk-zone map layer descriptor and features."""
    layer_id: str
    layer_type: str = "risk_zones"
    description: str = "Multi-horizon predicted flood risk zones"
    crs: str = "EPSG:4326"
    active_horizons: List[int] = Field(default_factory=lambda: [1, 3, 6])
    issued_at: Optional[datetime] = None
    model_version: Optional[str] = None
    mode: Optional[str] = None
    data_quality: Optional[str] = None
    status: str = Field(..., description="active, no_data, or degraded")
    total_zones: int = 0
    features: List[Dict[str, Any]] = Field(default_factory=list)
