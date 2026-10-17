"""Tests verifying Pydantic API schemas against documented JSON contracts."""
import json
from datetime import datetime, timezone
from app.schemas.common import ErrorResponse
from app.schemas.event import WebSocketEvent
from app.schemas.forecast import ForecastResponse


def test_documented_forecast_json_contract():
    """Verify example forecast JSON from DATABASE_API_EVENT_CONTRACTS.md validates properly."""
    raw_forecast_json = {
        "forecast_id": "demo-forecast-001",
        "location_id": "demo-village-01",
        "issued_at": "2026-10-17T06:00:00Z",
        "mode": "historical_demo",
        "model_version": "baseline-v1",
        "data_quality": "partial",
        "horizons": [
            {"hours": 1, "risk_level": "low"},
            {"hours": 3, "risk_level": "moderate"},
            {"hours": 6, "risk_level": "high"}
        ],
        "limitations": ["Upstream gauge unavailable"]
    }

    # Validate against Pydantic schema
    forecast = ForecastResponse.model_validate(raw_forecast_json)
    assert forecast.forecast_id == "demo-forecast-001"
    assert forecast.location_id == "demo-village-01"
    assert forecast.model_version == "baseline-v1"
    assert forecast.data_quality == "partial"
    assert len(forecast.horizons) == 3
    assert forecast.horizons[0].hours == 1
    assert forecast.horizons[0].risk_level == "low"
    assert forecast.horizons[1].hours == 3
    assert forecast.horizons[1].risk_level == "moderate"
    assert forecast.horizons[2].hours == 6
    assert forecast.horizons[2].risk_level == "high"
    assert forecast.limitations == ["Upstream gauge unavailable"]


def test_documented_websocket_event_json_contract():
    """Verify example WebSocket event JSON from DATABASE_API_EVENT_CONTRACTS.md validates properly."""
    raw_event_json = {
        "event_id": "evt_001",
        "type": "risk.updated",
        "timestamp": "2026-10-17T06:10:00Z",
        "location_id": "demo-village-01",
        "resource_id": "demo-forecast-001",
        "version": 2
    }

    event = WebSocketEvent.model_validate(raw_event_json)
    assert event.event_id == "evt_001"
    assert event.type == "risk.updated"
    assert event.location_id == "demo-village-01"
    assert event.resource_id == "demo-forecast-001"
    assert event.version == 2


def test_documented_error_format_contract():
    """Verify error envelope matches {"error": {"code": ..., "message": ..., "request_id": ...}}."""
    raw_error_json = {
        "error": {
            "code": "DATA_UNAVAILABLE",
            "message": "No verified gauge reading",
            "request_id": "req_001"
        }
    }

    error_resp = ErrorResponse.model_validate(raw_error_json)
    assert error_resp.error.code == "DATA_UNAVAILABLE"
    assert error_resp.error.message == "No verified gauge reading"
    assert error_resp.error.request_id == "req_001"
