"""Analytics, model versions, and evaluation endpoints."""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.database import get_db
from app.models.enums import UserRole
from app.models.evaluation import Evaluation
from app.models.user import User

router = APIRouter(tags=["Analytics & Models"])


@router.get(
    "/analytics/events/{event_id}",
    status_code=status.HTTP_200_OK,
    summary="Get event evaluation metrics (Phase 3)",
)
async def get_event_analytics(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve forecast vs observation comparison metrics."""
    evals = db.query(Evaluation).filter(Evaluation.id == event_id).all()
    return {
        "event_id": event_id,
        "evaluations_count": len(evals),
        "results": [
            {
                "id": e.id,
                "target_type": e.target_type,
                "baseline_version": e.baseline_version,
                "metrics": e.metrics,
            }
            for e in evals
        ],
    }


@router.get(
    "/models",
    status_code=status.HTTP_200_OK,
    summary="List available AI/ML model versions and status",
)
async def list_models() -> List[Dict[str, Any]]:
    """List baseline and candidate models."""
    return [
        {
            "version": "baseline-v1",
            "type": "hydrological_baseline",
            "status": "active",
            "horizons": [1, 3, 6],
            "description": "Deterministic baseline risk estimation logic",
        }
    ]


@router.post(
    "/models/training-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start controlled candidate-training job (requires authority)",
)
async def start_training_job(
    config: Dict[str, Any],
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
) -> Dict[str, Any]:
    """Trigger offline model candidate training and benchmark."""
    return {
        "job_id": "train_job_placeholder",
        "status": "queued",
        "model_version": config.get("candidate_version", "candidate-v2"),
        "initiated_by": current_user.id,
        "message": "Candidate training initiated in sandbox",
    }
