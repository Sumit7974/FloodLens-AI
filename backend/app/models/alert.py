"""Authority emergency alert records and review workflows."""
from datetime import datetime
from typing import ClassVar, Optional
from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Table, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from app.models.enums import AlertStatus, OperationalMode


class AlertBase(DeclarativeBase):
    """DeclarativeBase bridge sharing the global Base registry for native typing."""
    registry = Base.registry


class Alert(AlertBase, TimestampMixin):
    """Authority draft -> approval -> test dispatch alert record."""
    __tablename__ = "alerts"
    __table__: ClassVar[Table]

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=generate_uuid, index=True)
    area_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, values_callable=lambda obj: [e.value for e in obj], name="alertstatus"),
        default=AlertStatus.DRAFT,
        nullable=False,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mode: Mapped[OperationalMode] = mapped_column(
        Enum(OperationalMode, values_callable=lambda obj: [e.value for e in obj], name="operationalmode"),
        default=OperationalMode.HISTORICAL_DEMO,
        nullable=False,
    )
    target_channels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[created_by], backref="created_alerts")
    approver = relationship("User", foreign_keys=[approved_by], backref="approved_alerts")

    def __repr__(self) -> str:
        return f"<Alert id={self.id} status={self.status} area={self.area_id}>"
