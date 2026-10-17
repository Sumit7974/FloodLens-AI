"""Forecast and risk prediction API contract schemas."""
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    def normalize_data_quality(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    model_config = ConfigDict(from_attributes=True)

