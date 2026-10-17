"""Emergency alert schemas for authority review and test dispatch."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import AlertStatus, OperationalMode


class AlertCreateRequest(BaseModel):
    """Authority draft alert creation schema."""
    area_id: str = Field(..., description="Target area or settlement location ID")
    title: str = Field(..., max_length=255, description="Alert headline")
    message: str = Field(..., description="Clear advisory or instruction text")
    mode: OperationalMode = Field(default=OperationalMode.HISTORICAL_DEMO, description="Operational state")
    target_channels: List[str] = Field(default_factory=lambda: ["in_app"], description="Channels: in_app, push, sms")


class AlertApprovalRequest(BaseModel):
    """Authority approval request schema."""
    notes: Optional[str] = Field(default=None, description="Optional audit approval note")


class AlertResponse(BaseModel):
    """Alert response schema."""
    id: str
    area_id: str
    title: str
    message: str
    status: AlertStatus
    created_by: str
    approved_by: Optional[str] = None
    issued_at: Optional[datetime] = None
    mode: OperationalMode
    target_channels: List[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

