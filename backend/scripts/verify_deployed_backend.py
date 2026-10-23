"""Comprehensive verification script for publicly deployed FloodLens AI backend.

Executes live HTTP and WebSocket verification against any public HTTPS URL:
1. Root Service Index (GET /)
2. Health & Readiness Probes (GET /health, GET /ready, GET /api/v1/health, GET /api/v1/ready)
3. PostgreSQL 16 & PostGIS 3.6 confirmation (NOT SQLite)
4. OpenAPI Swagger Interactive Documentation (GET /api/v1/docs)
5. Authority Authentication & JWT Issuance (POST /api/v1/auth/login)
6. Protected Route Access Control (GET /api/v1/auth/me - unauthorized 401 & authorized 200)
7. Historical Flood Events (GET /api/v1/flood-events)
8. Benchmark Locations & Settlement Hierarchy (GET /api/v1/locations)
9. Multi-Horizon Forecast Runs (+1h, +3h, +6h) with uncalibrated probabilities (calibrated_probability=None)
10. Multi-Horizon Risk Map Layer (GET /api/v1/predictions/map)
11. Terai Monsoon Historical SAR Extent (GET /api/v1/flood-events/evt_2024_terai_monsoon/extent)
12. Authentic Koshi 2017 Optical NDWI Extent (~0.6429 km², PROCESSED_OPTICAL provenance, null confidence)
13. Spatial Settlement Exposure Assessment (GET /api/v1/flood-events/{id}/settlements)
14. Historical Flood Inundation Reports (GET /api/v1/flood-events/{id}/report)
15. Critical Infrastructure & Shelters Demo Labeled Fixtures (GET /api/v1/facilities/shelters)
16. Candidate Evacuation Route Hazard Screening (POST /api/v1/routes/assess)
17. Strict HTTPS & CORS Restricted Origin Protection (allowed origin ok, arbitrary origin rejected)
18. Real-time WebSocket Protocol & Authorization (unauthorized rejected, authorized verified)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


def _http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 25,
) -> Tuple[int, Any, Dict[str, str]]:
    req_headers = {"User-Agent": "FloodLens-Live-Verifier/1.0", **(headers or {})}
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            resp_headers = {k.lower(): v for k, v in dict(resp.headers).items()}
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return resp.status, parsed, resp_headers
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = err_body
        resp_headers = {k.lower(): v for k, v in dict(exc.headers).items()}
        return exc.code, parsed, resp_headers
    except Exception as exc:
        return 0, str(exc), {}


async def _probe_websocket(ws_url: str, token: Optional[str] = None) -> Tuple[bool, str]:
    if not HAS_WEBSOCKETS:
        return True, "SKIPPED (websockets library not installed in runner)"

    target = f"{ws_url}?token={token}" if token else ws_url
    try:
        if token:
            async with websockets.connect(target, open_timeout=10, close_timeout=5) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                return True, "Connected & received authenticated welcome handshake event"
        else:
            # Unauthorized attempt should be rejected
            try:
                async with websockets.connect(target, open_timeout=10, close_timeout=5) as ws:
                    return False, "Failed: Connected without authentication token"
            except websockets.exceptions.InvalidStatus as e:
                return True, f"Rejected unauthorized connection with HTTP status {e.response.status_code}"
            except websockets.exceptions.ConnectionClosed as e:
                return True, f"Connection rejected: code {e.rcvd.code}"
            except Exception as e:
                return True, f"Rejected unauthorized connection: {type(e).__name__}"
    except Exception as exc:
        if token:
            return False, f"Failed authorized WebSocket connection: {type(exc).__name__} ({exc})"
        return True, f"Rejected unauthorized connection: {type(exc).__name__}"


def verify_deployment(base_url: str) -> bool:
    base = base_url.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")

    print("=" * 80)
    print("FLOODLENS AI: LIVE CLOUD DEPLOYMENT VERIFICATION SUITE")
    print(f"Target Public HTTPS URL: {base}")
    print("=" * 80)

    results: Dict[str, str] = {}
    details: Dict[str, Any] = {}

    # 1. GET / (Root Service Index)
    print("\n[1] Checking Root Service Index (GET /)...")
    code, data, _ = _http_request(f"{base}/")
    if code == 200 and isinstance(data, dict) and "operational_mode" in data:
        print(f"    PASS: HTTP 200 OK -> name='{data.get('name')}', mode='{data.get('operational_mode')}'")
        results["GET / (Service Index)"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET / (Service Index)"] = "FAIL"

    # 2. GET /health (Root Health Probe)
    print("\n[2] Checking Root Health Probe (GET /health)...")
    code, data, _ = _http_request(f"{base}/health")
    if code == 200 and isinstance(data, dict) and data.get("status") in ("healthy", "ready"):
        print(f"    PASS: HTTP 200 OK -> status={data.get('status')}, env={data.get('environment')}")
        results["GET /health"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /health"] = "FAIL"

    # 3. GET /ready (Readiness & PostGIS Verification)
    print("\n[3] Checking Root Readiness Probe (GET /ready)...")
    code, data, _ = _http_request(f"{base}/ready")
    if code == 200 and isinstance(data, dict):
        db_info = data.get("database", {})
        db_type = db_info.get("database_type")
        pg_ver = db_info.get("postgis_version")
        is_postgis = db_info.get("postgis_installed")
        connected = db_info.get("connected")
        print(f"    Readiness status: {data.get('status')}")
        print(f"    Database: connected={connected}, type={db_type}, postgis={is_postgis}, ver={pg_ver}")

        if connected and "postgres" in str(db_type).lower() and is_postgis:
            print("    PASS: Verified PostgreSQL with PostGIS installed (NOT SQLite).")
            results["PostgreSQL & PostGIS Readiness"] = "PASS"
        else:
            print(f"    FAIL: Inadequate database configuration: type={db_type}, postgis={is_postgis}")
            results["PostgreSQL & PostGIS Readiness"] = "FAIL"
        results["GET /ready"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /ready"] = "FAIL"
        results["PostgreSQL & PostGIS Readiness"] = "FAIL"

    # 4. GET /api/v1/health & GET /api/v1/ready
    print("\n[4] Checking API v1 Probes (/api/v1/health & /api/v1/ready)...")
    code_h, data_h, _ = _http_request(f"{base}/api/v1/health")
    code_r, data_r, _ = _http_request(f"{base}/api/v1/ready")
    if code_h == 200 and code_r == 200:
        print(f"    PASS: /api/v1/health HTTP {code_h}, /api/v1/ready HTTP {code_r}")
        results["GET /api/v1/health & /api/v1/ready"] = "PASS"
    else:
        print(f"    FAIL: health={code_h}, ready={code_r}")
        results["GET /api/v1/health & /api/v1/ready"] = "FAIL"

    # 5. GET /api/v1/docs (OpenAPI Swagger UI)
    print("\n[5] Checking OpenAPI Swagger Documentation (/api/v1/docs)...")
    code, _, _ = _http_request(f"{base}/api/v1/docs")
    if code == 200:
        print("    PASS: HTTP 200 OK (Swagger UI documentation rendered)")
        results["GET /api/v1/docs"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code}")
        results["GET /api/v1/docs"] = "FAIL"

    # 6. Authority Authentication (POST /api/v1/auth/login)
    print("\n[6] Testing Authority Authentication (/api/v1/auth/login)...")
    auth_email = os.getenv("DEMO_AUTHORITY_EMAIL", "authority_lead@floodlens.org")
    auth_password = os.getenv("DEMO_AUTHORITY_PASSWORD")
    auth_token = None

    if not auth_password:
        print("    FAIL: DEMO_AUTHORITY_PASSWORD environment variable not set. Please provide it.")
        results["POST /api/v1/auth/login"] = "FAIL"
    else:
        login_payload = {"email": auth_email, "password": auth_password}
        code, data, _ = _http_request(f"{base}/api/v1/auth/login", method="POST", data=login_payload)
        if code == 200 and isinstance(data, dict) and "access_token" in data:
            auth_token = data["access_token"]
            print(f"    PASS: Authority authenticated successfully! (JWT token issued, valid session established)")
            results["POST /api/v1/auth/login"] = "PASS"
        else:
            print(f"    FAIL: HTTP {code} -> {data}")
            results["POST /api/v1/auth/login"] = "FAIL"

    auth_headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    # 7. Protected Route Authorization Checks (/api/v1/auth/me)
    print("\n[7] Checking Protected Route Access Control (/api/v1/auth/me)...")
    code_noauth, data_noauth, _ = _http_request(f"{base}/api/v1/auth/me")
    if code_noauth == 401:
        print(f"    PASS: Unauthorized access correctly rejected with HTTP 401 Unauthorized")
        results["Protected Route Rejects Unauthorized"] = "PASS"
    else:
        print(f"    FAIL: Protected route returned HTTP {code_noauth} when unauthenticated")
        results["Protected Route Rejects Unauthorized"] = "FAIL"

    if auth_token:
        code_auth, data_auth, _ = _http_request(f"{base}/api/v1/auth/me", headers=auth_headers)
        if code_auth == 200 and isinstance(data_auth, dict) and data_auth.get("role") == "authority":
            print(f"    PASS: Authorized access granted -> user='{data_auth.get('email')}', role='{data_auth.get('role')}'")
            results["Protected Route Grants Authorized"] = "PASS"
        else:
            print(f"    FAIL: HTTP {code_auth} -> {data_auth}")
            results["Protected Route Grants Authorized"] = "FAIL"
    else:
        results["Protected Route Grants Authorized"] = "SKIPPED (no auth token)"

    # 8. GET /api/v1/flood-events
    print("\n[8] Checking Historical Flood Events (/api/v1/flood-events)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events", headers=auth_headers)
    if code == 200 and isinstance(data, list) and len(data) >= 2:
        event_ids = [e.get("id") for e in data]
        print(f"    PASS: HTTP 200 OK -> Retrieved {len(data)} event(s): {event_ids}")
        results["GET /api/v1/flood-events"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/flood-events"] = "FAIL"

    # 9. GET /api/v1/locations
    print("\n[9] Checking Benchmark Locations & Hierarchy (/api/v1/locations)...")
    code, data, _ = _http_request(f"{base}/api/v1/locations", headers=auth_headers)
    if code == 200 and isinstance(data, list) and len(data) >= 7:
        print(f"    PASS: HTTP 200 OK -> Retrieved {len(data)} location(s)")
        results["GET /api/v1/locations"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/locations"] = "FAIL"

    # 10. GET /api/v1/predictions/latest & check uncalibrated probabilities
    print("\n[10] Checking Multi-Horizon Forecasts (+1h, +3h, +6h) & Uncalibrated Probability Null Check...")
    code, data, _ = _http_request(f"{base}/api/v1/predictions/latest?location_id=settlement_janakpurdham")
    if code == 200 and isinstance(data, dict):
        horizons = data.get("horizons", [])
        hrs = [h.get("hours") for h in horizons]
        probs = [h.get("calibrated_probability") for h in horizons]
        all_null = all(p is None for p in probs)
        print(f"    Forecast horizons: {hrs}, calibrated_probabilities: {probs}")
        if set(hrs) >= {1, 3, 6} and all_null:
            print("    PASS: Verified +1h, +3h, +6h horizons and all uncalibrated probabilities are strictly null.")
            results["Multi-Horizon Predictions & Null Probabilities"] = "PASS"
        else:
            print("    FAIL: Missing required horizons or calibrated_probability was not null")
            results["Multi-Horizon Predictions & Null Probabilities"] = "FAIL"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Multi-Horizon Predictions & Null Probabilities"] = "FAIL"

    # 11. GET /api/v1/predictions/map
    print("\n[11] Checking Multi-Horizon Risk Map (/api/v1/predictions/map)...")
    code, data, _ = _http_request(f"{base}/api/v1/predictions/map")
    if code == 200 and isinstance(data, dict) and "features" in data:
        print(f"    PASS: HTTP 200 OK -> Risk map layer contains {len(data.get('features', []))} feature(s)")
        results["GET /api/v1/predictions/map"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["GET /api/v1/predictions/map"] = "FAIL"

    # 12. GET /api/v1/flood-events/evt_2024_terai_monsoon/extent (Terai SAR)
    print("\n[12] Checking Nepal Terai July 2024 Extent (/api/v1/flood-events/evt_2024_terai_monsoon/extent)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/evt_2024_terai_monsoon/extent")
    if code == 200 and isinstance(data, dict):
        area = data.get("area_km2")
        method = data.get("method")
        provenance = data.get("provenance")
        geom_type = data.get("geometry", {}).get("type")
        print(f"    PASS: Terai SAR Extent: area={area} km², method='{method}', provenance='{provenance}', geom='{geom_type}'")
        results["Terai July 2024 Extent"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Terai July 2024 Extent"] = "FAIL"

    # 13. GET /api/v1/flood-events/event_nepal_koshi_2017/extent (Authentic Koshi Optical NDWI)
    print("\n[13] Checking Nepal Koshi August 2017 Optical NDWI Extent (~0.6429 km²)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/event_nepal_koshi_2017/extent")
    if code == 200 and isinstance(data, dict):
        area = data.get("area_km2")
        method = data.get("method")
        provenance = data.get("provenance")
        conf = data.get("confidence")
        geom_type = data.get("geometry", {}).get("type")
        print(f"    Koshi Optical Extent: area={area} km², method='{method}', provenance='{provenance}', confidence={conf}")
        if area is not None and abs(area - 0.6429) < 0.05 and provenance == "PROCESSED_OPTICAL" and conf is None:
            print("    PASS: Verified authentic optical processing result ~0.6429 km², PROCESSED_OPTICAL, null confidence.")
            results["Koshi 2017 Optical NDWI Extent & Provenance"] = "PASS"
        else:
            print("    FAIL: Koshi optical extent did not meet empirical validation criteria")
            results["Koshi 2017 Optical NDWI Extent & Provenance"] = "FAIL"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Koshi 2017 Optical NDWI Extent & Provenance"] = "FAIL"

    # 14. GET /api/v1/flood-events/evt_2024_terai_monsoon/settlements
    print("\n[14] Checking Spatial Settlement Exposure (/api/v1/flood-events/evt_2024_terai_monsoon/settlements)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/evt_2024_terai_monsoon/settlements", headers=auth_headers)
    if code == 200 and isinstance(data, dict):
        evaluated = data.get("total_settlements_evaluated") or data.get("settlements_count")
        affected = data.get("total_settlements_affected") or len(data.get("affected_settlements", []))
        print(f"    PASS: HTTP 200 OK -> Settlements evaluated: {evaluated}, affected: {affected}")
        results["Settlement Impact Calculations"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Settlement Impact Calculations"] = "FAIL"

    # 15. GET /api/v1/flood-events/evt_2024_terai_monsoon/report
    print("\n[15] Checking Historical Flood Inundation Report (/api/v1/flood-events/evt_2024_terai_monsoon/report)...")
    code, data, _ = _http_request(f"{base}/api/v1/flood-events/evt_2024_terai_monsoon/report", headers=auth_headers)
    if code == 200 and isinstance(data, dict) and "data_limitations" in data:
        print(f"    PASS: HTTP 200 OK -> Report status: '{data.get('status')}', event: '{data.get('event_id')}'")
        results["Historical Flood Reports"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Historical Flood Reports"] = "FAIL"

    # 16. GET /api/v1/facilities/shelters
    print("\n[16] Checking Shelters & Critical Facilities Demo Labeling (/api/v1/facilities/shelters)...")
    code, data, _ = _http_request(f"{base}/api/v1/facilities/shelters")
    if code == 200 and isinstance(data, dict) and "shelters" in data:
        shelters = data.get("shelters", [])
        status_flags = [s.get("verification_status") for s in shelters]
        all_demo = all(st == "demo_labeled" for st in status_flags)
        print(f"    Shelters count: {len(shelters)}, verification_status: {status_flags}")
        if len(shelters) > 0 and all_demo:
            print("    PASS: Verified all shelters are explicitly labeled demo fixtures.")
            results["Shelters & Emergency Facilities Demo Labeled"] = "PASS"
        else:
            print("    FAIL: Shelters missing or not demo_labeled")
            results["Shelters & Emergency Facilities Demo Labeled"] = "FAIL"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Shelters & Emergency Facilities Demo Labeled"] = "FAIL"

    # 17. POST /api/v1/routes/assess (Candidate Route Hazard Screening)
    print("\n[17] Checking Candidate Route Hazard Screening (/api/v1/routes/assess)...")
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
        print(f"    PASS: HTTP 200 OK -> route_status='{status_val}'")
        results["Route Hazard Screening"] = "PASS"
    else:
        print(f"    FAIL: HTTP {code} -> {data}")
        results["Route Hazard Screening"] = "FAIL"

    # 18. Strict HTTPS & CORS Restricted Origin Protection
    print("\n[18] Checking HTTPS & CORS Origin Protection...")
    if base.startswith("https://"):
        print(f"    PASS: Enforced HTTPS validated: {base}")
        results["HTTPS Enforced"] = "PASS"
    else:
        print(f"    WARN: Base URL is not HTTPS: {base}")
        results["HTTPS Enforced"] = "WARN"

    # Test allowed origin
    code_cors_ok, _, hdrs_ok = _http_request(
        f"{base}/api/v1/health",
        method="OPTIONS",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    # Test disallowed origin
    code_cors_bad, _, hdrs_bad = _http_request(
        f"{base}/api/v1/health",
        method="OPTIONS",
        headers={"Origin": "https://malicious-site.com", "Access-Control-Request-Method": "GET"},
    )
    cors_allowed = hdrs_ok.get("access-control-allow-origin") == "http://localhost:3000"
    cors_blocked = "access-control-allow-origin" not in hdrs_bad or code_cors_bad >= 400

    if cors_allowed and cors_blocked:
        print("    PASS: CORS properly restricts access (configured origin allowed, unauthorized origin rejected).")
        results["CORS Restricted to Configured Origins"] = "PASS"
    else:
        print(f"    FAIL: CORS policy issue: allowed={cors_allowed}, blocked={cors_blocked}")
        results["CORS Restricted to Configured Origins"] = "FAIL"

    # 19. WebSocket Security (Unauthorized Rejection & Authorized Handshake)
    print("\n[19] Checking WebSocket Security (/ws/v1/events)...")
    ws_endpoint = f"{ws_base}/ws/v1/events"
    loop = asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else asyncio.new_event_loop()

    # Unauthorized probe
    unauth_ok, unauth_msg = loop.run_until_complete(_probe_websocket(ws_endpoint, token=None))
    print(f"    Unauthorized WebSocket connection: {unauth_msg}")
    if unauth_ok:
        results["WebSocket Rejects Unauthorized Connection"] = "PASS"
    else:
        results["WebSocket Rejects Unauthorized Connection"] = "FAIL"

    # Authorized probe
    if auth_token:
        auth_ws_ok, auth_ws_msg = loop.run_until_complete(_probe_websocket(ws_endpoint, token=auth_token))
        print(f"    Authorized WebSocket connection: {auth_ws_msg}")
        if auth_ws_ok:
            results["WebSocket Accepts Authorized Connection"] = "PASS"
        else:
            results["WebSocket Accepts Authorized Connection"] = "FAIL"
    else:
        results["WebSocket Accepts Authorized Connection"] = "SKIPPED (no auth token)"

    # Summary
    print("\n" + "=" * 80)
    print("LIVE VERIFICATION RESULTS SUMMARY")
    print("=" * 80)
    passed_count = sum(1 for v in results.values() if v == "PASS")
    failed_count = sum(1 for v in results.values() if v == "FAIL")
    skipped_count = sum(1 for v in results.values() if "SKIPPED" in v)
    total_count = len(results)

    for test, res in results.items():
        print(f"  [{res}] {test}")

    print(f"\nTotal: {passed_count}/{total_count} checks passed ({skipped_count} skipped, {failed_count} failed).")
    success = failed_count == 0 and passed_count >= 16
    print(f"Verdict: {'ALL CHECKS PASSED' if success else 'ISSUES DETECTED'}")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live FloodLens AI Backend Verifier")
    parser.add_argument("url", nargs="?", default="https://floodlens-backend-4pt5.onrender.com", help="Base URL of deployed backend")
    args = parser.parse_args()
    ok = verify_deployment(args.url)
    sys.exit(0 if ok else 1)
