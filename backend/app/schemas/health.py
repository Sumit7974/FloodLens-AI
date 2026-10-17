"""Health check schemas for GET /api/v1/health."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    """Database connectivity and PostGIS status."""
    connected: bool = Field(..., description="Whether database connection succeeded")
    database_type: str = Field(..., description="Database engine dialect, e.g. postgresql or sqlite")
    postgis_installed: bool = Field(..., description="Whether PostGIS extension is installed and available")
    postgis_version: Optional[str] = Field(default=None, description="PostGIS extension version string")
    latency_ms: Optional[float] = Field(default=None, description="Database ping latency in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if connection failed")


class HealthResponse(BaseModel):
    """System health response envelope."""
    status: str = Field(..., description="Overall service status: healthy or degraded")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application semantic version")
    environment: str = Field(..., description="Runtime environment")
    operational_mode: str = Field(..., description="Operational mode: historical_demo, test, live_observation")
    timestamp: datetime = Field(..., description="Current UTC timestamp")
    database: DatabaseHealth = Field(..., description="Database component health")


class ReadinessCheck(BaseModel):
    """Individual component readiness check."""
    name: str = Field(..., description="Subsystem component name (e.g. database, postgis)")
    status: str = Field(..., description="Component readiness status: ok or failed")
    details: Optional[str] = Field(default=None, description="Detailed diagnostic or latency message")


class ReadinessResponse(BaseModel):
    """Service readiness response envelope."""
    status: str = Field(..., description="Overall readiness: ready or not_ready")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application semantic version")
    environment: str = Field(..., description="Runtime environment")
    timestamp: datetime = Field(..., description="Current UTC timestamp")
    database: DatabaseHealth = Field(..., description="Database component health")
    checks: list[ReadinessCheck] = Field(default_factory=list, description="Subsystem readiness check results")

