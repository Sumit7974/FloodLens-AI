"""Authority alert management: draft creation, review approval, and test dispatch."""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.core.exceptions import FloodLensAPIException, NotFoundError
from app.database import get_db
from app.models.alert import Alert
from app.models.enums import AlertStatus, EventType, UserRole
from app.models.user import User
from app.schemas.alert import AlertApprovalRequest, AlertCreateRequest, AlertResponse
from app.schemas.event import WebSocketEvent
from app.websocket.connection_manager import connection_manager

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft alert for authority review",
)
async def create_alert_draft(
    request: AlertCreateRequest,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> Alert:
    """Create draft alert requiring second-tier or explicit authority approval."""
    new_alert = Alert(
        area_id=request.area_id,
        title=request.title,
        message=request.message,
        status=AlertStatus.DRAFT,
        created_by=current_user.id,
        mode=request.mode,
        target_channels=request.target_channels,
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    return new_alert


@router.get(
    "",
    response_model=List[AlertResponse],
    status_code=status.HTTP_200_OK,
    summary="List accessible alerts",
)
async def list_alerts(
    area_id: Optional[str] = None,
    status_filter: Optional[AlertStatus] = None,
    db: Session = Depends(get_db),
) -> List[Alert]:
    """List published or draft alerts."""
    query = db.query(Alert)
    if area_id:
        query = query.filter(Alert.area_id == area_id)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    return query.order_by(Alert.created_at.desc()).all()


@router.post(
    "/{alert_id}/approve",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a draft alert",
)
async def approve_alert(
    alert_id: str,
    approval: AlertApprovalRequest,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> Alert:
    """Authorize alert for test or live dispatch."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert '{alert_id}' not found", code="ALERT_NOT_FOUND")

    if alert.status != AlertStatus.DRAFT:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message=f"Only DRAFT alerts can be approved. Current status: {alert.status.value}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    alert.status = AlertStatus.APPROVED
    alert.approved_by = current_user.id
    db.commit()
    db.refresh(alert)

    # Broadcast WebSocket notification: alert.approved
    event = WebSocketEvent(
        event_id=f"evt_{alert.id}",
        type=EventType.ALERT_APPROVED.value,
        timestamp=datetime.now(timezone.utc),
        location_id=alert.area_id,
        resource_id=alert.id,
    )
    await connection_manager.broadcast_to_channel("alerts", event)

    return alert


@router.post(
    "/{alert_id}/dispatch",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch approved test alert",
)
async def dispatch_alert(
    alert_id: str,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> Alert:
    """Dispatch approved alert to target test subscribers."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert '{alert_id}' not found", code="ALERT_NOT_FOUND")

    if alert.status != AlertStatus.APPROVED:
        raise FloodLensAPIException(
            code="NOT_APPROVED",
            message="Alert must be in APPROVED state prior to dispatch",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    now = datetime.now(timezone.utc)
    alert.status = AlertStatus.DISPATCHED
    alert.issued_at = now
    db.commit()
    db.refresh(alert)

    # Broadcast WebSocket notification: alert.published
    event = WebSocketEvent(
        event_id=f"evt_dispatch_{alert.id}",
        type=EventType.ALERT_PUBLISHED.value,
        timestamp=now,
        location_id=alert.area_id,
        resource_id=alert.id,
    )
    await connection_manager.broadcast_to_channel("alerts", event)

    return alert
