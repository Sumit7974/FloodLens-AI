"""Schemas for Emergency Facilities (shelters, hospitals) and Route Hazard Assessment."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FacilityResponseItem(BaseModel):
    """Map-ready facility representation preserving legacy fields and adding geospatial metadata."""
    id: str = Field(..., description="Unique facility identifier")
    type: str = Field(..., description="Facility category: shelter or hospital")
    name: str = Field(..., description="Facility official or operational name")
    verification_status: str = Field(
        ...,
        description="Verification state: verified, unverified, or demo_labeled",
    )
    capacity: Optional[int] = Field(default=None, description="Known operational capacity (beds/people), null if unrecorded")
    contact_info: Optional[str] = Field(default=None, description="Authorized public contact number or liaison info")
    status_checked_at: Optional[datetime] = Field(default=None, description="Timestamp of latest verification check")
    location: Optional[Dict[str, Any]] = Field(
        default=None,
        description="RFC 7946 GeoJSON Point geometry dict in EPSG:4326 [longitude, latitude]",
    )
    longitude: Optional[float] = Field(default=None, description="WGS84 longitude coordinate")
    latitude: Optional[float] = Field(default=None, description="WGS84 latitude coordinate")
    source: Optional[str] = Field(default=None, description="Provenance or data source if known")
    details: Dict[str, Any] = Field(default_factory=dict, description="Operational metadata and attributes")
    limitations: List[str] = Field(
        default_factory=list,
        description="Explicit caveats, unverified warnings, or coordinate absence notices",
    )

    model_config = ConfigDict(from_attributes=True)


class ShelterListResponse(BaseModel):
    """Enriched shelter listing response preserving legacy 'count' and 'shelters' fields."""
    count: int = Field(..., description="Total shelters returned")
    shelters: List[FacilityResponseItem] = Field(..., description="List of shelter facilities")
    data_notes: Optional[str] = Field(
        default="Presence in database does not imply guaranteed flood safety; consult local authorities.",
        description="System disclaimer for decision support",
    )


class HospitalListResponse(BaseModel):
    """Enriched hospital listing response preserving legacy 'count' and 'hospitals' fields."""
    count: int = Field(..., description="Total hospitals returned")
    hospitals: List[FacilityResponseItem] = Field(..., description="List of hospital facilities")
    data_notes: Optional[str] = Field(
        default="Facility readiness and bed availability require direct verification with health authorities.",
        description="System disclaimer for decision support",
    )


class RouteAssessRequest(BaseModel):
    """Candidate route hazard assessment request."""
    route: Dict[str, Any] = Field(
        ...,
        description="GeoJSON LineString geometry or Feature containing LineString in EPSG:4326",
    )
    event_id: Optional[str] = Field(
        default=None,
        description="Optional historical flood event ID to evaluate against satellite flood extent polygons",
    )
    evaluation_time: Optional[datetime] = Field(
        default=None,
        description="Observation cutoff timestamp; hazards observed after this time are excluded from historical screening",
    )
    buffer_meters: float = Field(
        default=25.0,
        ge=0.0,
        le=5000.0,
        description="Proximity buffer in meters around candidate route line for hazard detection",
    )
    evaluation_context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Contextual metadata (e.g. screening agency, mission objective)",
    )

    @field_validator("route")
    @classmethod
    def validate_route_geojson(cls, v: Any) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("Route must be a valid GeoJSON object (dictionary)")

        geom = v
        if v.get("type") == "Feature":
            geom = v.get("geometry")
            if not isinstance(geom, dict):
                raise ValueError("GeoJSON Feature must contain a valid geometry object")

        geom_type = geom.get("type")
        if geom_type != "LineString":
            raise ValueError(f"Route geometry type must be 'LineString', received '{geom_type}'")

        coords = geom.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 2:
            raise ValueError("Route LineString must contain at least 2 coordinate pairs [longitude, latitude]")

        if len(coords) > 10000:
            raise ValueError("Route contains too many vertices (maximum 10,000 coordinate pairs)")

        for idx, pt in enumerate(coords):
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                raise ValueError(f"Vertex at index {idx} is invalid; expected [longitude, latitude]")
            lon, lat = pt[0], pt[1]
            if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                raise ValueError(f"Coordinates at vertex {idx} must be numeric")
            if not (-180.0 <= lon <= 180.0):
                raise ValueError(f"Longitude at vertex {idx} ({lon}) is outside valid range [-180, 180]")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude at vertex {idx} ({lat}) is outside valid range [-90, 90]")

        return v


class RouteHazardIntersection(BaseModel):
    """Specific hazard intersecting or in close proximity to candidate route."""
    hazard_id: str = Field(..., description="Identifier of the intersecting hazard or flood extent")
    hazard_type: str = Field(..., description="Hazard type (submerged, debris, bridge_closed, observed_flood_extent)")
    source_layer: str = Field(..., description="Source table/layer: road_hazard or flood_extent")
    status: str = Field(..., description="Hazard operational status (active, cleared, unverified)")
    observed_at: datetime = Field(..., description="UTC timestamp when hazard was observed")
    source: Optional[str] = Field(default=None, description="Sensor, satellite, or authority reporting source")
    confidence: Optional[float] = Field(default=None, description="Confidence score if available (0.0 to 1.0)")
    intersection_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Geographic details of intersection (e.g. approximate location, proximity distance)",
    )
    notes: Optional[str] = Field(default=None, description="Operational notes or limitations")


class RouteAssessResponse(BaseModel):
    """Evidence-based candidate route hazard screening evaluation response."""
    route_status: Literal["conditional", "hazards_detected", "no_known_hazards_detected", "not_evaluated", "incomplete_data"] = Field(
        ...,
        description="Overall route status summary for decision-support display",
    )
    assessment_status: Literal["HAZARDS_INTERSECTED", "NO_KNOWN_INTERSECTIONS", "NOT_EVALUATED", "INCOMPLETE_DATA"] = Field(
        ...,
        description="Structured assessment category",
    )
    hazards_detected: List[RouteHazardIntersection] = Field(
        default_factory=list,
        description="List of detected hazard intersections along candidate route",
    )
    event_id: Optional[str] = Field(default=None, description="Historical event ID evaluated against if provided")
    evaluation_time: datetime = Field(..., description="UTC timestamp of evaluation execution")
    cutoff_time_applied: Optional[datetime] = Field(default=None, description="Observation cutoff timestamp applied to screening")
    total_hazards_screened: int = Field(default=0, description="Total active hazards and flood extent layers screened")
    hazards_intersected_count: int = Field(default=0, description="Total hazard intersections identified")
    limitations: List[str] = Field(
        default_factory=list,
        description="System boundary and safety disclaimers",
    )
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Spatial screening engine and dataset provenance",
    )
