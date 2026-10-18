"""Authority alert management: draft creation, review approval, and test dispatch."""
from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_optional_current_user, require_roles
from app.core.exceptions import FloodLensAPIException, ForbiddenError, NotFoundError
from app.database import get_db
from app.models.alert import Alert
from app.models.enums import AlertStatus, EventType, OperationalMode, UserRole
from app.models.user import User
from app.schemas.alert import AlertApprovalRequest, AlertCreateRequest, AlertDispatchRequest, AlertResponse
from app.schemas.event import WebSocketEvent
from app.services.demo_participants import is_authorized_for_demo_alerts
from app.services.push_notifications import push_adapter
from app.websocket.connection_manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def is_demo_alert(alert: Optional[Alert]) -> bool:
    """Identify if an alert is a demonstration or simulation alert.

    Checks:
    1. Title prefix: [DEMO or [TEST
    2. OperationalMode: HISTORICAL_DEMO or TEST
    """
    if not alert:
        return False
    title = (alert.title or "").strip().upper()
    if title.startswith("[DEMO") or title.startswith("[TEST"):
        return True
    if alert.mode in (OperationalMode.HISTORICAL_DEMO, OperationalMode.TEST):
        return True
    return False


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
    """Create draft alert requiring second-tier or explicit authority approval.

    Ensures test and demo alerts are visibly labelled to prevent any confusion with live warnings.
    """
    title = request.title
    if request.mode in (OperationalMode.HISTORICAL_DEMO, OperationalMode.TEST):
        if not (title.upper().startswith("[DEMO") or title.upper().startswith("[TEST")):
            title = f"[DEMO ONLY] {title}"

    new_alert = Alert(
        area_id=request.area_id,
        title=title,
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
    include_demo: bool = False,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[Alert]:
    """List accessible alerts.

    Unpublished alerts (DRAFT, APPROVED) are strictly restricted to authorized
    authorities. Citizens and unauthenticated clients can only query and view
    DISPATCHED alerts.

    ISOLATION SAFEGUARD: Demo simulation alerts (visibly labelled with [DEMO] or [TEST])
    are isolated from the public general REST feed by default. General users must
    explicitly specify include_demo=True to inspect simulation demo alerts.
    """
    is_authorized = current_user is not None and current_user.role in (UserRole.AUTHORITY, UserRole.ADMIN)

    # Deny explicit requests for unpublished drafts/approvals from non-authorities
    if status_filter in (AlertStatus.DRAFT, AlertStatus.APPROVED) and not is_authorized:
        raise ForbiddenError(
            message="Unpublished alerts (draft/approved) are restricted to authorized authorities.",
            code="UNPUBLISHED_ALERTS_RESTRICTED",
        )

    # ACCESS CONTROL SAFEGUARD:
    # include_demo=True is strictly restricted to authorities and explicitly authorized demonstration participants.
    # An arbitrary citizen query or anonymous caller requesting include_demo=True MUST be rejected.
    if include_demo and not is_authorized_for_demo_alerts(current_user):
        raise ForbiddenError(
            message="Access to demonstration alerts (?include_demo=true) is restricted to authorities and authorized demonstration participants.",
            code="DEMO_ALERTS_RESTRICTED",
        )

    query = db.query(Alert)
    if area_id:
        query = query.filter(Alert.area_id == area_id)

    if is_authorized:
        if status_filter:
            query = query.filter(Alert.status == status_filter)
    else:
        # Non-authority users are strictly limited to DISPATCHED alerts
        query = query.filter(Alert.status == AlertStatus.DISPATCHED)
        # Isolate demo simulation alerts from public REST feed unless authorized participant explicitly requested
        if not include_demo:
            query = query.filter(
                ~Alert.title.like("[DEMO%"),
                ~Alert.title.like("[TEST%"),
                ~Alert.mode.in_([OperationalMode.HISTORICAL_DEMO, OperationalMode.TEST]),
            )

    return query.order_by(Alert.created_at.desc()).all()


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Get alert by ID with authorization checks",
)
async def get_alert(
    alert_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Alert:
    """Retrieve specific alert.

    Authorization checks:
    - Unpublished alerts (DRAFT, APPROVED) require authority authorization.
    - Demonstration simulation alerts require authority authorization or authorized demonstration participant status.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert '{alert_id}' not found", code="ALERT_NOT_FOUND")

    is_authorized = current_user is not None and current_user.role in (UserRole.AUTHORITY, UserRole.ADMIN)
    if alert.status != AlertStatus.DISPATCHED and not is_authorized:
        raise ForbiddenError(
            message="Unpublished alerts (draft/approved) are restricted to authorized authorities.",
            code="UNPUBLISHED_ALERTS_RESTRICTED",
        )

    # ACCESS CONTROL SAFEGUARD:
    # Demonstration simulation alerts are restricted to authorities and authorized demonstration participants.
    # Unrelated citizens and anonymous callers are forbidden from retrieving demo alerts.
    if is_demo_alert(alert) and not is_authorized_for_demo_alerts(current_user):
        raise ForbiddenError(
            message="Demonstration simulation alerts are restricted to authorities and authorized demonstration participants.",
            code="DEMO_ALERT_RESTRICTED",
        )

    return alert


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
    """Authorize alert for test or live dispatch.

    Enforces strict state transitions: only DRAFT alerts can be approved.
    Dispatched or cancelled alerts cannot be re-approved.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert '{alert_id}' not found", code="ALERT_NOT_FOUND")

    if alert.status == AlertStatus.APPROVED:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message="Alert is already approved",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if alert.status == AlertStatus.DISPATCHED:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message="Dispatched alert cannot be re-approved",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if alert.status == AlertStatus.CANCELLED:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message="Cancelled alert cannot be approved",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
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

    # Broadcast WebSocket notification ONLY to authority channel (confidential)
    event = WebSocketEvent(
        event_id=f"evt_{alert.id}",
        type=EventType.ALERT_APPROVED.value,
        timestamp=datetime.now(timezone.utc),
        location_id=alert.area_id,
        resource_id=alert.id,
    )
    await connection_manager.broadcast_to_channel("authority_queue", event)

    return alert


@router.post(
    "/{alert_id}/dispatch",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Dispatch approved test alert",
)
async def dispatch_alert(
    alert_id: str,
    dispatch_request: Optional[AlertDispatchRequest] = None,
    current_user: User = Depends(require_roles([UserRole.AUTHORITY, UserRole.ADMIN])),
    db: Session = Depends(get_db),
) -> Alert:
    """Dispatch approved alert under test-only safeguards.

    Strict Safety Rules:
    - Alert must be in APPROVED state prior to dispatch.
    - All dispatches must be restricted to historical-demo simulations or test mode.
    - Operational disaster warnings are strictly prohibited.
    - Demo/test alerts are visibly labelled with '[DEMO / TEST ONLY]'.
    - Dispatches to push channels use sandbox testing with opted-in test devices.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise NotFoundError(message=f"Alert '{alert_id}' not found", code="ALERT_NOT_FOUND")

    if alert.status == AlertStatus.DRAFT:
        raise FloodLensAPIException(
            code="NOT_APPROVED",
            message="Alert must be in APPROVED state prior to dispatch",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if alert.status == AlertStatus.DISPATCHED:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message="Alert has already been dispatched",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if alert.status == AlertStatus.CANCELLED:
        raise FloodLensAPIException(
            code="INVALID_STATE",
            message="Cancelled alert cannot be dispatched",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if alert.status != AlertStatus.APPROVED:
        raise FloodLensAPIException(
            code="NOT_APPROVED",
            message="Alert must be in APPROVED state prior to dispatch",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Safeguard 0: Enforce simulation and prohibit operational dispatch requests
    if dispatch_request and dispatch_request.simulated is False:
        raise FloodLensAPIException(
            code="OPERATIONAL_DISPATCH_PROHIBITED",
            message="Operational dispatch is strictly prohibited. 'simulated' must be True for all test dispatches.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Safeguard 1: Restrict all dispatch to historical-demo simulations or test mode
    if alert.mode not in (OperationalMode.HISTORICAL_DEMO, OperationalMode.TEST):
        raise FloodLensAPIException(
            code="DISPATCH_RESTRICTED_TO_TEST",
            message="All dispatch is strictly restricted to historical-demo simulations or test mode. Operational disaster warnings are prohibited.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Safeguard 2: Ensure demo/test alerts are visibly labelled
    if not (alert.title.upper().startswith("[DEMO") or alert.title.upper().startswith("[TEST")):
        alert.title = f"[DEMO / TEST ONLY] {alert.title}"
    if not ("DEMO" in alert.message.upper() or "TEST" in alert.message.upper()):
        alert.message = f"[HISTORICAL DEMO / TEST SIMULATION] {alert.message}"

    # Safeguard 3: Safe push notification sandbox dispatch for opted-in test devices
    if dispatch_request and dispatch_request.target_device_tokens:
        push_adapter.send_test_alert(
            tokens=dispatch_request.target_device_tokens,
            title=alert.title,
            message=alert.message,
            metadata={"alert_id": alert.id, "area_id": alert.area_id, "mode": alert.mode.value},
            is_opted_in=True,
        )

    now = datetime.now(timezone.utc)
    alert.status = AlertStatus.DISPATCHED
    alert.issued_at = now
    db.commit()
    db.refresh(alert)

    # Broadcast WebSocket notification:
    # ISOLATION SAFEGUARD: Demo simulation alerts are strictly broadcast to 'demo_alerts'
    # and 'authority_queue', keeping them isolated from general-user channels ('alerts' and 'public').
    event = WebSocketEvent(
        event_id=f"evt_dispatch_{alert.id}",
        type=EventType.ALERT_PUBLISHED.value,
        timestamp=now,
        location_id=alert.area_id,
        resource_id=alert.id,
        metadata={
            "title": alert.title,
            "mode": alert.mode.value,
            "is_test": True,
            "simulation": True,
            "simulated_only": True,
        },
    )
    target_channel = "demo_alerts" if alert.mode in (OperationalMode.HISTORICAL_DEMO, OperationalMode.TEST) else "alerts"
    await connection_manager.broadcast_to_channel(target_channel, event)
    await connection_manager.broadcast_to_channel("authority_queue", event)

    return alert
