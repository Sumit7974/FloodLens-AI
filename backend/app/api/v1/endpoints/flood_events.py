"""Flood events, observed extent, settlement exposure, and report endpoints."""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent
from app.schemas.flood_event import FloodEventResponse, FloodExtentResponse

router = APIRouter(prefix="/flood-events", tags=["Flood Events"])


@router.get(
    "/{event_id}/extent",
    response_model=FloodExtentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get observed flood extent for an event",
)
async def get_flood_extent(event_id: str, db: Session = Depends(get_db)) -> FloodExtentResponse:
    """Retrieve derived satellite flood extent mask/polygons."""
    extent = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.desc())
        .first()
    )
    if not extent:
        raise NotFoundError(message=f"No flood extent observed for event '{event_id}'", code="EXTENT_NOT_FOUND")

    return FloodExtentResponse(
        id=extent.id,
        event_id=extent.event_id,
        observed_at=extent.observed_at,
        method=extent.method,
        polygon_ref=extent.polygon_ref,
        raster_ref=extent.raster_ref,
        area_km2=extent.area_km2,
        source_scene_ids=extent.source_scene_ids or [],
        confidence=extent.confidence,
    )


@router.get(
    "/{event_id}/settlements",
    status_code=status.HTTP_200_OK,
    summary="Get affected settlements intersected by flood extent",
)
async def get_affected_settlements(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve settlements identified as exposed or inundated."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    return {
        "event_id": event_id,
        "region_id": event.region_id,
        "affected_settlements": [],
        "total_settlements_affected": 0,
        "status": "pending_gis_pipeline",
    }


@router.get(
    "/{event_id}/assets",
    status_code=status.HTTP_200_OK,
    summary="Get exposed infrastructure assets",
)
async def get_exposed_assets(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve potentially exposed roads, bridges, and structures."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    return {
        "event_id": event_id,
        "roads_exposed_km": 0.0,
        "structures_exposed_count": 0,
        "cropland_exposed_ha": 0.0,
        "status": "pending_gis_pipeline",
    }


@router.get(
    "/{event_id}/report",
    status_code=status.HTTP_200_OK,
    summary="Download impact assessment summary report",
)
async def get_flood_report(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return report metadata and downloadable artifact references."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    return {
        "event_id": event_id,
        "event_name": event.name,
        "report_generated_at": None,
        "status": "pending_generation",
        "download_url": None,
    }
