"""Authority emergency alert records and review workflows."""
from sqlalchemy import Column, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from app.models.enums import AlertStatus, OperationalMode


class Alert(Base, TimestampMixin):
    """Authority draft -> approval -> test dispatch alert record."""
    __tablename__ = "alerts"

    id = Column(String(50), primary_key=True, default=generate_uuid, index=True)
    area_id = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(
        Enum(AlertStatus, values_callable=lambda obj: [e.value for e in obj], name="alertstatus"),
        default=AlertStatus.DRAFT,
        nullable=False,
        index=True,
    )
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    mode = Column(
        Enum(OperationalMode, values_callable=lambda obj: [e.value for e in obj], name="operationalmode"),
        default=OperationalMode.HISTORICAL_DEMO,
        nullable=False,
    )
    target_channels = Column(JSON, default=list, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[created_by], backref="created_alerts")
    approver = relationship("User", foreign_keys=[approved_by], backref="approved_alerts")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} status={self.status} area={self.area_id}>"
