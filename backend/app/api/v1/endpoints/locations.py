"""Location, administrative boundary, and settlement management endpoints."""
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.core.spatial import geometry_to_geojson, to_wkt_element
from app.database import get_db
from app.models.enums import UserRole
from app.models.location import Location
from app.models.user import User
from app.schemas.location import LocationCreate, LocationResponse

router = APIRouter(prefix="/locations", tags=["Locations & Settlements"])


@router.post(
    "",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a location or settlement boundary",
    description="Registers an administrative boundary, settlement polygon, or village point. Authorized only.",
)
async def create_location(
    loc_in: LocationCreate,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> LocationResponse:
    """Create a new spatial location record."""
    loc_id = loc_in.id or f"loc_{uuid.uuid4().hex[:10]}"

    existing = db.query(Location).filter(Location.id == loc_id).first()
    if existing:
        raise ConflictError(message=f"Location with id '{loc_id}' already exists", code="LOCATION_ALREADY_EXISTS")

    geom_elem = None
    if loc_in.geometry:
        # Accept point or polygon/multipolygon
        geom_elem = to_wkt_element(loc_in.geometry, expected_type=None, srid=4326)

    new_loc = Location(
        id=loc_id,
        name=loc_in.name,
        admin_level=loc_in.admin_level,
        parent_id=loc_in.parent_id,
        geometry=geom_elem,
        crs_source=loc_in.crs_source,
        metadata_json=loc_in.metadata_json,
    )
    db.add(new_loc)
    db.commit()
    db.refresh(new_loc)

    return LocationResponse(
        id=new_loc.id,
        name=new_loc.name,
        admin_level=new_loc.admin_level,
        parent_id=new_loc.parent_id,
        geometry=geometry_to_geojson(new_loc.geometry),
        crs_source=new_loc.crs_source,
        metadata_json=new_loc.metadata_json,
        created_at=new_loc.created_at,
    )


@router.get(
    "",
    response_model=List[LocationResponse],
    status_code=status.HTTP_200_OK,
    summary="List locations and settlements",
    description="List mapped locations, administrative boundaries, and settlements.",
)
async def list_locations(
    admin_level: Optional[int] = Query(None, description="Filter by administrative level (1=Prov, 2=Dist, 3=Muni, 4=Settlement)"),
    parent_id: Optional[str] = Query(None, description="Filter by parent location ID"),
    db: Session = Depends(get_db),
) -> List[LocationResponse]:
    """Retrieve locations with GeoJSON geometry representations."""
    query = db.query(Location)
    if admin_level is not None:
        query = query.filter(Location.admin_level == admin_level)
    if parent_id is not None:
        query = query.filter(Location.parent_id == parent_id)

    locations = query.order_by(Location.admin_level.asc(), Location.name.asc()).all()
    return [
        LocationResponse(
            id=loc.id,
            name=loc.name,
            admin_level=loc.admin_level,
            parent_id=loc.parent_id,
            geometry=geometry_to_geojson(loc.geometry),
            crs_source=loc.crs_source,
            metadata_json=loc.metadata_json,
            created_at=loc.created_at,
        )
        for loc in locations
    ]


@router.get(
    "/{location_id}",
    response_model=LocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get location details by ID",
)
async def get_location(location_id: str, db: Session = Depends(get_db)) -> LocationResponse:
    """Retrieve details and geometry for a specific location."""
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise NotFoundError(message=f"Location '{location_id}' not found", code="LOCATION_NOT_FOUND")

    return LocationResponse(
        id=loc.id,
        name=loc.name,
        admin_level=loc.admin_level,
        parent_id=loc.parent_id,
        geometry=geometry_to_geojson(loc.geometry),
        crs_source=loc.crs_source,
        metadata_json=loc.metadata_json,
        created_at=loc.created_at,
    )
