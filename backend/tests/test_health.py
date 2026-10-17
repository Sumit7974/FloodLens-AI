"""Automated tests for health check and root service discovery."""
from fastapi import status
from fastapi.testclient import TestClient


def test_root_index(client: TestClient):
    """Test GET / returns basic service discovery metadata."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "name" in data
    assert data["docs"] == "/api/v1/docs"
    assert data["health"] == "/api/v1/health"
    assert data["ready"] == "/api/v1/ready"
    assert "operational_mode" in data


def test_health_check_endpoint(client: TestClient):
    """Test GET /api/v1/health returns contract-compliant health response."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Validate top-level keys
    assert "status" in data
    assert data["status"] in ("healthy", "degraded")
    assert data["app_name"] == "FloodLens AI Backend"
    assert data["version"] == "0.1.0"
    assert "environment" in data
    assert "operational_mode" in data
    assert "timestamp" in data

    # Validate database health sub-structure
    assert "database" in data
    db_data = data["database"]
    assert "connected" in db_data
    assert "database_type" in db_data
    assert "postgis_installed" in db_data
    assert isinstance(db_data["connected"], bool)


def test_readiness_endpoint_ready(client: TestClient):
    """Test GET /api/v1/ready and /ready return 200 and ready status when database is online."""
    for path in ("/api/v1/ready", "/ready"):
        response = client.get(path)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["status"] == "ready"
        assert data["app_name"] == "FloodLens AI Backend"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        assert data["database"]["connected"] is True
        assert len(data["checks"]) >= 2

        db_check = next((c for c in data["checks"] if c["name"] == "database"), None)
        assert db_check is not None
        assert db_check["status"] == "ok"

        pg_check = next((c for c in data["checks"] if c["name"] == "postgis"), None)
        assert pg_check is not None
        assert pg_check["status"] == "ok"


def test_readiness_endpoint_degraded(client: TestClient, monkeypatch):
    """Test GET /api/v1/ready returns HTTP 503 when database connectivity fails."""
    from app.api.v1.endpoints import health

    def mock_broken_db():
        return {
            "connected": False,
            "database_type": "postgresql",
            "postgis_installed": False,
            "postgis_version": None,
            "latency_ms": None,
            "error": "Connection refused to database host:5432",
        }

    monkeypatch.setattr(health, "check_db_connection", mock_broken_db)

    response = client.get("/api/v1/ready")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()

    assert data["status"] == "not_ready"
    assert data["database"]["connected"] is False
    assert "error" in data["database"]

    db_check = next((c for c in data["checks"] if c["name"] == "database"), None)
    assert db_check is not None
    assert db_check["status"] == "failed"
    assert "Connection refused" in db_check["details"]

