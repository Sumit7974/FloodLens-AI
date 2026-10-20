"""Emergency facilities, shelters, hospitals, and route hazard assessment."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.spatial import assess_route_spatial, facility_to_response_dict
from app.database import get_db
from app.models.asset import Facility
from app.schemas.facility import (
    HospitalListResponse,
    RouteAssessRequest,
    RouteAssessResponse,
    ShelterListResponse,
)

router = APIRouter(tags=["Facilities & Routes"])


@router.get(
    "/facilities/shelters",
    response_model=ShelterListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get verified and demo emergency shelter facilities",
    description="Retrieve map-ready shelter locations with GeoJSON Point coordinates, capacity, verification status, and data limitations.",
)
async def get_shelters(
    verification_status: Optional[str] = Query(
        default=None,
        description="Filter by verification state: verified, unverified, or demo_labeled",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve shelter locations with map-ready coordinates and explicit verification status."""
    query = db.query(Facility).filter(Facility.type == "shelter")
    if verification_status:
        query = query.filter(Facility.verification_status == verification_status)
    shelters = query.order_by(Facility.name.asc()).all()

    return {
        "count": len(shelters),
        "shelters": [facility_to_response_dict(s) for s in shelters],
        "data_notes": (
            "Presence in database does NOT guarantee physical safety, structural integrity, "
            "or active staffing. Emergency authorities make all operational shelter activation decisions."
        ),
    }


@router.get(
    "/facilities/hospitals",
    response_model=HospitalListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get known hospital and health post facilities",
    description="Retrieve hospital facilities with verification freshness, emergency contact info, and GeoJSON coordinates.",
)
async def get_hospitals(
    verification_status: Optional[str] = Query(
        default=None,
        description="Filter by verification state: verified, unverified, or demo_labeled",
    ),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve hospital locations with status check freshness and data limitations."""
    query = db.query(Facility).filter(Facility.type == "hospital")
    if verification_status:
        query = query.filter(Facility.verification_status == verification_status)
    hospitals = query.order_by(Facility.name.asc()).all()

    return {
        "count": len(hospitals),
        "hospitals": [facility_to_response_dict(h) for h in hospitals],
        "data_notes": (
            "Facility operational readiness, flood impact, and bed availability must be "
            "confirmed directly with public health authorities."
        ),
    }


@router.post(
    "/routes/assess",
    response_model=RouteAssessResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess candidate route against observed and predicted hazards",
    description=(
        "Performs spatial intersection screening between a candidate route LineString "
        "and active road hazards and historical observed flood extent polygons. "
        "Intended strictly for authority screening, NOT automated evacuation instructions."
    ),
)
async def assess_route(
    route_request: RouteAssessRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Evaluate path coordinates against active road hazards and flood extents."""
    result = assess_route_spatial(
        db=db,
        route_geojson=route_request.route,
        event_id=route_request.event_id,
        cutoff_time=route_request.evaluation_time,
        buffer_meters=route_request.buffer_meters,
        evaluation_context=route_request.evaluation_context,
    )
    return result
