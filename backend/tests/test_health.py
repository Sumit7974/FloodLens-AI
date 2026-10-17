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
