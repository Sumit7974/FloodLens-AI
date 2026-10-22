"""Lightweight testing mock server on port 8000 for verifying Phase 3 Live Backend transition."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

GAUGE_STATIONS = [
    {
        "station_id": "gauge-chatara",
        "name": "Chatara Hydro-Station (Live Sensor)",
        "river": "Saptakoshi Main Stem",
        "coordinates": [87.163, 26.871],
        "current_level": 8.24,
        "warning_level": 7.0,
        "danger_level": 8.0,
        "discharge_rate": 14680,
        "trend": "RISING",
        "last_reported_at": "Just now (Live Telemetry)",
        "battery_level": 99,
        "status": "CRITICAL",
    },
    {
        "station_id": "gauge-barrage",
        "name": "Koshi Barrage Control (Live Sensor)",
        "river": "Koshi Main Channel",
        "coordinates": [86.918, 26.522],
        "current_level": 74.92,
        "warning_level": 74.0,
        "danger_level": 75.0,
        "discharge_rate": 13120,
        "trend": "RISING",
        "last_reported_at": "Just now (Live Telemetry)",
        "battery_level": 95,
        "status": "WARNING",
    },
]

class TestServerHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization')

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()

        path = self.path
        if '/health' in path or path == '/':
            payload = {"status": "healthy", "service": "FloodLens Live Backend Container"}
        elif '/monitoring/gauges' in path or '/monitoring/rivers' in path:
            payload = {"status": "active", "stations": GAUGE_STATIONS, "count": len(GAUGE_STATIONS)}
        elif '/predictions/map' in path:
            payload = {
                "type": "FeatureCollection",
                "properties": {
                    "horizon": "3H",
                    "event_id": "koshi-basin-primary",
                    "model_version": "FloodLens-LSTM-GNN v1.2",
                    "calibrated_at": "2026-10-22T00:00:00Z"
                },
                "features": [
                    {
                        "type": "Feature",
                        "id": "inundation-3h",
                        "properties": {
                            "horizon": "3H",
                            "inflow_cusecs": 13950,
                            "threat_level": "CRITICAL",
                            "exposed_population": 42000
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[87.05, 26.75], [87.15, 26.78], [87.18, 26.68], [87.08, 26.65], [87.05, 26.75]]]
                        }
                    }
                ]
            }
        elif '/flood-events' in path:
            payload = {
                "id": "koshi-basin-primary",
                "name": "Nepal Terai — Koshi Basin (2026 Monsoon Surge)",
                "status": "SURGING",
                "peak_discharge_m3s": 14250,
                "crest_time": "+3.5 Hours Estimated",
                "bounding_box": [[86.9, 26.4], [87.3, 26.9]],
            }
        else:
            payload = {"status": "active"}

        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def log_message(self, format, *args):
        print(f"[Live Backend 8000] {self.command} {self.path} -> 200 OK")

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8000), TestServerHandler)
    print("Serving FloodLens Live API on http://127.0.0.1:8000...")
    server.serve_forever()
