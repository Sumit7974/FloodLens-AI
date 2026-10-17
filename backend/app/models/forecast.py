"""Forecast run and risk prediction database models."""
from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from app.models.enums import DataQuality, OperationalMode, RiskLevel


class ForecastRun(Base, TimestampMixin):
    """Forecast execution run tying inputs, cutoff timestamps, and prediction outputs."""
    __tablename__ = "forecast_runs"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    event_id = Column(String(36), ForeignKey("flood_events.id"), nullable=True, index=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    model_version = Column(String(50), nullable=False)
    input_data_cutoff_at = Column(DateTime(timezone=True), nullable=True)
    mode = Column(
        Enum(OperationalMode, values_callable=lambda obj: [e.value for e in obj], name="operationalmode"),
        default=OperationalMode.HISTORICAL_DEMO,
        nullable=False,
    )
    status = Column(String(50), default="completed", nullable=False)
    limitations = Column(JSON, default=list, nullable=False)

    # Relationships
    event = relationship("FloodEvent", backref="forecast_runs")
    predictions = relationship("RiskPrediction", back_populates="forecast_run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ForecastRun id={self.id} model={self.model_version} issued_at={self.issued_at}>"


class RiskPrediction(Base, TimestampMixin):
    """Specific horizon risk prediction for a target location."""
    __tablename__ = "risk_predictions"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    forecast_run_id = Column(String(50), ForeignKey("forecast_runs.id"), nullable=False, index=True)
    location_id = Column(String(50), ForeignKey("locations.id"), nullable=False, index=True)
    valid_at = Column(DateTime(timezone=True), nullable=False)
    horizon_hours = Column(Integer, nullable=False)  # 1, 3, 6
    risk_level = Column(
        Enum(RiskLevel, values_callable=lambda obj: [e.value for e in obj], name="risklevel"),
        nullable=False,
    )
    calibrated_probability = Column(Float, nullable=True)
    geometry_ref = Column(String(255), nullable=True)
    data_quality = Column(
        Enum(DataQuality, values_callable=lambda obj: [e.value for e in obj], name="dataquality"),
        default=DataQuality.PARTIAL,
        nullable=False,
    )

    # Relationships
    forecast_run = relationship("ForecastRun", back_populates="predictions")
    location = relationship("Location", backref="risk_predictions")

    def __repr__(self) -> str:
        return f"<RiskPrediction id={self.id} loc={self.location_id} h={self.horizon_hours} risk={self.risk_level}>"
