"""Demonstration participant authorization and registry service.

Ensures simulation demo alerts are strictly isolated and accessible only to:
1. Authorities and Administrators (UserRole.AUTHORITY, UserRole.ADMIN)
2. Explicitly authorized demonstration participants by authenticated User ID.

SECURITY SAFEGUARD:
Email-based authorization is strictly prohibited because email ownership is not
verified during public account registration. Only explicitly configured or
registered authenticated user IDs are authorized.

Arbitrary citizens and anonymous callers are strictly forbidden from:
- Subscribing to WebSocket channel 'demo_alerts'
- Accessing demo alerts via GET /api/v1/alerts?include_demo=true
- Accessing demo alerts directly via GET /api/v1/alerts/{alert_id}
"""
import logging
from typing import Optional, Set
from app.config import get_settings
from app.models.enums import UserRole
from app.models.user import User

logger = logging.getLogger(__name__)


class DemoParticipantRegistry:
    """Registry managing explicit demonstration participants by authenticated User ID."""

    def __init__(self) -> None:
        self.registered_participant_ids: Set[str] = set()

    @property
    def configured_user_ids(self) -> Set[str]:
        settings = get_settings()
        ids = settings.demo_participant_ids
        return set(ids) if isinstance(ids, list) else set()

    def register_participant(self, user_id: str) -> bool:
        """Explicitly register an authenticated user ID as an authorized demonstration participant."""
        if not user_id:
            return False
        clean = user_id.strip()
        # Strictly prohibit email-based registration
        if "@" in clean:
            logger.warning(
                "Rejected demo participant registration for '%s': email-based authorization is forbidden. User ID required.",
                clean,
            )
            return False
        self.registered_participant_ids.add(clean)
        logger.info("Registered authorized demonstration participant user_id: %s", clean)
        return True

    def unregister_participant(self, user_id: str) -> None:
        """Remove participant user ID from registry."""
        if not user_id:
            return
        clean = user_id.strip()
        self.registered_participant_ids.discard(clean)

    def is_authorized_participant(self, user: Optional[User]) -> bool:
        """Check if user entity is an authorized demonstration participant by authenticated user ID."""
        if user is None or not user.id:
            return False
        return self.is_authorized_user_id(user.id)

    def is_authorized_user_id(self, user_id: Optional[str]) -> bool:
        """Check if authenticated user_id is authorized for demo participation."""
        if not user_id:
            return False
        clean = user_id.strip()
        return clean in self.configured_user_ids or clean in self.registered_participant_ids


demo_participant_registry = DemoParticipantRegistry()


def is_authorized_for_demo_alerts(user: Optional[User]) -> bool:
    """Verify if user is authorized to view or subscribe to demo alerts.

    Returns True ONLY for:
    - Authority or Admin users
    - Explicitly configured or registered demonstration participants by User ID

    Returns False for unrelated citizens and unauthenticated/anonymous callers.
    """
    if user is None:
        return False
    if user.role in (UserRole.AUTHORITY, UserRole.ADMIN):
        return True
    return demo_participant_registry.is_authorized_participant(user)


def is_authorized_demo_user(user_id: Optional[str], role: Optional[str] = None) -> bool:
    """Check authorization by user_id and role string (e.g. for WebSocket subscriptions)."""
    if not user_id:
        return False
    if role in (UserRole.AUTHORITY.value, UserRole.ADMIN.value):
        return True
    return demo_participant_registry.is_authorized_user_id(user_id)
