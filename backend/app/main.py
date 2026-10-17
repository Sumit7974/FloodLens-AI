"""Main FastAPI application entry point for FloodLens AI."""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.endpoints.health import get_health, get_readiness
from app.api.v1.router import api_v1_router
from app.config import get_settings
from app.core.exceptions import (
    FloodLensAPIException,
    floodlens_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.database import check_db_connection
from app.websocket.router import ws_router

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("floodlens.backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger.info("Initializing %s (mode=%s)...", settings.app_name, settings.operational_mode)
    db_status = check_db_connection()
    if db_status["connected"]:
        logger.info(
            "Database connected successfully (%s, PostGIS: %s, latency: %sms)",
            db_status["database_type"],
            db_status["postgis_version"] or "Not installed",
            db_status["latency_ms"],
        )
    else:
        logger.warning("Database connection failed during startup: %s", db_status["error"])

    yield

    logger.info("Shutting down %s...", settings.app_name)


def create_application() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.app_name,
        description=(
            "FloodLens AI: End-to-end flood prediction, satellite flood mapping, "
            "citizen protection, and evidence-based model improvement."
        ),
        version="0.1.0",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    # Correlation ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:8]}"
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

    # CORS configuration
    origins = settings.cors_origins if isinstance(settings.cors_origins, list) else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register standardized error handlers
    app.add_exception_handler(FloodLensAPIException, floodlens_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Mount API routers
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    app.include_router(ws_router, prefix=settings.ws_v1_prefix)

    # Probes and discovery
    @app.get("/health", tags=["Root"], include_in_schema=False)
    async def root_health():
        """Root health probe alias."""
        return await get_health()

    @app.get("/ready", tags=["Root"], include_in_schema=False)
    async def root_ready(response: Response):
        """Root readiness probe alias."""
        return await get_readiness(response)

    @app.get("/", tags=["Root"])
    async def root_index() -> dict:
        """Root service index."""
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": f"{settings.api_v1_prefix}/docs",
            "health": f"{settings.api_v1_prefix}/health",
            "ready": f"{settings.api_v1_prefix}/ready",
            "operational_mode": settings.operational_mode,
        }

    return app



app = create_application()
