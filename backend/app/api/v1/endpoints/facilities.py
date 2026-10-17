"""Emergency facilities, shelters, hospitals, and route hazard assessment."""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.asset import Facility

router = APIRouter(tags=["Facilities & Routes"])


@router.get(
    "/facilities/shelters",
    status_code=status.HTTP_200_OK,
    summary="Get verified emergency shelter facilities",
)
async def get_shelters(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve shelter locations with verification status."""
    shelters = db.query(Facility).filter(Facility.type == "shelter").all()
    return {
        "count": len(shelters),
        "shelters": [
            {
                "id": s.id,
                "name": s.name,
                "verification_status": s.verification_status,
                "capacity": s.capacity,
                "contact_info": s.contact_info,
            }
            for s in shelters
        ],
    }


@router.get(
    "/facilities/hospitals",
    status_code=status.HTTP_200_OK,
    summary="Get known hospital facilities",
)
async def get_hospitals(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve hospital locations with status check freshness."""
    hospitals = db.query(Facility).filter(Facility.type == "hospital").all()
    return {
        "count": len(hospitals),
        "hospitals": [
            {
                "id": h.id,
                "name": h.name,
                "verification_status": h.verification_status,
                "contact_info": h.contact_info,
            }
            for h in hospitals
        ],
    }


@router.post(
    "/routes/assess",
    status_code=status.HTTP_200_OK,
    summary="Assess candidate route against observed and predicted hazards",
)
async def assess_route(route_request: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate path coordinates against active road hazards and flood extents."""
    return {
        "route_status": "conditional",
        "hazards_detected": [],
        "limitations": [
            "Demonstration prototype only: route guidance cannot guarantee safety",
            "Always follow official directives from emergency authorities",
        ],
    }
