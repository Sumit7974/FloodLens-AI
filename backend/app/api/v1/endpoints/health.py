"""Health check endpoint for FloodLens AI backend."""
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from app.config import get_settings
from app.database import check_db_connection
from app.schemas.health import DatabaseHealth, HealthResponse, ReadinessCheck, ReadinessResponse

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


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        200: {"description": "Service is ready to handle traffic"},
        503: {"description": "Service is degraded or dependencies unavailable", "model": ReadinessResponse},
    },
    summary="Get backend readiness status",
    description="Readiness probe verifying operational state, database connectivity, and PostGIS spatial capabilities.",
)
async def get_readiness(response: Response) -> ReadinessResponse:
    """Service readiness check for Kubernetes/orchestration probes and load balancers."""
    db_status = check_db_connection()
    is_connected = db_status.get("connected", False)

    checks = [
        ReadinessCheck(
            name="database",
            status="ok" if is_connected else "failed",
            details=(
                f"{db_status.get('database_type')} ping successful ({db_status.get('latency_ms')}ms)"
                if is_connected
                else f"Database connection error: {db_status.get('error')}"
            ),
        )
    ]

    # PostGIS extension check
    if not settings.is_sqlite:
        postgis_ok = db_status.get("postgis_installed", False)
        checks.append(
            ReadinessCheck(
                name="postgis",
                status="ok" if postgis_ok else "failed",
                details=(
                    f"PostGIS version {db_status.get('postgis_version')}"
                    if postgis_ok
                    else "PostGIS extension not detected on PostgreSQL host"
                ),
            )
        )
        is_ready = is_connected and postgis_ok
    else:
        # SQLite development/testing fallback
        checks.append(
            ReadinessCheck(
                name="postgis",
                status="ok",
                details="SQLite spatial emulation active",
            )
        )
        is_ready = is_connected

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        app_name=settings.app_name,
        version="0.1.0",
        environment=settings.environment,
        timestamp=datetime.now(timezone.utc),
        database=DatabaseHealth(
            connected=is_connected,
            database_type=db_status.get("database_type", "unknown"),
            postgis_installed=db_status.get("postgis_installed", False),
            postgis_version=db_status.get("postgis_version"),
            latency_ms=db_status.get("latency_ms"),
            error=db_status.get("error"),
        ),
        checks=checks,
    )

