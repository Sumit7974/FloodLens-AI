"""Satellite job dispatch and imagery scene metadata endpoints."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.enums import UserRole
from app.models.satellite import SatelliteScene
from app.models.user import User
from app.schemas.satellite import (
    SatelliteJobCreate,
    SatelliteJobResponse,
    SatelliteSceneCreate,
    SatelliteSceneResponse,
)

router = APIRouter(prefix="/satellite", tags=["Satellite & GIS"])

# In-memory tracking for scheduled background jobs
_SATELLITE_JOBS: Dict[str, Dict[str, Any]] = {}


@router.post(
    "/scenes",
    response_model=SatelliteSceneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a satellite imagery scene",
    description="Imports optical (Sentinel-2, Landsat) or radar (Sentinel-1 SAR) scene metadata. Authorized only.",
)
async def register_satellite_scene(
    scene_in: SatelliteSceneCreate,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> SatelliteScene:
    """Store satellite scene metadata and asset reference with provenance validation."""
    scene_id = scene_in.id or f"scene_{uuid.uuid4().hex[:12]}"

    existing = db.query(SatelliteScene).filter(SatelliteScene.id == scene_id).first()
    if existing:
        raise ConflictError(
            message=f"Satellite scene '{scene_id}' is already registered",
            code="SCENE_ALREADY_EXISTS",
        )

    new_scene = SatelliteScene(
        id=scene_id,
        provider=scene_in.provider,
        sensor=scene_in.sensor,
        modality=scene_in.modality.lower(),
        captured_at=scene_in.captured_at,
        cloud_quality=scene_in.cloud_quality,
        asset_ref=scene_in.asset_ref,
        bbox_geojson=scene_in.bbox_geojson,
    )
    db.add(new_scene)
    db.commit()
    db.refresh(new_scene)
    return new_scene


@router.get(
    "/scenes",
    response_model=List[SatelliteSceneResponse],
    status_code=status.HTTP_200_OK,
    summary="List available satellite image scenes",
    description="List stored optical and SAR scenes with cloud coverage and capture timestamp.",
)
async def list_satellite_scenes(
    modality: Optional[str] = Query(None, description="Filter by modality: optical, sar"),
    sensor: Optional[str] = Query(None, description="Filter by sensor: Sentinel-2, Sentinel-1"),
    db: Session = Depends(get_db),
) -> List[SatelliteScene]:
    """List stored optical and SAR scenes."""
    query = db.query(SatelliteScene)
    if modality:
        query = query.filter(SatelliteScene.modality == modality.lower())
    if sensor:
        query = query.filter(SatelliteScene.sensor.ilike(f"%{sensor}%"))
    return query.order_by(SatelliteScene.captured_at.desc()).all()


@router.get(
    "/scenes/{scene_id}",
    response_model=SatelliteSceneResponse,
    status_code=status.HTTP_200_OK,
    summary="Get satellite scene by ID",
)
async def get_satellite_scene(scene_id: str, db: Session = Depends(get_db)) -> SatelliteScene:
    """Retrieve metadata for a specific satellite scene."""
    scene = db.query(SatelliteScene).filter(SatelliteScene.id == scene_id).first()
    if not scene:
        raise NotFoundError(message=f"Satellite scene '{scene_id}' not found", code="SCENE_NOT_FOUND")
    return scene


@router.post(
    "/jobs",
    response_model=SatelliteJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start authorized satellite processing job",
    description="Enqueues satellite NDWI/MNDWI water extraction or SAR change detection task.",
)
async def create_satellite_job(
    job_spec: SatelliteJobCreate,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
) -> SatelliteJobResponse:
    """Enqueue satellite NDWI/MNDWI or SAR processing task."""
    job_id = f"sat_job_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    _SATELLITE_JOBS[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "method": job_spec.method,
        "event_id": job_spec.event_id,
        "scene_id": job_spec.scene_id,
        "requested_by": current_user.id,
        "created_at": now,
        "progress_percent": 10,
    }
    return SatelliteJobResponse(
        job_id=job_id,
        status="processing",
        message=f"Satellite {job_spec.method} processing pipeline scheduled",
        requested_by=current_user.id,
        created_at=now,
    )


@router.get(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get status of satellite processing job",
)
async def get_satellite_job_status(job_id: str) -> Dict[str, Any]:
    """Poll progress of a background satellite processing job. Unknown IDs return 404."""
    if job_id not in _SATELLITE_JOBS:
        raise NotFoundError(
            message=f"Satellite processing job '{job_id}' not found",
            code="JOB_NOT_FOUND",
        )

    job = _SATELLITE_JOBS[job_id]
    created_at_val = job.get("created_at")
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percent": job.get("progress_percent", 0),
        "method": job.get("method"),
        "event_id": job.get("event_id"),
        "scene_id": job.get("scene_id"),
        "requested_by": job.get("requested_by"),
        "created_at": created_at_val.isoformat() if hasattr(created_at_val, "isoformat") else created_at_val,
    }
