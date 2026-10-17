"""Evaluation and model benchmark records."""
from sqlalchemy import Column, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class Evaluation(Base, TimestampMixin):
    """Prediction vs observation evaluation and model candidate benchmark."""
    __tablename__ = "evaluations"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    event_id = Column(String(36), ForeignKey("flood_events.id"), nullable=False, index=True)
    target_type = Column(String(50), nullable=False)  # flood_extent, risk_forecast
    baseline_version = Column(String(50), nullable=False)
    candidate_version = Column(String(50), nullable=True)
    metrics = Column(JSON, default=dict, nullable=False)
    reference_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    event = relationship("FloodEvent", backref="evaluations")

    def __repr__(self) -> str:
        return f"<Evaluation id={self.id} event={self.event_id} target={self.target_type}>"
