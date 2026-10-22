"""Isolated regression tests for the historical-only ML -> FastAPI forecast handoff."""
from __future__ import annotations

import pytest

from app.schemas.forecast import ForecastIngestRequest
from ml.scripts.submit_demo_forecast import build_demo_forecast, submit_historical_test_forecast


@pytest.fixture
def demo_features():
    return {
        "rainfall_mm": 12.5,
        "rainfall_rolling_3h_mm": 28.0,
        "rainfall_rolling_6h_mm": 45.0,
        "rainfall_rolling_24h_mm": 95.0,
        "upstream_discharge_m3s_lag24h": 5400.0,
        "temperature_c": 28.5,
        "relative_humidity_pct": 83.0,
        "season": "monsoon",
        "catchment_saturation_class": "wet",
    }


def test_leakfree_candidate_generates_valid_historical_backend_payload(demo_features):
    request_json = build_demo_forecast(
        demo_features,
        location_id="loc_barahachhetra_w2",
        event_id=None,
        issued_at="2024-08-10T00:00:00Z",
    )
    request = ForecastIngestRequest.model_validate(request_json)
    assert request.mode.value == "historical_demo"
    assert request.model_version == "candidate-leakfree-v1"
    assert request.location_id == "loc_barahachhetra_w2"
    assert request.event_id is None
    assert request.issued_at.isoformat().startswith("2024-08-10T00:00")
    assert sorted(h.hours for h in request.horizons) == [1, 3, 6]
    assert all(h.risk_level in ("low", "moderate", "high", "critical") for h in request.horizons)
    assert all(h.calibrated_probability is None for h in request.horizons), (
        "Uncalibrated model scores must not be presented as calibrated probabilities"
    )
    assert any("proxy" in statement.lower() for statement in request.limitations)
    assert any("not" in statement.lower() for statement in request.limitations)


def test_refuse_unknown_inputs_and_older_leaky_baseline():
    with pytest.raises(ValueError, match="Insufficient hydrological"):
        build_demo_forecast({}, "loc_barahachhetra_w2")
    with pytest.raises(ValueError, match="only the leak-free candidate"):
        build_demo_forecast({"rainfall_mm": 10}, "loc_barahachhetra_w2", model_version="era5-v1")


def test_transport_requires_authority_and_rejects_insecure_remote():
    payload = {"mode": "historical_demo", "data_quality": "PARTIAL", "location_id": "loc"}
    with pytest.raises(ValueError, match="FLOODLENS_AUTHORITY_TOKEN"):
        submit_historical_test_forecast(payload, "https://example.org", "")
    with pytest.raises(ValueError, match="HTTPS"):
        submit_historical_test_forecast(payload, "http://example.org", "not-a-real-token")
    with pytest.raises(ValueError, match="Only historical-demo"):
        submit_historical_test_forecast({**payload, "mode": "live_observation"}, "http://localhost:8000", "x")
    with pytest.raises(ValueError, match="Unknown risk"):
        submit_historical_test_forecast({**payload, "data_quality": "UNAVAILABLE"}, "http://localhost:8000", "x")


def test_authenticated_roundtrip_protocol_without_network(monkeypatch, demo_features):
    payload = build_demo_forecast(demo_features, location_id="loc_barahachhetra_w2")
    requests = []
    def fake_request(url, token, body=None):
        requests.append((url, token, body))
        if body is not None:
            return {"forecast_id": body["forecast_id"]}
        return {
            "forecast_id": payload["forecast_id"],
            "model_version": payload["model_version"],
            "location_id": payload["location_id"],
            "horizons": payload["horizons"],
        }

    monkeypatch.setattr("ml.scripts.submit_demo_forecast._json_request", fake_request)
    result = submit_historical_test_forecast(payload, "http://localhost:8000", "test-token")
    assert result["forecast_id"] == payload["forecast_id"]
    assert len(requests) == 2
    assert requests[0][0].endswith("/api/v1/predictions/ingest")
    assert "/api/v1/predictions/latest?location_id=" in requests[1][0]
    assert all(entry[1] == "test-token" for entry in requests)
