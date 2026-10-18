"""Predictions and risk forecast endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import DataUnavailableError, NotFoundError
from app.core.spatial import geometry_to_geojson
from app.database import get_db
from app.models.enums import DataQuality, EventType, OperationalMode, RiskLevel, UserRole
from app.models.forecast import ForecastRun, RiskPrediction
from app.models.location import Location
from app.models.user import User
from app.schemas.event import WebSocketEvent
from app.schemas.forecast import (
    ForecastIngestRequest,
    ForecastResponse,
    HorizonRisk,
    PredictionMapResponse,
)
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post(
    "/ingest",
    response_model=ForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest multi-horizon risk forecast",
    description="Ingests +1h, +3h, and +6h risk predictions from AI/ML forecasting pipelines. Restricted to authority/admin.",
)
async def ingest_forecast(
    request: ForecastIngestRequest,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Store multi-horizon forecast run and risk predictions in database and notify clients."""
    # Ensure target location exists in database
    loc = db.query(Location).filter(Location.id == request.location_id).first()
    if not loc:
        # Create an auto-registered location entry so spatial foreign key constraint holds
        loc = Location(
            id=request.location_id,
            name=f"Location {request.location_id}",
            admin_level=4,
            crs_source="EPSG:4326",
            metadata_json={"auto_registered": True},
        )
        db.add(loc)
        db.flush()

    forecast_run_id = request.forecast_id or f"fc_run_{uuid.uuid4().hex[:10]}"

    # Check if this forecast_run_id already exists; reuse or create
    forecast_run = db.query(ForecastRun).filter(ForecastRun.id == forecast_run_id).first()
    if not forecast_run:
        forecast_run = ForecastRun(
            id=forecast_run_id,
            event_id=request.event_id,
            issued_at=request.issued_at,
            model_version=request.model_version,
            input_data_cutoff_at=request.input_data_cutoff_at,
            mode=request.mode,
            status="completed",
            limitations=request.limitations,
        )
        db.add(forecast_run)
        db.flush()

    # Map input string risk level to enum
    risk_level_map = {
        "low": RiskLevel.LOW,
        "moderate": RiskLevel.MODERATE,
        "high": RiskLevel.HIGH,
        "critical": RiskLevel.CRITICAL,
    }

    horizons_response: List[HorizonRisk] = []

    for h_in in request.horizons:
        r_level = risk_level_map.get(h_in.risk_level.lower(), RiskLevel.MODERATE)
        v_at = h_in.valid_at or (request.issued_at + timedelta(hours=h_in.hours))

        d_quality = request.data_quality
        if h_in.data_quality:
            try:
                d_quality = DataQuality[h_in.data_quality.upper()]
            except KeyError:
                pass

        pred = RiskPrediction(
            id=f"pred_{uuid.uuid4().hex[:10]}",
            forecast_run_id=forecast_run.id,
            location_id=request.location_id,
            valid_at=v_at,
            horizon_hours=h_in.hours,
            risk_level=r_level,
            calibrated_probability=h_in.calibrated_probability,
            geometry_ref=h_in.geometry_ref,
            data_quality=d_quality,
        )
        db.add(pred)

        horizons_response.append(
            HorizonRisk(
                hours=h_in.hours,
                risk_level=r_level.value,
                calibrated_probability=h_in.calibrated_probability,
            )
        )

    db.commit()

    # Publish real-time WebSocket event
    ws_event = WebSocketEvent(
        event_id=f"evt_pred_{forecast_run.id}",
        type=EventType.RISK_UPDATED.value,
        timestamp=datetime.now(timezone.utc),
        location_id=request.location_id,
        resource_id=forecast_run.id,
    )
    await connection_manager.broadcast(ws_event)

    # Sort horizons for clean response
    horizons_response.sort(key=lambda x: x.hours)

    return ForecastResponse(
        forecast_id=forecast_run.id,
        location_id=request.location_id,
        issued_at=forecast_run.issued_at,
        mode=forecast_run.mode.value if hasattr(forecast_run.mode, "value") else str(forecast_run.mode),
        model_version=forecast_run.model_version,
        data_quality=request.data_quality.value if hasattr(request.data_quality, "value") else str(request.data_quality),
        horizons=horizons_response,
        limitations=forecast_run.limitations or [],
    )


@router.post(
    "/forecasts",
    response_model=ForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest multi-horizon risk forecast (alias)",
    include_in_schema=False,
)
async def ingest_forecast_alias(
    request: ForecastIngestRequest,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Alias for /predictions/ingest to support alternative client conventions."""
    return await ingest_forecast(request=request, current_user=current_user, db=db)


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
    """Retrieve latest forecast run and horizons for a location, selected by newest issued_at timestamp."""
    latest_run = (
        db.query(ForecastRun)
        .join(RiskPrediction, RiskPrediction.forecast_run_id == ForecastRun.id)
        .filter(RiskPrediction.location_id == location_id)
        .order_by(ForecastRun.issued_at.desc(), ForecastRun.created_at.desc())
        .first()
    )

    if not latest_run:
        raise DataUnavailableError(
            message=f"No forecast records currently available for location '{location_id}'",
            code="FORECAST_UNAVAILABLE",
        )

    all_horizons = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.forecast_run_id == latest_run.id, RiskPrediction.location_id == location_id)
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
        forecast_id=latest_run.id,
        location_id=location_id,
        issued_at=latest_run.issued_at,
        mode=latest_run.mode.value if hasattr(latest_run.mode, "value") else str(latest_run.mode),
        model_version=latest_run.model_version,
        data_quality=all_horizons[0].data_quality.value if all_horizons else "partial",
        horizons=horizons_data,
        limitations=latest_run.limitations or [],
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
    response_model=PredictionMapResponse,
    status_code=status.HTTP_200_OK,
    summary="Get published risk-zone map layer descriptor and features",
    description="Returns database-backed GeoJSON risk zones with +1h/+3h/+6h horizons across active locations.",
)
async def get_prediction_map_layer(db: Session = Depends(get_db)) -> PredictionMapResponse:
    """Query database for active risk zones and synthesize a real GeoJSON feature collection."""
    # Find the most recently issued ForecastRun
    latest_run = db.query(ForecastRun).order_by(ForecastRun.issued_at.desc()).first()

    if not latest_run:
        return PredictionMapResponse(
            layer_id="risk_zones_none",
            layer_type="risk_zones",
            description="Multi-horizon predicted flood risk zones",
            crs="EPSG:4326",
            active_horizons=[1, 3, 6],
            issued_at=None,
            model_version=None,
            mode=None,
            data_quality="unavailable",
            status="no_data",
            total_zones=0,
            features=[],
        )

    # Fetch all predictions associated with this run
    predictions = (
        db.query(RiskPrediction)
        .filter(RiskPrediction.forecast_run_id == latest_run.id)
        .order_by(RiskPrediction.location_id, RiskPrediction.horizon_hours.asc())
        .all()
    )

    if not predictions:
        return PredictionMapResponse(
            layer_id=f"risk_zones_{latest_run.id}",
            layer_type="risk_zones",
            description="Multi-horizon predicted flood risk zones",
            crs="EPSG:4326",
            active_horizons=[1, 3, 6],
            issued_at=latest_run.issued_at,
            model_version=latest_run.model_version,
            mode=latest_run.mode.value if hasattr(latest_run.mode, "value") else str(latest_run.mode),
            data_quality="unavailable",
            status="no_data",
            total_zones=0,
            features=[],
        )

    # Group predictions by location_id
    by_loc: Dict[str, List[RiskPrediction]] = {}
    for p in predictions:
        by_loc.setdefault(p.location_id, []).append(p)

    features: List[Dict[str, Any]] = []
    data_quality_val = predictions[0].data_quality.value if hasattr(predictions[0].data_quality, "value") else str(predictions[0].data_quality)

    for loc_id, preds in by_loc.items():
        loc = db.query(Location).filter(Location.id == loc_id).first()
        loc_name = loc.name if loc else f"Location {loc_id}"
        admin_level = loc.admin_level if loc else 4
        loc_geometry = geometry_to_geojson(loc.geometry) if loc else None

        horizons_dict: Dict[str, Any] = {}
        max_severity = "LOW"
        severity_order = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}

        for p in preds:
            h_key = f"+{p.horizon_hours}h"
            r_val = p.risk_level.value if hasattr(p.risk_level, "value") else str(p.risk_level)
            horizons_dict[h_key] = {
                "risk_level": r_val.lower(),
                "calibrated_probability": p.calibrated_probability,
            }
            if severity_order.get(r_val.upper(), 1) > severity_order.get(max_severity.upper(), 1):
                max_severity = r_val

        feature = {
            "type": "Feature",
            "id": loc_id,
            "properties": {
                "location_id": loc_id,
                "location_name": loc_name,
                "admin_level": admin_level,
                "forecast_id": latest_run.id,
                "model_version": latest_run.model_version,
                "mode": latest_run.mode.value if hasattr(latest_run.mode, "value") else str(latest_run.mode),
                "data_quality": preds[0].data_quality.value if hasattr(preds[0].data_quality, "value") else str(preds[0].data_quality),
                "horizons": horizons_dict,
                "max_risk_level": max_severity.lower(),
            },
            "geometry": loc_geometry,
        }
        features.append(feature)

    return PredictionMapResponse(
        layer_id=f"risk_zones_{latest_run.id}",
        layer_type="risk_zones",
        description="Multi-horizon predicted flood risk zones",
        crs="EPSG:4326",
        active_horizons=[1, 3, 6],
        issued_at=latest_run.issued_at,
        model_version=latest_run.model_version,
        mode=latest_run.mode.value if hasattr(latest_run.mode, "value") else str(latest_run.mode),
        data_quality=data_quality_val.lower(),
        status="active",
        total_zones=len(features),
        features=features,
    )
