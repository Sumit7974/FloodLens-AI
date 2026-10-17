"""Predictions and risk forecast endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.exceptions import DataUnavailableError, NotFoundError
from app.database import get_db
from app.models.forecast import ForecastRun, RiskPrediction
from app.schemas.forecast import ForecastResponse, HorizonRisk

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.get(
    "/latest",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest risk forecast for a location",
    description="Returns the most recent multi-horizon risk prediction (+1h, +3h, +6h) for the given location.",
)
async def get_latest_forecast(
    location_id: str = Query(..., description="Target location / settlement ID"),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Retrieve latest forecast run and horizons for a location."""
    # Find latest prediction for this location
    latest_pred = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.location_id == location_id)
        .order_by(RiskPrediction.valid_at.desc())
        .first()
    )

    if not latest_pred:
        raise DataUnavailableError(
            message=f"No forecast records currently available for location '{location_id}'",
            code="FORECAST_UNAVAILABLE",
        )

    forecast_run = latest_pred.forecast_run
    all_horizons = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.forecast_run_id == forecast_run.id, RiskPrediction.location_id == location_id)
        .order_by(RiskPrediction.horizon_hours.asc())
        .all()
    )

    horizons_data = [
        HorizonRisk(
            hours=h.horizon_hours,
            risk_level=h.risk_level.value if hasattr(h.risk_level, "value") else str(h.risk_level),
            calibrated_probability=h.calibrated_probability,
        )
        for h in all_horizons
    ]

    return ForecastResponse(
        forecast_id=forecast_run.id,
        location_id=location_id,
        issued_at=forecast_run.issued_at,
        mode=forecast_run.mode.value if hasattr(forecast_run.mode, "value") else str(forecast_run.mode),
        model_version=forecast_run.model_version,
        data_quality=all_horizons[0].data_quality.value if all_horizons else "partial",
        horizons=horizons_data,
        limitations=forecast_run.limitations or [],
    )


@router.get(
    "/locations/{location_id}",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Get forecast for a specific location",
)
async def get_location_forecast(location_id: str, db: Session = Depends(get_db)) -> ForecastResponse:
    """Alias for latest forecast query by path parameter."""
    return await get_latest_forecast(location_id=location_id, db=db)


@router.get(
    "/map",
    status_code=status.HTTP_200_OK,
    summary="Get published risk-zone map layer descriptor",
)
async def get_prediction_map_layer() -> dict:
    """Return map layer metadata for spatial overlays."""
    return {
        "layer_type": "risk_zones",
        "description": "Multi-horizon predicted flood risk zones",
        "crs": "EPSG:4326",
        "active_horizons": [1, 3, 6],
        "status": "ready",
    }
