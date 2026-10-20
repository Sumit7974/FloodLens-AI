"""Analytics, model versions, and evaluation endpoints."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.enums import UserRole
from app.models.evaluation import Evaluation
from app.models.flood_event import FloodEvent
from app.models.user import User
from app.schemas.analytics import EventAnalyticsResponse, ModelVersionItem

router = APIRouter(tags=["Analytics & Models"])


@router.get(
    "/analytics/events/{event_id}",
    response_model=EventAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get event evaluation metrics (Phase 3)",
    description="Retrieve forecast vs observation comparison metrics scoped to a specific flood event.",
)
async def get_event_analytics(event_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve forecast vs observation comparison metrics for an existing flood event."""
    event = db.query(FloodEvent).filter(FloodEvent.id == event_id).first()
    if not event:
        raise NotFoundError(message=f"Flood event '{event_id}' not found", code="EVENT_NOT_FOUND")

    evals = db.query(Evaluation).filter(Evaluation.event_id == event_id).order_by(Evaluation.created_at.desc()).all()

    if len(evals) == 0:
        status_str = "no_evaluations_recorded"
        limitations = [
            f"No comparative model evaluation benchmarks have been recorded for event '{event_id}'.",
            "Evaluations require synchronized satellite observation extents and issued forecasts.",
        ]
    else:
        status_str = "evaluations_available"
        limitations = [
            "Evaluation metrics reflect benchmark comparison between model predictions and reference observations.",
            "Performance metrics should not be extrapolated outside the validated historical study area.",
        ]

    return {
        "event_id": event.id,
        "event_name": event.name,
        "mode": event.mode.value if hasattr(event.mode, "value") else str(event.mode),
        "evaluations_count": len(evals),
        "status": status_str,
        "data_limitations": limitations,
        "results": [
            {
                "id": e.id,
                "event_id": e.event_id,
                "target_type": e.target_type,
                "baseline_version": e.baseline_version,
                "candidate_version": e.candidate_version,
                "metrics": e.metrics if isinstance(e.metrics, dict) else {},
                "reference_id": e.reference_id,
                "notes": e.notes,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
            }
            for e in evals
        ],
    }


@router.get(
    "/models",
    response_model=List[ModelVersionItem],
    status_code=status.HTTP_200_OK,
    summary="List available AI/ML model versions and status",
    description="Lists baseline operational models and offline research candidates with explicit deployment status.",
)
async def list_models() -> List[Dict[str, Any]]:
    """List baseline and candidate models without claiming unverified active deployment."""
    return [
        {
            "version": "baseline-v1",
            "type": "hydrological_baseline",
            "status": "active",
            "horizons": [1, 3, 6],
            "description": "Deterministic rule-based hydrological risk baseline used for historical simulation and benchmarks",
            "limitations": [
                "Calibrated on historical Nepal Terai river gauge observations and runoff thresholds",
                "Does not simulate hydrodynamic 2D overland flow velocity or micro-topography",
            ],
        },
        {
            "version": "candidate-v2",
            "type": "research_candidate",
            "status": "research_prototype",
            "horizons": [1, 3, 6],
            "description": "Offline experimental candidate model for retrospective comparative benchmarking",
            "limitations": [
                "Offline research prototype only; not promoted to operational authority warning workflow",
                "Requires continuous upstream telemetry without sensor dropouts",
            ],
        },
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
