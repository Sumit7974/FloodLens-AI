"""Pydantic API schemas for FloodLens AI."""
from app.schemas.alert import AlertApprovalRequest, AlertCreateRequest, AlertResponse
from app.schemas.assistance import AssistanceCreateRequest, AssistanceResponse, AssistanceUpdateRequest
from app.schemas.auth import TokenPayload, TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from app.schemas.common import ErrorDetail, ErrorResponse, GeoJSONFeature, GeoJSONGeometry
from app.schemas.event import WebSocketEvent, WebSocketSubscription
from app.schemas.flood_event import FloodEventResponse, FloodExtentResponse
from app.schemas.forecast import ForecastResponse, HorizonRisk
from app.schemas.health import DatabaseHealth, HealthResponse

__all__ = [
    "AlertApprovalRequest",
    "AlertCreateRequest",
    "AlertResponse",
    "AssistanceCreateRequest",
    "AssistanceResponse",
    "AssistanceUpdateRequest",
    "DatabaseHealth",
    "ErrorDetail",
    "ErrorResponse",
    "FloodEventResponse",
    "FloodExtentResponse",
    "ForecastResponse",
    "GeoJSONFeature",
    "GeoJSONGeometry",
    "HealthResponse",
    "HorizonRisk",
    "TokenPayload",
    "TokenResponse",
    "UserLoginRequest",
    "UserRegisterRequest",
    "UserResponse",
    "WebSocketEvent",
    "WebSocketSubscription",
]
