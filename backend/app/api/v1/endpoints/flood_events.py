"""Flood events, observed extent, settlement exposure, and report endpoints."""
import csv
from datetime import datetime, timezone
import io
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
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
from app.models.evaluation import Evaluation
from app.models.flood_event import FloodEvent
from app.models.forecast import ForecastRun, RiskPrediction
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
from app.schemas.timeline import (
    EventTimelineCoverage,
    EventTimelineResponse,
    TimelineEntry,
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
        provenance=extent_in.provenance,
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
        provenance=new_extent.provenance,
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
        .order_by(FloodExtent.observed_at.desc(), FloodExtent.created_at.desc())
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
        provenance=extent.provenance,
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
        .order_by(FloodExtent.observed_at.desc(), FloodExtent.created_at.desc())
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
            "provenance": extent.provenance,
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
        .order_by(FloodExtent.observed_at.desc(), FloodExtent.created_at.desc())
        .first()
    )

    if not extent:
        return AffectedSettlementsResponse(
            event_id=event_id,
            region_id=event.region_id,
            extent_id=None,
            observed_at=None,
            total_settlements_evaluated=0,
            total_settlements_affected=0,
            affected_settlements=[],
            status="no_extent_available",
            notes="No flood extent has been observed or imported for this event.",
        )

    if not extent.geometry:
        return AffectedSettlementsResponse(
            event_id=event_id,
            region_id=event.region_id,
            extent_id=extent.id,
            observed_at=extent.observed_at,
            total_settlements_evaluated=0,
            total_settlements_affected=0,
            affected_settlements=[],
            status="no_extent_geometry",
            notes="Observed flood extent has no valid geospatial polygon geometry attached for spatial intersection.",
        )

    # Perform actual PostGIS / spatial intersection scoped to event study area / region
    affected, total_evaluated = get_affected_settlements_spatial(db, extent, region_id=event.region_id)

    if total_evaluated == 0:
        return AffectedSettlementsResponse(
            event_id=event_id,
            region_id=event.region_id,
            extent_id=extent.id,
            observed_at=extent.observed_at,
            total_settlements_evaluated=0,
            total_settlements_affected=0,
            affected_settlements=[],
            status="no_settlement_data",
            notes=f"No mapped settlement GIS layers are available for spatial intersection in region '{event.region_id}'.",
        )

    return AffectedSettlementsResponse(
        event_id=event_id,
        region_id=event.region_id,
        extent_id=extent.id,
        observed_at=extent.observed_at,
        total_settlements_evaluated=total_evaluated,
        total_settlements_affected=len(affected),
        affected_settlements=affected,
        status="completed",
        notes=None,
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
        status=asset_metrics["status"],
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
    total_evaluated = 0
    settlements_status = "no_extent_available" if not extent else "no_settlement_data"
    assets_status = "no_extent_available" if not extent else "no_assets_available"
    roads_km = 0.0
    structures_count = 0
    cropland_ha = 0.0
    extent_observed_at = None
    extent_area_km2 = None
    overall_status = "pending_data"

    if extent:
        extent_observed_at = extent.observed_at
        extent_area_km2 = extent.area_km2
        if not extent.geometry:
            settlements_status = "no_extent_geometry"
            assets_status = "no_extent_geometry"
            overall_status = "incomplete_evidence"
        else:
            affected, total_evaluated = get_affected_settlements_spatial(db, extent, region_id=event.region_id)
            affected_count = len(affected)
            settlements_status = "completed" if total_evaluated > 0 else "no_settlement_data"
            asset_metrics = get_exposed_assets_spatial(db, extent)
            assets_status = asset_metrics["status"]
            roads_km = asset_metrics["roads_exposed_km"]
            structures_count = asset_metrics["structures_exposed_count"]
            cropland_ha = asset_metrics["cropland_exposed_ha"]

            if asset_metrics.get("status") == "no_extent_geometry":
                overall_status = "incomplete_evidence"
            else:
                overall_status = "summary_available"

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
        report_generated_at=None,
        status=overall_status,
        download_url=None,
        settlements_evaluated=total_evaluated,
        settlements_data_status=settlements_status,
        assets_data_status=assets_status,
        data_limitations=[
            "Physical exposure indicates spatial intersection with satellite water mask; exposure does not equal verified damage.",
            "Settlement population counts reflect census figures, not verified casualties or displaced persons.",
        ],
        data_provenance={
            "extent_id": extent.id if extent else None,
            "export_available": True if extent else False,
            "export_endpoint": f"/api/v1/flood-events/{event_id}/report/export",
        },
    )


@router.get(
    "/{event_id}/report/export",
    status_code=status.HTTP_200_OK,
    summary="Export impact assessment report as downloadable JSON or CSV",
    description="Generates a downloadable historical impact assessment or demo report artifact in JSON or CSV format.",
)
async def export_flood_report(
    event_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$", description="Export format: json or csv"),
    db: Session = Depends(get_db),
) -> Response:
    """Generate physical export file artifact (JSON or CSV) for the synthesized event impact report."""
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
    total_evaluated = 0
    roads_km = 0.0
    structures_count = 0
    cropland_ha = 0.0
    extent_observed_at_str = ""
    extent_area = 0.0
    extent_method = ""
    status_desc = "pending_data"

    if extent:
        extent_observed_at_str = extent.observed_at.isoformat()
        extent_area = extent.area_km2
        extent_method = extent.method
        if not extent.geometry:
            status_desc = "incomplete_evidence"
        else:
            affected, total_evaluated = get_affected_settlements_spatial(db, extent, region_id=event.region_id)
            affected_count = len(affected)
            settlements_status = "completed" if total_evaluated > 0 else "no_settlement_data"
            asset_metrics = get_exposed_assets_spatial(db, extent)
            assets_status = asset_metrics["status"]
            roads_km = asset_metrics["roads_exposed_km"]
            structures_count = asset_metrics["structures_exposed_count"]
            cropland_ha = asset_metrics["cropland_exposed_ha"]

            if asset_metrics.get("status") == "no_extent_geometry":
                status_desc = "incomplete_evidence"
            else:
                status_desc = "summary_available"

    now_iso = datetime.now(timezone.utc).isoformat()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "event_id",
            "event_name",
            "region_id",
            "mode",
            "status",
            "extent_observed_at",
            "extent_area_km2",
            "extent_method",
            "settlements_evaluated",
            "settlements_affected",
            "roads_exposed_km",
            "structures_exposed_count",
            "cropland_exposed_ha",
            "exported_at",
        ])
        writer.writerow([
            event.id,
            event.name,
            event.region_id,
            event.mode.value if hasattr(event.mode, "value") else str(event.mode),
            status_desc,
            extent_observed_at_str,
            extent_area,
            extent_method,
            total_evaluated,
            affected_count,
            roads_km,
            structures_count,
            cropland_ha,
            now_iso,
        ])
        csv_bytes = output.getvalue().encode("utf-8")
        filename = f"floodlens_impact_report_{event.id}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        report_data = {
            "event_id": event.id,
            "event_name": event.name,
            "region_id": event.region_id,
            "mode": event.mode.value if hasattr(event.mode, "value") else str(event.mode),
            "status": status_desc,
            "extent_observed_at": extent_observed_at_str or None,
            "extent_area_km2": extent_area if extent else None,
            "extent_method": extent_method or None,
            "total_settlements_evaluated": total_evaluated,
            "total_settlements_affected": affected_count,
            "roads_exposed_km": roads_km,
            "structures_exposed_count": structures_count,
            "cropland_exposed_ha": cropland_ha,
            "exported_at": now_iso,
            "limitations": [
                "Physical exposure indicates spatial intersection with satellite water mask; exposure does not equal verified damage.",
                "Settlement population counts reflect census figures, not verified casualties.",
            ],
            "provenance": {
                "system": "FloodLens AI Decision Support",
                "extent_id": extent.id if extent else None,
                "source_scenes": extent.source_scene_ids if extent else [],
            },
        }
        json_bytes = json.dumps(report_data, indent=2).encode("utf-8")
        filename = f"floodlens_impact_report_{event.id}.json"
        return Response(
            content=json_bytes,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.get(
    "/{event_id}/timeline",
    response_model=EventTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chronological historical event replay timeline",
    description=(
        "Presents chronological milestones for one historical flood event, including "
        "event boundaries, AI forecast issue times, target horizon valid times, "
        "satellite flood extent observations, and retrospective model evaluations."
    ),
)
async def get_event_timeline(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve chronological event milestones from persisted database records."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    entries: List[TimelineEntry] = []

    # 1. Event Start
    entries.append(
        TimelineEntry(
            entry_id=f"evt_start_{event.id}",
            timestamp=event.start_at,
            entry_type="event_start",
            title=f"Event Initiated: {event.name}",
            description=event.description or f"Flood event episode registered in region {event.region_id}",
            resource_id=event.id,
            resource_type="flood_event",
            details={
                "region_id": event.region_id,
                "mode": event.mode.value if hasattr(event.mode, "value") else str(event.mode),
                "source_refs": event.source_refs if isinstance(event.source_refs, dict) else {},
            },
            data_quality=None,
            limitations=["Historical dataset start boundary milestone."],
        )
    )

    # 2. Event End if present
    if event.end_at:
        duration_hrs = round((event.end_at - event.start_at).total_seconds() / 3600.0, 2)
        entries.append(
            TimelineEntry(
                entry_id=f"evt_end_{event.id}",
                timestamp=event.end_at,
                entry_type="event_end",
                title=f"Historical Episode End: {event.name}",
                description="Recorded end timestamp of the historical flood episode dataset",
                resource_id=event.id,
                resource_type="flood_event",
                details={
                    "region_id": event.region_id,
                    "duration_hours": duration_hrs,
                },
                data_quality=None,
                limitations=["Recorded dataset conclusion; does not represent an official government conclusion without external verification."],
            )
        )

    # 3. Forecast Runs
    forecast_runs = (
        db.query(ForecastRun)
        .filter(ForecastRun.event_id == event_id)
        .order_by(ForecastRun.issued_at.asc())
        .all()
    )
    for run in forecast_runs:
        preds: List[RiskPrediction] = (
            db.query(RiskPrediction)
            .filter(RiskPrediction.forecast_run_id == run.id)
            .order_by(RiskPrediction.horizon_hours.asc())
            .all()
        )
        horizons_summary = [
            {
                "hours": p.horizon_hours,
                "location_id": p.location_id,
                "valid_at": p.valid_at.isoformat(),
                "risk_level": p.risk_level.value if hasattr(p.risk_level, "value") else str(p.risk_level),
                "calibrated_probability": p.calibrated_probability,
                "data_quality": p.data_quality.value if hasattr(p.data_quality, "value") else str(p.data_quality),
            }
            for p in preds
        ]
        qualities = [p.data_quality.value for p in preds if hasattr(p.data_quality, "value")]
        if len(qualities) == 0:
            quality = None
        elif len(set(qualities)) == 1:
            quality = qualities[0]
        else:
            quality = "MIXED"

        entries.append(
            TimelineEntry(
                entry_id=f"fc_{run.id}",
                timestamp=run.issued_at,
                entry_type="forecast_issued",
                title=f"Risk Forecast Issued ({run.model_version})",
                description=f"Hydrological forecast issued with {len(preds)} horizon prediction(s)",
                resource_id=run.id,
                resource_type="forecast_run",
                details={
                    "model_version": run.model_version,
                    "issued_at": run.issued_at.isoformat(),
                    "input_data_cutoff_at": run.input_data_cutoff_at.isoformat() if run.input_data_cutoff_at else None,
                    "mode": run.mode.value if hasattr(run.mode, "value") else str(run.mode),
                    "status": run.status,
                    "prediction_horizons": horizons_summary,
                },
                data_quality=quality,
                limitations=run.limitations if isinstance(run.limitations, list) else [],
            )
        )

    # 4. Flood Extents
    extents = (
        db.query(FloodExtent)
        .filter(FloodExtent.event_id == event_id)
        .order_by(FloodExtent.observed_at.asc())
        .all()
    )
    for ext in extents:
        entries.append(
            TimelineEntry(
                entry_id=f"ext_{ext.id}",
                timestamp=ext.observed_at,
                entry_type="flood_observation",
                title=f"Satellite Flood Extent Observed ({ext.method})",
                description=f"Satellite sensor mapped {ext.area_km2} km2 inundated surface area",
                resource_id=ext.id,
                resource_type="flood_extent",
                details={
                    "method": ext.method,
                    "area_km2": ext.area_km2,
                    "observed_at": ext.observed_at.isoformat(),
                    "confidence": ext.confidence,
                    "source_scene_ids": ext.source_scene_ids if isinstance(ext.source_scene_ids, list) else [],
                    "polygon_ref": ext.polygon_ref,
                    "raster_ref": ext.raster_ref,
                    "has_spatial_geometry": ext.geometry is not None,
                },
                data_quality="SATELLITE_DERIVED",
                limitations=[f"Derived via {ext.method} satellite processing; surface extent accuracy subject to sensor resolution and canopy penetration limitations."],
            )
        )

    # 5. Evaluations
    evals = (
        db.query(Evaluation)
        .filter(Evaluation.event_id == event_id)
        .order_by(Evaluation.created_at.asc())
        .all()
    )
    for ev in evals:
        entries.append(
            TimelineEntry(
                entry_id=f"eval_{ev.id}",
                timestamp=ev.created_at,
                entry_type="evaluation_recorded",
                title=f"Model Evaluation Benchmark: {ev.target_type}",
                description=f"Retrospective performance benchmark against reference {ev.reference_id or 'ground truth'}",
                resource_id=ev.id,
                resource_type="evaluation",
                details={
                    "target_type": ev.target_type,
                    "baseline_version": ev.baseline_version,
                    "candidate_version": ev.candidate_version,
                    "metrics": ev.metrics if isinstance(ev.metrics, dict) else {},
                    "reference_id": ev.reference_id,
                    "notes": ev.notes,
                },
                data_quality="BENCHMARK_DERIVED",
                limitations=[ev.notes] if ev.notes else [],
            )
        )

    # Sort strictly chronologically by timestamp
    entries.sort(key=lambda x: x.timestamp)

    now_utc = datetime.now(timezone.utc)
    notes: List[str] = [
        f"Timeline reconstructed strictly from database records durably associated with event '{event.id}'.",
        "Alert dispatches and citizen assistance requests are handled via decoupled authority queues and are excluded from event timeline.",
    ]
    if len(forecast_runs) == 0:
        notes.append("No AI risk forecast runs have been recorded for this event.")
    if len(extents) == 0:
        notes.append("No satellite flood extents have been recorded for this event.")
    if len(evals) == 0:
        notes.append("No model benchmark evaluations have been recorded for this event.")

    return {
        "event_id": event.id,
        "event_name": event.name,
        "region_id": event.region_id,
        "mode": event.mode.value if hasattr(event.mode, "value") else str(event.mode),
        "start_at": event.start_at,
        "end_at": event.end_at,
        "timeline_generated_at": now_utc,
        "total_entries": len(entries),
        "coverage": {
            "has_forecasts": len(forecast_runs) > 0,
            "forecast_runs_count": len(forecast_runs),
            "has_flood_extents": len(extents) > 0,
            "flood_extents_count": len(extents),
            "has_evaluations": len(evals) > 0,
            "evaluations_count": len(evals),
        },
        "entries": entries,
        "notes": notes,
    }
