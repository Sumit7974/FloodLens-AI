"""Analytics, model versions, and evaluation endpoints."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.core.exceptions import FloodLensAPIException, NotFoundError
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
    description="Lists baseline demonstration models and offline research prototypes with explicit status and limitations.",
)
async def list_models() -> List[Dict[str, Any]]:
    """List baseline and research models without claiming unverified active deployment or candidate availability."""
    return [
        {
            "version": "baseline-v1",
            "type": "demo_prototype",
            "status": "demo_ready",
            "horizons": [1, 3, 6],
            "description": "Demonstration pipeline baseline model trained on synthetic historical data for pipeline testing and software integration verification.",
            "limitations": [
                "PIPELINE TEST ONLY: Model trained on synthetic demonstration data.",
                "Metrics reflect software pipeline functionality and code correctness, NOT real-world operational flood prediction accuracy.",
                "Do NOT use for real-world operational flood warnings.",
            ],
        },
        {
            "version": "era5-v1",
            "type": "offline_benchmark",
            "status": "offline_research",
            "horizons": [1, 3, 6],
            "description": "Research benchmark model trained on open-access ERA5 reanalysis precipitation and GloFAS discharge proxy data.",
            "limitations": [
                "RESEARCH PROTOTYPE: Offline model trained on ERA5 reanalysis and GloFAS proxies; not validated against in-situ Nepal DHM gauge observations.",
                "River stage telemetry was unavailable during training; uses proxy discharge approximations.",
                "Do NOT use for real-world operational flood warnings.",
            ],
        },
    ]


@router.post(
    "/models/training-jobs",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Trigger candidate-training job (Not Implemented)",
    description="Returns 501 Not Implemented because model training is executed offline via research scripts. No online background training executor is configured.",
)
async def start_training_job(
    config: Dict[str, Any],
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
) -> Dict[str, Any]:
    """Reject online training job requests truthfully with 501 Not Implemented."""
    raise FloodLensAPIException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        code="TRAINING_NOT_IMPLEMENTED",
        message="Automated online model training is not implemented: model training is executed offline in research scripts and notebooks. No online background training executor is configured.",
        details={
            "execution_environment": "offline_research_only",
            "available_models": ["baseline-v1", "era5-v1"],
            "requested_config": config,
            "documentation": "Training workflows are managed offline via ml/src/train_models.py",
        },
    )
