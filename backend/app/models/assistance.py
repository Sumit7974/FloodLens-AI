"""Citizen assistance request records for emergency responder queues."""
from sqlalchemy import Column, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import GeometryType, TimestampMixin, generate_uuid
from app.models.enums import AssistanceCategory, AssistanceStatus


class AssistanceRequest(Base, TimestampMixin):
    """Citizen assistance request with restricted responder access."""
    __tablename__ = "assistance_requests"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    citizen_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_geometry = Column(GeometryType("POINT", 4326), nullable=True)
    category = Column(Enum(AssistanceCategory), default=AssistanceCategory.OTHER, nullable=False)
    status = Column(Enum(AssistanceStatus), default=AssistanceStatus.PENDING, nullable=False, index=True)
    details = Column(Text, nullable=True)
    people_count = Column(Integer, default=1, nullable=False)
    assigned_to = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    status_notes = Column(Text, nullable=True)

    # Relationships
    citizen = relationship("User", foreign_keys=[citizen_id], backref="assistance_requests")
    assignee = relationship("User", foreign_keys=[assigned_to], backref="assigned_assistance_tasks")

    def __repr__(self) -> str:
        return f"<AssistanceRequest id={self.id} category={self.category} status={self.status}>"
