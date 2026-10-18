"""Citizen assistance requests and authority response queue."""
from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.exceptions import ForbiddenError, NotFoundError
from app.database import get_db
from app.models.assistance import AssistanceRequest
from app.models.enums import AssistanceStatus, EventType, UserRole
from app.models.user import User
from app.schemas.assistance import AssistanceCreateRequest, AssistanceResponse, AssistanceUpdateRequest
from app.schemas.event import WebSocketEvent
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistance", tags=["Assistance"])


@router.post(
    "",
    response_model=AssistanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit citizen assistance request",
)
async def create_assistance_request(
    request: AssistanceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistanceRequest:
    """Submit emergency help request. Sensitive coordinates restricted to authorized responders."""
    req = AssistanceRequest(
        citizen_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
        category=request.category,
        details=request.details,
        people_count=request.people_count,
        status=AssistanceStatus.PENDING,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Publish notification exclusively to authority responder channel.
    # PRIVACY SAFEGUARD: Never broadcast raw coordinates, personal details, or citizen IDs publicly.
    event = WebSocketEvent(
        event_id=f"evt_req_{req.id}",
        type=EventType.ASSISTANCE_CREATED.value,
        timestamp=datetime.now(timezone.utc),
        resource_id=req.id,
        metadata={"category": req.category.value, "people_count": req.people_count},
    )
    await connection_manager.broadcast_to_channel("authority_queue", event)

    return req


@router.get(
    "/mine",
    response_model=List[AssistanceResponse],
    status_code=status.HTTP_200_OK,
    summary="Get authenticated citizen's own submitted requests",
)
async def get_my_assistance_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[AssistanceRequest]:
    """Retrieve personal request history. Citizens can strictly view only their own requests."""
    return (
        db.query(AssistanceRequest)
        .filter(AssistanceRequest.citizen_id == current_user.id)
        .order_by(AssistanceRequest.created_at.desc())
        .all()
    )


@router.get(
    "/{request_id}",
    response_model=AssistanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single assistance request by ID with ownership verification",
)
async def get_assistance_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssistanceRequest:
    """Retrieve specific assistance request.

    Citizens can strictly access only their own requests.
    Authorities and admins can view any request in the response queue.
    """
    req = db.query(AssistanceRequest).filter(AssistanceRequest.id == request_id).first()
    if not req:
        raise NotFoundError(message=f"Assistance request '{request_id}' not found", code="REQUEST_NOT_FOUND")

    is_authority = current_user.role in (UserRole.AUTHORITY, UserRole.ADMIN)
    if not is_authority and req.citizen_id != current_user.id:
        raise ForbiddenError(
            message="Citizens may only access their own assistance requests.",
            code="FORBIDDEN_REQUEST_ACCESS",
        )

    return req


@router.get(
    "",
    response_model=List[AssistanceResponse],
    status_code=status.HTTP_200_OK,
    summary="Authority responder queue",
)
async def get_assistance_queue(
    status_filter: Optional[AssistanceStatus] = None,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> List[AssistanceRequest]:
    """Authorized responders list pending or ongoing assistance requests."""
    query = db.query(AssistanceRequest)
    if status_filter:
        query = query.filter(AssistanceRequest.status == status_filter)
    return query.order_by(AssistanceRequest.created_at.asc()).all()


@router.patch(
    "/{request_id}",
    response_model=AssistanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update assistance request assignment and status",
)
async def update_assistance_status(
    request_id: str,
    update: AssistanceUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> AssistanceRequest:
    """Update status, assign responder, and record resolution notes.

    Emits authenticated, user-specific WebSocket notification to citizen's private channel
    and notifies responder queue without exposing personal data publicly.
    """
    req = db.query(AssistanceRequest).filter(AssistanceRequest.id == request_id).first()
    if not req:
        raise NotFoundError(message=f"Assistance request '{request_id}' not found", code="REQUEST_NOT_FOUND")

    setattr(req, "status", update.status)
    if update.assigned_to is not None:
        setattr(req, "assigned_to", update.assigned_to)
    if update.status_notes is not None:
        setattr(req, "status_notes", update.status_notes)

    db.commit()
    db.refresh(req)

    now = datetime.now(timezone.utc)

    # 1. User-specific private notification to the citizen
    citizen_event = WebSocketEvent(
        event_id=f"evt_update_user_{req.id}_{int(now.timestamp())}",
        type=EventType.ASSISTANCE_UPDATED.value,
        timestamp=now,
        resource_id=req.id,
        metadata={
            "status": req.status.value,
            "status_notes": req.status_notes,
            "assigned_to": req.assigned_to,
        },
    )
    await connection_manager.broadcast_to_channel(f"user:{req.citizen_id}", citizen_event)

    # 2. Operational notification to authority responder queue
    auth_event = WebSocketEvent(
        event_id=f"evt_update_auth_{req.id}_{int(now.timestamp())}",
        type=EventType.ASSISTANCE_UPDATED.value,
        timestamp=now,
        resource_id=req.id,
        metadata={
            "new_status": req.status.value,
            "assigned_to": req.assigned_to,
        },
    )
    await connection_manager.broadcast_to_channel("authority_queue", auth_event)

    return req
