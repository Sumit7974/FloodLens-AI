"""WebSocket event schemas matching DATABASE_API_EVENT_CONTRACTS.md."""
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from app.models.enums import EventType


class WebSocketEvent(BaseModel):
    """Event payload emitted over WebSocket channel /ws/v1/events."""
    event_id: str = Field(..., description="Unique event identifier (e.g. evt_001)")
    type: str = Field(..., description="Event type: risk.updated, alert.published, etc.")
    timestamp: datetime = Field(..., description="UTC timestamp of the state transition")
    location_id: Optional[str] = Field(default=None, description="Optional associated location ID")
    resource_id: Optional[str] = Field(default=None, description="Resource ID to fetch via REST API")
    version: int = Field(default=1, description="Version or revision counter")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional non-sensitive metadata")


class WebSocketSubscription(BaseModel):
    """Client subscription request over WebSocket."""
    action: str = Field(default="subscribe", description="subscribe or unsubscribe")
    channel: str = Field(..., description="Target channel or topic (e.g. 'locations:demo-village-01', 'alerts')")
