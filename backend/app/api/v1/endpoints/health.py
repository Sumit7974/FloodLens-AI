"""Health check endpoint for FloodLens AI backend."""
from datetime import datetime, timezone
from fastapi import APIRouter, status
from app.config import get_settings
from app.database import check_db_connection
from app.schemas.health import DatabaseHealth, HealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get backend and database health status",
    description="Returns service status, environment, operational mode, and database/PostGIS connectivity details.",
)
async def get_health() -> HealthResponse:
    """Service and database health check."""
    db_status = check_db_connection()

    is_healthy = db_status.get("connected", False)
    overall_status = "healthy" if is_healthy else "degraded"

    return HealthResponse(
        status=overall_status,
        app_name=settings.app_name,
        version="0.1.0",
        environment=settings.environment,
        operational_mode=settings.operational_mode,
        timestamp=datetime.now(timezone.utc),
        database=DatabaseHealth(
            connected=db_status.get("connected", False),
            database_type=db_status.get("database_type", "unknown"),
            postgis_installed=db_status.get("postgis_installed", False),
            postgis_version=db_status.get("postgis_version"),
            latency_ms=db_status.get("latency_ms"),
            error=db_status.get("error"),
        ),
    )
