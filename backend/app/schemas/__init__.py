"""Pydantic API schemas for FloodLens AI."""
from app.schemas.alert import AlertApprovalRequest, AlertCreateRequest, AlertDispatchRequest, AlertResponse
from app.schemas.assistance import AssistanceCreateRequest, AssistanceResponse, AssistanceUpdateRequest
from app.schemas.auth import TokenPayload, TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from app.schemas.common import ErrorDetail, ErrorResponse, GeoJSONFeature, GeoJSONGeometry
from app.schemas.event import WebSocketEvent, WebSocketSubscription
from app.schemas.flood_event import (
    AffectedSettlementItem,
    AffectedSettlementsResponse,
    ExposedAssetsResponse,
    FloodEventCreate,
    FloodEventResponse,
    FloodExtentCreate,
    FloodExtentResponse,
    FloodReportResponse,
)
from app.schemas.forecast import (
    ForecastIngestRequest,
    ForecastResponse,
    HorizonRisk,
    HorizonRiskInput,
    PredictionMapFeature,
    PredictionMapResponse,
)
from app.schemas.health import DatabaseHealth, HealthResponse, ReadinessCheck, ReadinessResponse
from app.schemas.location import LocationCreate, LocationResponse
from app.schemas.satellite import (
    SatelliteJobCreate,
    SatelliteJobResponse,
    SatelliteSceneCreate,
    SatelliteSceneResponse,
)

__all__ = [
    "AffectedSettlementItem",
    "AffectedSettlementsResponse",
    "AlertApprovalRequest",
    "AlertCreateRequest",
    "AlertDispatchRequest",
    "AlertResponse",
    "AssistanceCreateRequest",
    "AssistanceResponse",
    "AssistanceUpdateRequest",
    "DatabaseHealth",
    "ErrorDetail",
    "ErrorResponse",
    "ExposedAssetsResponse",
    "FloodEventCreate",
    "FloodEventResponse",
    "FloodExtentCreate",
    "FloodExtentResponse",
    "FloodReportResponse",
    "ForecastIngestRequest",
    "ForecastResponse",
    "GeoJSONFeature",
    "GeoJSONGeometry",
    "HealthResponse",
    "HorizonRisk",
    "HorizonRiskInput",
    "LocationCreate",
    "LocationResponse",
    "PredictionMapFeature",
    "PredictionMapResponse",
    "ReadinessCheck",
    "ReadinessResponse",
    "SatelliteJobCreate",
    "SatelliteJobResponse",
    "SatelliteSceneCreate",
    "SatelliteSceneResponse",
    "TokenPayload",
    "TokenResponse",
    "UserLoginRequest",
    "UserRegisterRequest",
    "UserResponse",
    "WebSocketEvent",
    "WebSocketSubscription",
]
