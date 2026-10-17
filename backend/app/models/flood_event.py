"""Flood event model representing historical demo or live flood episodes."""
from sqlalchemy import Column, DateTime, Enum, JSON, String, Text
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from app.models.enums import OperationalMode


class FloodEvent(Base, TimestampMixin):
    """Flood Event record tying forecasts, satellite observations, and evaluations together."""
    __tablename__ = "flood_events"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    region_id = Column(String(100), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=True)
    mode = Column(Enum(OperationalMode), default=OperationalMode.HISTORICAL_DEMO, nullable=False, index=True)
    source_refs = Column(JSON, default=dict, nullable=False)
    description = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<FloodEvent id={self.id} name={self.name} mode={self.mode}>"
