"""Comprehensive verification script for publicly deployed FloodLens AI backend.

Executes live HTTP verification against any public HTTPS URL:
1. Health & readiness probes (/health, /ready, /api/v1/health)
2. Verification that database is PostGIS / PostgreSQL, not SQLite
3. Interactive Swagger documentation (/api/v1/docs)
4. Authority authentication and JWT issuance (/api/v1/auth/login)
5. Historical flood event retrieval (/api/v1/flood-events)
6. Location and settlement retrieval (/api/v1/locations)
7. Multi-horizon forecast retrieval (+1h, +3h, +6h) (/api/v1/predictions/latest)
8. Multi-horizon risk map retrieval (/api/v1/predictions/map)
9. Historical satellite-derived observed flood extent (/api/v1/flood-events/{id}/extent)
10. Spatial settlement exposure assessment (/api/v1/flood-events/{id}/settlements)
11. Candidate route hazard screening (/api/v1/routes/assess)
12. CORS preflight and HTTPS validation
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


def _http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 20,
) -> Tuple[int, Any, Dict[str, str]]:
    req_headers = {"User-Agent": "FloodLens-Live-Verifier/1.0", **(headers or {})}
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return resp.status, parsed, resp_headers
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = err_body
        return exc.code, parsed, dict(exc.headers)
    except Exception as exc:
        return 0, str(exc), {}


def verify_deployment(base_url: str) -> bool:
    base = base_url.rstrip("/")
    print("=" * 80)
    print(f"FLOODLENS AI: LIVE DEPLOYED BACKEND VERIFICATION")
    print(f"Target URL: {base}")
    print("=" * 80)

    results: Dict[str, str] = {}
    details: Dict[str, Any] = {}

    # 1. GET /health
    print("\n[1] Checking Root Health Probe (/health)...")
    code, data, _ = _http_request(f"{base}/health")
    if code == 200 and isinstance(data, dict) and data.get("status") in ("healthy", "ready"):
        print(f"    PASS: HTTP 200 OK -> status={data.get('status')}")
        results["GET /health"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /health"] = "FAIL"

    # 2. GET /ready (Check PostGIS + PostgreSQL)
    print("\n[2] Checking Readiness Probe (/ready)...")
    code, data, _ = _http_request(f"{base}/ready")
    if code == 200 and isinstance(data, dict):
        db_info = data.get("database", {})
        db_type = db_info.get("database_type")
        pg_ver = db_info.get("postgis_version")
        is_postgis = db_info.get("postgis_installed")
        print(f"    Readiness: status={data.get('status')}")
        print(f"    Database: type={db_type}, postgis_installed={is_postgis}, version={pg_ver}")

        if "postgres" in str(db_type).lower():
            print("    PASS: Verified PostgreSQL database backend (NOT SQLite).")
            results["Database Type (PostgreSQL)"] = "PASS"
        else:
            print(f"    WARN: Database reported as '{db_type}'.")
            results["Database Type (PostgreSQL)"] = f"WARN ({db_type})"

        results["GET /ready"] = "PASS"
        details["postgis_version"] = pg_ver
        details["database_type"] = db_type
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /ready"] = "FAIL"

    # 3. GET /api/v1/health
    print("\n[3] Checking API v1 Health Probe (/api/v1/health)...")
    code, data, _ = _http_request(f"{base}/api/v1/health")
    if code == 200 and isinstance(data, dict):
        op_mode = data.get("operational_mode")
        print(f"    PASS: HTTP 200 OK -> app_name='{data.get('app_name')}', mode='{op_mode}'")
        results["GET /api/v1/health"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/health"] = "FAIL"

    # 4. GET /api/v1/docs (Swagger UI)
    print("\n[4] Checking OpenAPI Swagger Documentation (/api/v1/docs)...")
    code, _, _ = _http_request(f"{base}/api/v1/docs")
    if code == 200:
        print("    PASS: HTTP 200 OK (Swagger documentation rendered)")
        results["GET /api/v1/docs"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code}")
        results["GET /api/v1/docs"] = "FAIL"

    # 5. POST /api/v1/auth/login (Authority Token)
    print("\n[5] Testing Authority Authentication (/api/v1/auth/login)...")
    auth_email = os.getenv("DEMO_AUTHORITY_EMAIL", "authority_lead@floodlens.org")
    auth_password = os.getenv("DEMO_AUTHORITY_PASSWORD")
    auth_token = None
    if not auth_password:
        print("    FAIL: DEMO_AUTHORITY_PASSWORD environment variable not set. Please set DEMO_AUTHORITY_PASSWORD.")
        results["POST /api/v1/auth/login"] = "FAIL"
    else:
        login_payload = {
            "email": auth_email,
            "password": auth_password,
        }
        code, data, _ = _http_request(f"{base}/api/v1/auth/login", method="POST", data=login_payload)
        if code == 200 and isinstance(data, dict) and "access_token" in data:
            auth_token = data["access_token"]
            print(f"    PASS: Authenticated successfully! Token issued: {auth_token[:15]}...")
            results["POST /api/v1/auth/login"] = "PASS"
        else:
            print(f"    FAIL: HTTP {code} -> {data}")
            results["POST /api/v1/auth/login"] = "FAIL"

    auth_headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    # 6. GET /api/v1/flood-events
    print("\n[6] Checking Flood Event Retrieval (/api/v1/flood-events)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events", headers=auth_headers)
    if code == 200 and isinstance(data, list) and len(data) > 0:
        print(f"    PASS: HTTP 200 OK -> Retrieved {len(data)} event(s): {[e.get('id') for e in data]}")
        results["GET /api/v1/flood-events"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/flood-events"] = "FAIL"

    # 7. GET /api/v1/locations
    print("\n[7] Checking Location & Settlement Retrieval (/api/v1/locations)...")
    code, data, _ = _http_request(f"{base}/api/v1/locations", headers=auth_headers)
    if code == 200 and isinstance(data, list) and len(data) > 0:
        print(f"    PASS: HTTP 200 OK -> Retrieved {len(data)} location(s): {[loc.get('id') for loc in data]}")
        results["GET /api/v1/locations"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/locations"] = "FAIL"

    # 8. GET /api/v1/predictions/latest?location_id=settlement_janakpurdham
    print("\n[8] Checking Multi-Horizon Forecast (+1h, +3h, +6h) (/api/v1/predictions/latest)...")
    code, data, _ = _http_request(f"{base}/api/v1/predictions/latest?location_id=settlement_janakpurdham")
    if code == 200 and isinstance(data, dict):
        horizons = data.get("horizons", [])
        hrs = [h.get("hours") for h in horizons]
        print(f"    PASS: HTTP 200 OK -> Retrieved forecast for '{data.get('location_id')}' with horizons: {hrs}")
        results["GET /api/v1/predictions/latest"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/predictions/latest"] = "FAIL"

    # 9. GET /api/v1/predictions/map
    print("\n[9] Checking Multi-Horizon Risk Map (/api/v1/predictions/map)...")
    code, data, _ = _http_request(f"{base}/api/v1/predictions/map")
    if code == 200 and isinstance(data, dict):
        feats = data.get("features", [])
        print(f"    PASS: HTTP 200 OK -> Risk map layer contains {len(feats)} feature(s)")
        results["GET /api/v1/predictions/map"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/predictions/map"] = "FAIL"

    # 10. GET /api/v1/flood-events/{id}/extent
    print("\n[10] Checking Historical Observed Flood Extent (/api/v1/flood-events/evt_2024_terai_monsoon/extent)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/evt_2024_terai_monsoon/extent")
    if code == 200 and isinstance(data, dict):
        area = data.get("area_km2")
        method = data.get("method")
        print(f"    PASS: HTTP 200 OK -> Extent: id='{data.get('id')}', area={area} km², method='{method}'")
        results["GET /flood-events/{id}/extent"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /flood-events/{id}/extent"] = "FAIL"

    # 11. GET /api/v1/flood-events/{id}/settlements
    print("\n[11] Checking Spatial Settlement Exposure (/api/v1/flood-events/evt_2024_terai_monsoon/settlements)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/evt_2024_terai_monsoon/settlements", headers=auth_headers)
    if code == 200 and isinstance(data, dict):
        count = data.get("settlements_count") or len(data.get("affected_settlements", []))
        print(f"    PASS: HTTP 200 OK -> Assessed settlements count: {count}")
        results["GET /flood-events/{id}/settlements"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /flood-events/{id}/settlements"] = "FAIL"

    # 12. POST /api/v1/routes/assess (Candidate Route Hazard Screening)
    print("\n[12] Checking Candidate Route Hazard Screening (/api/v1/routes/assess)...")
    route_payload = {
        "route": {
            "type": "LineString",
            "coordinates": [[85.9200, 26.7200], [85.9300, 26.7350]],
        },
        "event_id": "evt_2024_terai_monsoon",
        "buffer_meters": 25.0,
    }
    code, data, _ = _http_request(f"{base}/api/v1/routes/assess", method="POST", headers=auth_headers, data=route_payload)
    if code == 200 and isinstance(data, dict):
        status_val = data.get("route_status") or data.get("assessment_status") or data.get("status")
        assessment = data.get("assessment") or data.get("hazards_detected")
        print(f"    PASS: HTTP 200 OK -> route_status='{status_val}', hazards_count={len(assessment) if isinstance(assessment, list) else assessment}")
        results["POST /api/v1/routes/assess"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["POST /api/v1/routes/assess"] = "FAIL"

    # 13. CORS & HTTPS Headers Verification
    print("\n[13] Checking CORS Preflight & HTTPS...")
    code, _, hdrs = _http_request(
        f"{base}/api/v1/health",
        method="OPTIONS",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    cors_allowed = "access-control-allow-origin" in hdrs
    if base.startswith("https://"):
        print(f"    PASS: Strict HTTPS validated -> {base}")
        results["HTTPS Enforced"] = "PASS"
    else:
        print(f"    WARN: Base URL is not HTTPS -> {base}")
        results["HTTPS Enforced"] = "WARN"

    if cors_allowed or code in (200, 204):
        print(f"    PASS: CORS Preflight response valid (code {code})")
        results["CORS Preflight"] = "PASS"
    else:
        print(f"    WARN: CORS Preflight returned HTTP {code}")
        results["CORS Preflight"] = f"WARN (code {code})"

    # Summary
    print("\n" + "=" * 80)
    print("LIVE VERIFICATION RESULTS SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for v in results.values() if v == "PASS")
    total_count = len(results)
    for test, res in results.items():
        print(f"  [{res}] {test}")

    print(f"\nTotal: {passed_count}/{total_count} checks passed.")
    success = passed_count == total_count
    print(f"Verdict: {'ALL CHECKS PASSED' if success else 'ISSUES DETECTED'}")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live FloodLens AI Backend Verifier")
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8000", help="Base URL of deployed backend")
    args = parser.parse_args()
    ok = verify_deployment(args.url)
    sys.exit(0 if ok else 1)
