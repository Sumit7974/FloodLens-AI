"""Flood events, observed extent, settlement exposure, and report endpoints."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.core.spatial import (
    calculate_area_km2_from_geometry,
    geometry_to_geojson,
    get_affected_settlements_spatial,
    get_exposed_assets_spatial,
    to_wkt_element,
)
from app.database import get_db
from app.models.enums import EventType, OperationalMode, UserRole
from app.models.flood_event import FloodEvent
from app.models.satellite import FloodExtent
from app.models.user import User
from app.schemas.event import WebSocketEvent
from app.schemas.flood_event import (
    AffectedSettlementsResponse,
    ExposedAssetsResponse,
    FloodEventCreate,
    FloodEventResponse,
    FloodExtentCreate,
    FloodExtentResponse,
    FloodReportResponse,
)
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/flood-events", tags=["Flood Events"])


@router.post(
    "",
    response_model=FloodEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or import a flood event",
    description="Registers a historical demo or live flood event episode. Restricted to authorized responders and admins.",
)
async def create_flood_event(
    event_in: FloodEventCreate,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> FloodEvent:
    """Create a new flood event with explicit operational mode and provenance metadata."""
    if event_in.id:
        existing = db.query(FloodEvent).filter(FloodEvent.id == event_in.id).first()
        if existing:
            raise ConflictError(
                message=f"Flood event with id '{event_in.id}' already exists",
                code="EVENT_ALREADY_EXISTS",
            )

    new_event = FloodEvent(
        id=event_in.id,
        region_id=event_in.region_id,
        name=event_in.name,
        start_at=event_in.start_at,
        end_at=event_in.end_at,
        mode=event_in.mode,
        source_refs=event_in.source_refs,
        description=event_in.description,
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event


@router.get(
    "",
    response_model=List[FloodEventResponse],
    status_code=status.HTTP_200_OK,
    summary="List flood events",
    description="Retrieve all registered flood event episodes with optional region or mode filtering.",
)
async def list_flood_events(
    mode: Optional[OperationalMode] = None,
    region_id: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[FloodEvent]:
    """List flood events ordered by start date."""
    query = db.query(FloodEvent)
    if mode:
        query = query.filter(FloodEvent.mode == mode)
    if region_id:
        query = query.filter(FloodEvent.region_id == region_id)
    return query.order_by(FloodEvent.start_at.desc()).all()


@router.get(
    "/{event_id}",
    response_model=FloodEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get flood event details",
)
async def get_flood_event(event_id: str, db: Session = Depends(get_db)) -> FloodEvent:
    """Retrieve flood event metadata by unique ID."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")
    return event


@router.post(
    "/{event_id}/extent",
    response_model=FloodExtentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Import georeferenced flood extent for an event",
    description="Stores derived satellite flood extent mask in PostGIS and notifies subscribers. Authorized only.",
)
async def import_flood_extent(
    event_id: str,
    extent_in: FloodExtentCreate,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> FloodExtentResponse:
    """Ingest satellite-derived flood extent polygons and emit WebSocket notification."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    # Parse and validate geometry if provided
    geometry_element = None
    if extent_in.geometry:
        geometry_element = to_wkt_element(extent_in.geometry, expected_type="MULTIPOLYGON", srid=4326)

    new_extent = FloodExtent(
        id=extent_in.id,
        event_id=event_id,
        observed_at=extent_in.observed_at,
        method=extent_in.method,
        polygon_ref=extent_in.polygon_ref,
        raster_ref=extent_in.raster_ref,
        area_km2=extent_in.area_km2,
        source_scene_ids=extent_in.source_scene_ids,
        confidence=extent_in.confidence,
        geometry=geometry_element,
    )
    db.add(new_extent)
    db.commit()
    db.refresh(new_extent)

    # Publish real-time WebSocket event
    ws_event = WebSocketEvent(
        event_id=f"evt_extent_{new_extent.id}",
        type=EventType.FLOOD_EXTENT_UPDATED.value,
        timestamp=datetime.now(timezone.utc),
        location_id=event.region_id,
        resource_id=new_extent.id,
    )
    await connection_manager.broadcast(ws_event)

    return FloodExtentResponse(
        id=new_extent.id,
        event_id=new_extent.event_id,
        observed_at=new_extent.observed_at,
        method=new_extent.method,
        polygon_ref=new_extent.polygon_ref,
        raster_ref=new_extent.raster_ref,
        area_km2=new_extent.area_km2,
        source_scene_ids=new_extent.source_scene_ids or [],
        confidence=new_extent.confidence,
        geometry=geometry_to_geojson(new_extent.geometry),
    )


@router.get(
    "/{event_id}/extent",
    response_model=FloodExtentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get observed flood extent for an event",
    description="Returns the most recent georeferenced flood extent layer with full GeoJSON polygon geometry.",
)
async def get_flood_extent(event_id: str, db: Session = Depends(get_db)) -> FloodExtentResponse:
    """Retrieve derived satellite flood extent mask/polygons with real GeoJSON geometry."""
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
        geometry=geometry_to_geojson(extent.geometry),
    )


@router.get(
    "/{event_id}/extent/geojson",
    status_code=status.HTTP_200_OK,
    summary="Get flood extent as GeoJSON Feature",
    description="Direct RFC 7946 GeoJSON Feature format for web/mobile mapping clients.",
)
async def get_flood_extent_geojson(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Return RFC 7946 GeoJSON Feature of the flood extent."""
    extent = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.desc())
        .first()
    )
    if not extent:
        raise NotFoundError(message=f"No flood extent observed for event '{event_id}'", code="EXTENT_NOT_FOUND")

    gj = geometry_to_geojson(extent.geometry)
    return {
        "type": "Feature",
        "id": extent.id,
        "properties": {
            "event_id": extent.event_id,
            "observed_at": extent.observed_at.isoformat(),
            "method": extent.method,
            "area_km2": extent.area_km2,
            "confidence": extent.confidence,
            "source_scene_ids": extent.source_scene_ids,
        },
        "geometry": gj,
    }


@router.get(
    "/{event_id}/settlements",
    response_model=AffectedSettlementsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get affected settlements intersected by flood extent",
    description="Performs spatial intersection in PostGIS between flood extent and mapped settlements.",
)
async def get_affected_settlements(
    event_id: str, db: Session = Depends(get_db)
) -> AffectedSettlementsResponse:
    """Retrieve settlements identified as exposed or inundated through spatial intersection."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    extent = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.desc())
        .first()
    )

    if not extent:
        return AffectedSettlementsResponse(
            event_id=event_id,
            region_id=event.region_id,
            extent_id=None,
            observed_at=None,
            total_settlements_affected=0,
            affected_settlements=[],
            status="no_extent_available",
        )

    # Perform actual PostGIS / spatial intersection
    affected = get_affected_settlements_spatial(db, extent)

    return AffectedSettlementsResponse(
        event_id=event_id,
        region_id=event.region_id,
        extent_id=extent.id,
        observed_at=extent.observed_at,
        total_settlements_affected=len(affected),
        affected_settlements=affected,
        status="completed",
    )


@router.get(
    "/{event_id}/assets",
    response_model=ExposedAssetsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get exposed infrastructure assets",
    description="Computes spatial intersection between observed flood extent and critical assets (roads, buildings, agriculture).",
)
async def get_exposed_assets(event_id: str, db: Session = Depends(get_db)) -> ExposedAssetsResponse:
    """Retrieve potentially exposed roads, bridges, and structures via spatial intersection."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    extent = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.desc())
        .first()
    )

    if not extent:
        return ExposedAssetsResponse(
            event_id=event_id,
            roads_exposed_km=0.0,
            structures_exposed_count=0,
            cropland_exposed_ha=0.0,
            exposed_assets=[],
            status="no_extent_available",
        )

    asset_metrics = get_exposed_assets_spatial(db, extent)
    return ExposedAssetsResponse(
        event_id=event_id,
        roads_exposed_km=asset_metrics["roads_exposed_km"],
        structures_exposed_count=asset_metrics["structures_exposed_count"],
        cropland_exposed_ha=asset_metrics["cropland_exposed_ha"],
        exposed_assets=asset_metrics["exposed_assets"],
        status="completed",
    )


@router.get(
    "/{event_id}/report",
    response_model=FloodReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Download impact assessment summary report",
    description="Returns synthesized impact assessment combining flood extent, affected settlements, and critical asset exposure.",
)
async def get_flood_report(event_id: str, db: Session = Depends(get_db)) -> FloodReportResponse:
    """Return synthesized impact report metadata."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    extent = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.desc())
        .first()
    )

    affected_count = 0
    roads_km = 0.0
    structures_count = 0
    cropland_ha = 0.0
    extent_observed_at = None
    extent_area_km2 = None

    if extent:
        extent_observed_at = extent.observed_at
        extent_area_km2 = extent.area_km2
        affected = get_affected_settlements_spatial(db, extent)
        affected_count = len(affected)
        asset_metrics = get_exposed_assets_spatial(db, extent)
        roads_km = asset_metrics["roads_exposed_km"]
        structures_count = asset_metrics["structures_exposed_count"]
        cropland_ha = asset_metrics["cropland_exposed_ha"]

    return FloodReportResponse(
        event_id=event_id,
        event_name=event.name,
        region_id=event.region_id,
        mode=event.mode.value if hasattr(event.mode, "value") else str(event.mode),
        extent_observed_at=extent_observed_at,
        extent_area_km2=extent_area_km2,
        total_settlements_affected=affected_count,
        roads_exposed_km=roads_km,
        structures_exposed_count=structures_count,
        cropland_exposed_ha=cropland_ha,
        report_generated_at=datetime.now(timezone.utc),
        status="generated",
        download_url=f"/api/v1/flood-events/{event_id}/report/download",
    )
