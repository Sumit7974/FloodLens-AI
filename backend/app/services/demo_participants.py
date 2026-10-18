"""Demonstration participant authorization and registry service.

Ensures simulation demo alerts are strictly isolated and accessible only to:
1. Authorities and Administrators (UserRole.AUTHORITY, UserRole.ADMIN)
2. Explicitly authorized demonstration participants (configured allowlist or verified registry)

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
    """Registry managing explicit demonstration participants."""

    def __init__(self) -> None:
        self.registered_participant_ids: Set[str] = set()
        self.registered_participant_emails: Set[str] = set()

    @property
    def configured_user_ids(self) -> Set[str]:
        settings = get_settings()
        ids = settings.demo_participant_ids
        return set(ids) if isinstance(ids, list) else set()

    @property
    def configured_emails(self) -> Set[str]:
        settings = get_settings()
        emails = settings.demo_participant_emails
        return {e.lower().strip() for e in emails} if isinstance(emails, list) else set()

    def register_participant(self, user_id_or_email: str) -> bool:
        """Explicitly register a user ID or email as an authorized demonstration participant."""
        if not user_id_or_email:
            return False
        clean = user_id_or_email.strip()
        if "@" in clean:
            self.registered_participant_emails.add(clean.lower())
        else:
            self.registered_participant_ids.add(clean)
        logger.info("Registered authorized demonstration participant: %s", clean)
        return True

    def unregister_participant(self, user_id_or_email: str) -> None:
        """Remove participant from registry."""
        if not user_id_or_email:
            return
        clean = user_id_or_email.strip()
        if "@" in clean:
            self.registered_participant_emails.discard(clean.lower())
        else:
            self.registered_participant_ids.discard(clean)

    def is_authorized_participant(self, user: Optional[User]) -> bool:
        """Check if user entity is an explicitly authorized demonstration participant."""
        if user is None:
            return False
        # Match by ID
        if user.id in self.configured_user_ids or user.id in self.registered_participant_ids:
            return True
        # Match by email
        if user.email:
            email_lower = user.email.strip().lower()
            if email_lower in self.configured_emails or email_lower in self.registered_participant_emails:
                return True
        return False

    def is_authorized_email(self, email: Optional[str]) -> bool:
        """Check if email is an authorized demonstration participant."""
        if not email:
            return False
        clean = email.strip().lower()
        return clean in self.configured_emails or clean in self.registered_participant_emails

    def is_authorized_user_id(self, user_id: Optional[str]) -> bool:
        """Check if user_id is an authorized demonstration participant."""
        if not user_id:
            return False
        return user_id in self.configured_user_ids or user_id in self.registered_participant_ids


demo_participant_registry = DemoParticipantRegistry()


def is_authorized_for_demo_alerts(user: Optional[User]) -> bool:
    """Verify if user is authorized to view or subscribe to demo alerts.

    Returns True ONLY for:
    - Authority or Admin users
    - Explicitly authorized demonstration participants

    Returns False for unrelated citizens and unauthenticated/anonymous callers.
    """
    if user is None:
        return False
    if user.role in (UserRole.AUTHORITY, UserRole.ADMIN):
        return True
    return demo_participant_registry.is_authorized_participant(user)


def is_authorized_demo_user(user_id: Optional[str], email: Optional[str] = None, role: Optional[str] = None) -> bool:
    """Check authorization by user_id, email, and role string (e.g. for WebSocket subscriptions)."""
    if not user_id:
        return False
    if role in (UserRole.AUTHORITY.value, UserRole.ADMIN.value):
        return True
    if demo_participant_registry.is_authorized_user_id(user_id):
        return True
    if email and demo_participant_registry.is_authorized_email(email):
        return True
    return False
