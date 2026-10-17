"""Satellite job dispatch and imagery scene metadata endpoints."""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.satellite import SatelliteScene
from app.models.user import User

router = APIRouter(prefix="/satellite", tags=["Satellite & GIS"])


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start authorized satellite processing job",
)
async def create_satellite_job(
    job_spec: Dict[str, Any],
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
) -> Dict[str, Any]:
    """Enqueue satellite NDWI/MNDWI or SAR processing task."""
    return {
        "job_id": "sat_job_placeholder",
        "status": "queued",
        "message": "Satellite processing pipeline scheduled",
        "requested_by": current_user.id,
    }


@router.get(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="Get status of satellite processing job",
)
async def get_satellite_job_status(job_id: str) -> Dict[str, Any]:
    """Poll progress of a background satellite processing job."""
    return {
        "job_id": job_id,
        "status": "pending_gis_pipeline",
        "progress_percent": 0,
        "result_refs": {},
    }


@router.get(
    "/scenes",
    status_code=status.HTTP_200_OK,
    summary="List available satellite image scenes",
)
async def list_satellite_scenes(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """List stored optical and SAR scenes."""
    scenes = db.query(SatelliteScene).order_by(SatelliteScene.captured_at.desc()).all()
    return [
        {
            "id": s.id,
            "sensor": s.sensor,
            "modality": s.modality,
            "captured_at": s.captured_at,
            "cloud_quality": s.cloud_quality,
        }
        for s in scenes
    ]
