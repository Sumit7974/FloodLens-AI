"""Central API v1 router consolidating all modular endpoint routers."""
from fastapi import APIRouter
from app.api.v1.endpoints.alerts import router as alerts_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.assistance import router as assistance_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.facilities import router as facilities_router
from app.api.v1.endpoints.flood_events import router as flood_events_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.locations import router as locations_router
from app.api.v1.endpoints.monitoring import router as monitoring_router
from app.api.v1.endpoints.predictions import router as predictions_router
from app.api.v1.endpoints.satellite import router as satellite_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(locations_router)
api_v1_router.include_router(predictions_router)
api_v1_router.include_router(flood_events_router)
api_v1_router.include_router(alerts_router)
api_v1_router.include_router(assistance_router)
api_v1_router.include_router(monitoring_router)
api_v1_router.include_router(facilities_router)
api_v1_router.include_router(satellite_router)
api_v1_router.include_router(analytics_router)
