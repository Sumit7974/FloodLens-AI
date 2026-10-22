"""Satellite job dispatch and imagery scene metadata endpoints."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import ConflictError, FloodLensAPIException, NotFoundError
from app.database import get_db
from app.models.enums import UserRole
from app.models.satellite import SatelliteJob, SatelliteScene
from app.models.user import User
from app.schemas.satellite import (
    SatelliteJobCreate,
    SatelliteJobDetailResponse,
    SatelliteJobResponse,
    SatelliteSceneCreate,
    SatelliteSceneResponse,
)
from app.services.satellite_processor import process_satellite_job, validate_satellite_job_parameters

router = APIRouter(prefix="/satellite", tags=["Satellite & GIS"])


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
    description="Enqueues durable optical NDWI or SAR change detection processing job. Authorized authority/admin only.",
)
async def create_satellite_job(
    job_spec: SatelliteJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> SatelliteJobResponse:
    """Validate parameters and enqueue a durable background satellite processing job."""
    # 1. Comprehensive domain validation
    target_scene, baseline_scene, flood_event, resolved_asset = validate_satellite_job_parameters(db, job_spec)

    normalized_method = (job_spec.method or "").strip().upper()

    # 2. Duplicate detection: if an identical job is already QUEUED or RUNNING, reuse it
    existing_active = (
        db.query(SatelliteJob)
        .filter(
            SatelliteJob.scene_id == job_spec.scene_id,
            SatelliteJob.baseline_scene_id == job_spec.baseline_scene_id,
            SatelliteJob.method == normalized_method,
            SatelliteJob.event_id == job_spec.event_id,
            SatelliteJob.status.in_(["QUEUED", "RUNNING"]),
        )
        .first()
    )
    if existing_active:
        return SatelliteJobResponse(
            job_id=existing_active.id,
            status=existing_active.status,
            message="An identical satellite processing job is already in progress.",
            requested_by=existing_active.requested_by,
            created_at=existing_active.created_at,
        )

    # 3. Create durable database record
    job_id = f"sat_job_{uuid.uuid4().hex[:12]}"
    new_job = SatelliteJob(
        id=job_id,
        event_id=job_spec.event_id,
        scene_id=job_spec.scene_id,
        baseline_scene_id=job_spec.baseline_scene_id,
        method=normalized_method,
        threshold=job_spec.threshold or 0.0,
        status="QUEUED",
        progress_percent=0.0,
        requested_by=current_user.email or current_user.id,
        parameters={
            "threshold": job_spec.threshold,
            "scene_id": job_spec.scene_id,
            "baseline_scene_id": job_spec.baseline_scene_id,
            "method": normalized_method,
            "event_id": job_spec.event_id,
        },
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # 4. Dispatch background worker task
    background_tasks.add_task(process_satellite_job, new_job.id)

    return SatelliteJobResponse(
        job_id=new_job.id,
        status="QUEUED",
        message="Satellite processing job queued successfully.",
        requested_by=new_job.requested_by,
        created_at=new_job.created_at,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=SatelliteJobDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get status of satellite processing job",
)
async def get_satellite_job_status(
    job_id: str,
    db: Session = Depends(get_db),
) -> SatelliteJobDetailResponse:
    """Retrieve persisted status, progress, timestamps, and output references for a processing job. Unknown IDs return 404."""
    job = db.query(SatelliteJob).filter(SatelliteJob.id == job_id).first()
    if not job:
        raise NotFoundError(
            message=f"Satellite processing job '{job_id}' not found",
            code="JOB_NOT_FOUND",
        )

    return SatelliteJobDetailResponse(
        job_id=job.id,
        status=job.status,
        progress_percent=job.progress_percent,
        method=job.method,
        threshold=job.threshold,
        event_id=job.event_id,
        scene_id=job.scene_id,
        baseline_scene_id=job.baseline_scene_id,
        requested_by=job.requested_by,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        output_extent_id=job.output_extent_id,
        error_message=job.error_message,
        provenance=job.provenance,
    )
