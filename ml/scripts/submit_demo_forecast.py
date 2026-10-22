"""Explicit, authority-only historical-demo forecast bridge.

This module does NOT issue alerts, send push notifications, or run live warnings.
Prediction is local by default. --submit requires a valid authority token and
an explicitly configured test backend. No credentials are printed or stored.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
for code_root in (REPO_ROOT, REPO_ROOT / "backend"):
    if str(code_root) not in sys.path:
        sys.path.insert(0, str(code_root))

from app.schemas.forecast import ForecastIngestRequest
from ml.src.predict import FloodRiskPredictor

DEFAULT_MODEL = "candidate-leakfree-v1"


def build_demo_forecast(
    features: Dict[str, Any],
    location_id: str,
    event_id: Optional[str] = None,
    model_version: str = DEFAULT_MODEL,
    issued_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate all generated +1/+3/+6 hour horizons against the REAL FastAPI schema."""
    if not location_id.strip():
        raise ValueError("Provide a real location_id registered with the target backend")
    if model_version != DEFAULT_MODEL:
        raise ValueError(
            "This review-only bridge permits only the leak-free candidate; "
            "the older ERA5 baseline has documented retrospective lookahead leakage."
        )
    predictor = FloodRiskPredictor(models_dir=REPO_ROOT / "ml" / "models", model_version=model_version)
    if set(predictor.models) != {1, 3, 6}:
        raise RuntimeError("Missing leak-free +1h/+3h/+6h trained model artifacts")
    payload = predictor.predict(
        features=features,
        location_id=location_id,
        event_id=event_id,
        issued_at=issued_at,
        mode="historical_demo",
    )
    if payload["data_quality"] == "UNAVAILABLE" or any(
        h["risk_level"] == "unknown" for h in payload["horizons"]
    ):
        raise ValueError("Insufficient hydrological inputs or model inference failed: refusing to ingest unknown risk")
    payload["limitations"].append(
        "Historical simulation only; proxy-labelled reanalysis is not independently "
        "verified flood ground truth and cannot justify public warning or routing."
    )
    request = ForecastIngestRequest.model_validate(payload)
    if request.mode.value != "historical_demo" or sorted(h.hours for h in request.horizons) != [1, 3, 6]:
        raise ValueError("Unsafe mode or incomplete horizon set")
    return request.model_dump(mode="json", exclude_none=True)


def _json_request(url: str, token: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def submit_historical_test_forecast(
    payload: Dict[str, Any], api_base: str, authority_token: str
) -> Dict[str, Any]:
    """Explicit test-only API write, followed by persisted forecast readback."""
    if not authority_token.strip():
        raise ValueError("FLOODLENS_AUTHORITY_TOKEN required for an authenticated test submission")
    parsed = urllib.parse.urlparse(api_base)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("Backend URL must be absolute HTTP(S)")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Remote backend connections require HTTPS")
    if payload.get("mode") != "historical_demo":
        raise ValueError("Only historical-demo forecasts may be submitted")
    if payload.get("data_quality") == "UNAVAILABLE":
        raise ValueError("Unknown risk must never be ingested as a valid forecast")
    root = api_base.rstrip("/")
    if not root.endswith("/api/v1"):
        root += "/api/v1"
    created = _json_request(f"{root}/predictions/ingest", authority_token, payload)
    if created.get("forecast_id") != payload.get("forecast_id"):
        raise RuntimeError("Backend returned a different forecast ID")
    location = urllib.parse.quote(payload["location_id"], safe="")
    latest = _json_request(f"{root}/predictions/latest?location_id={location}", authority_token)
    if latest.get("forecast_id") != created.get("forecast_id"):
        raise RuntimeError("Backend latest forecast does not match submitted record")
    if sorted(int(h["hours"]) for h in latest.get("horizons", [])) != [1, 3, 6]:
        raise RuntimeError("Backend did not persist all three forecast horizons")
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run leak-free +1/+3/+6h FastAPI historical-demo forecast bridge"
    )
    parser.add_argument("--features-file", required=True, help="JSON object with timestamp-valid model inputs")
    parser.add_argument("--location-id", required=True, help="Actual backend location ID")
    parser.add_argument("--event-id", default=None, help="Existing historical event ID, or omit")
    parser.add_argument("--issued-at", default=None, help="Optional issuance ISO timestamp")
    parser.add_argument("--submit", action="store_true", help="Opt-in to authenticated historical-test API write")
    args = parser.parse_args()
    features = json.loads(Path(args.features_file).read_text(encoding="utf-8"))
    if not isinstance(features, dict):
        parser.error("--features-file must contain a JSON object")
    payload = build_demo_forecast(features, args.location_id, args.event_id, issued_at=args.issued_at)
    if not args.submit:
        print(json.dumps(payload, indent=2))
        print("DRY RUN — no backend record created or alert sent", file=sys.stderr)
        return
    token = os.getenv("FLOODLENS_AUTHORITY_TOKEN", "")
    api = os.getenv("FLOODLENS_BACKEND_URL", "http://127.0.0.1:8000")
    if not token:
        parser.error("Set FLOODLENS_AUTHORITY_TOKEN for explicitly authorized test submission")
    try:
        latest = submit_historical_test_forecast(payload, api, token)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        parser.error(f"Test backend submission/readback failed: {type(exc).__name__}")
    print(json.dumps({
        "status": "historical_demo_persisted",
        "forecast_id": latest["forecast_id"],
        "model_version": latest["model_version"],
        "location_id": latest["location_id"],
        "horizons": latest["horizons"],
    }, indent=2))


if __name__ == "__main__":
    main()
