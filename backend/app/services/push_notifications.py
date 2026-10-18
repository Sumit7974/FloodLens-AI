"""Push notification adapter for test-only sandboxes (Expo / FCM).

Strict Safety Constraints:
- Dispatches are SIMULATED_ONLY. No real external Expo or FCM requests are executed.
- Dispatches are strictly restricted to verified test-device registrations or configured dummy tokens.
- Never send to arbitrary device tokens or assume opt-in without verification.
- Device tokens and credentials are masked in all logs and receipts (never logged raw).
"""
from datetime import datetime, timezone
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Token syntax patterns
EXPO_TOKEN_PATTERN = re.compile(r"^ExponentPushToken\[[A-Za-z0-9_\-\+]{10,}\]$|^[A-Za-z0-9_\-]{20,}$")
FCM_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_\-:\.]{30,}$")


class DeliveryStatus(str, Enum):
    """Delivery status outcomes for simulated test push dispatches."""
    SIMULATED_ONLY = "simulated_only"
    DELIVERED_SANDBOX = "simulated_only"  # Canonical value: simulated_only
    INVALID_TOKEN = "invalid_token"
    UNREGISTERED_DEVICE = "unregistered_device"
    OPT_OUT_SKIPPED = "opt_out_skipped"
    FAILED = "failed"


def mask_device_token(token: str) -> str:
    """Mask push token to prevent leaking credentials in logs or responses."""
    if not token or not isinstance(token, str):
        return "***"
    token = token.strip()
    if token.startswith("ExponentPushToken[") and token.endswith("]"):
        inner = token[18:-1]
        masked_inner = f"***{inner[-4:]}" if len(inner) >= 4 else "***"
        return f"ExponentPushToken[{masked_inner}]"
    if len(token) > 8:
        return f"{token[:4]}***{token[-4:]}"
    return "***"


class PushNotificationPayload(BaseModel):
    """Payload for mobile push notification dispatch."""
    title: str = Field(..., max_length=255)
    body: str = Field(...)
    data: Optional[Dict[str, Any]] = Field(default=None)
    priority: str = Field(default="high")


class PushDeliveryReceipt(BaseModel):
    """Receipt summarizing delivery outcome for a single device token.

    Unambiguously marks delivery as SIMULATED_ONLY to ensure no real push delivery is assumed.
    """
    token_masked: str
    status: DeliveryStatus
    provider: str = "expo"
    is_sandbox: bool = True
    simulated_only: bool = True
    receipt_id: Optional[str] = None
    delivery_note: str = "SIMULATED_ONLY: Prototype environment. No real external Expo or FCM network dispatch occurred."
    error: Optional[str] = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Configured dummy tokens for prototype sandbox testing
DEFAULT_CONFIGURED_DUMMY_TOKENS: Set[str] = {
    "ExponentPushToken[demo_test_device_sandbox_01]",
    "ExponentPushToken[mobile_test_device_token_01]",
    "ExponentPushToken[valid_token_test_12345]",
}


class SandboxPushNotificationAdapter:
    """Safe push notification adapter for Expo and FCM sandbox simulation."""

    def __init__(self, default_provider: str = "expo") -> None:
        self.default_provider = default_provider
        # Explicitly configured dummy tokens for prototype sandbox testing
        self.configured_dummy_tokens: Set[str] = set(DEFAULT_CONFIGURED_DUMMY_TOKENS)
        # Genuinely registered opted-in test devices
        self.registered_test_devices: Set[str] = set()

    def register_test_device(self, token: str) -> bool:
        """Explicitly register a genuinely opted-in test device token."""
        if token and self.validate_token_syntax(token):
            self.registered_test_devices.add(token.strip())
            return True
        return False

    def validate_token_syntax(self, token: str) -> bool:
        """Validate format of Expo or FCM device push token."""
        if not token or not isinstance(token, str):
            return False
        clean = token.strip()
        return bool(EXPO_TOKEN_PATTERN.match(clean) or FCM_TOKEN_PATTERN.match(clean))

    def is_verified_test_token(self, token: str) -> bool:
        """Verify device token is an explicitly configured dummy token or genuinely registered test device.

        SAFETY ENFORCEMENT: Never infer consent from token text.
        """
        if not token:
            return False
        clean = token.strip()
        return clean in self.configured_dummy_tokens or clean in self.registered_test_devices

    def detect_provider(self, token: str) -> str:
        """Identify push provider from token structure."""
        if token.startswith("ExponentPushToken["):
            return "expo"
        if ":" in token or len(token) > 60:
            return "fcm"
        return self.default_provider

    def send_push_notification(
        self,
        tokens: List[str],
        payload: PushNotificationPayload,
        is_opted_in: bool = True,
    ) -> List[PushDeliveryReceipt]:
        """Dispatch test push notifications to target tokens under strict SIMULATED_ONLY constraints.

        Args:
            tokens: List of mobile device push tokens.
            payload: Notification headline, body, and metadata dictionary.
            is_opted_in: Indicates explicit consent for test/sandbox dispatch.

        Returns:
            List of PushDeliveryReceipts with honest SIMULATED_ONLY delivery statuses and masked tokens.
        """
        receipts: List[PushDeliveryReceipt] = []

        # Safeguard 1: Do not assume opt-in without explicit flag
        if not is_opted_in:
            logger.warning("Push simulation skipped: recipient has not opted in for test dispatch.")
            for token in tokens:
                receipts.append(
                    PushDeliveryReceipt(
                        token_masked=mask_device_token(token),
                        status=DeliveryStatus.OPT_OUT_SKIPPED,
                        provider=self.detect_provider(token),
                        is_sandbox=True,
                        simulated_only=True,
                        error="Recipient has not explicitly opted into test sandbox alerts.",
                    )
                )
            return receipts

        for raw_token in tokens:
            masked = mask_device_token(raw_token)
            provider = self.detect_provider(raw_token)

            # Safeguard 2: Format validation
            if not self.validate_token_syntax(raw_token):
                logger.warning("Invalid push token format: %s (provider=%s)", masked, provider)
                receipts.append(
                    PushDeliveryReceipt(
                        token_masked=masked,
                        status=DeliveryStatus.INVALID_TOKEN,
                        provider=provider,
                        is_sandbox=True,
                        simulated_only=True,
                        error="Malformed or unrecognized device push token format.",
                    )
                )
                continue

            # Safeguard 3: Restrict to verified test-device registrations (never send to arbitrary tokens)
            if not self.is_verified_test_token(raw_token):
                logger.warning(
                    "Push rejected for unverified token: %s. Arbitrary device push dispatch prohibited in prototype.",
                    masked,
                )
                receipts.append(
                    PushDeliveryReceipt(
                        token_masked=masked,
                        status=DeliveryStatus.UNREGISTERED_DEVICE,
                        provider=provider,
                        is_sandbox=True,
                        simulated_only=True,
                        error="Device token is not a verified registered test device: neither an explicitly configured dummy token nor a genuinely registered test device. Consent is never inferred from token text.",
                    )
                )
                continue

            # Safeguard 4: Honest SIMULATED_ONLY delivery recording
            receipt_id = f"rcpt_sim_{uuid4().hex[:12]}"
            logger.info(
                "SIMULATED_ONLY push notification recorded for token %s (provider=%s, receipt=%s). "
                "No real external Expo/FCM delivery occurred.",
                masked,
                provider,
                receipt_id,
            )
            receipts.append(
                PushDeliveryReceipt(
                    token_masked=masked,
                    status=DeliveryStatus.SIMULATED_ONLY,
                    provider=provider,
                    is_sandbox=True,
                    simulated_only=True,
                    receipt_id=receipt_id,
                    delivery_note="SIMULATED_ONLY: Prototype environment. No real external Expo or FCM network dispatch occurred.",
                )
            )

        return receipts

    def send_test_alert(
        self,
        tokens: List[str],
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        is_opted_in: bool = True,
    ) -> List[PushDeliveryReceipt]:
        """Convenience method for simulating a test emergency alert."""
        payload = PushNotificationPayload(
            title=title,
            body=message,
            data=metadata or {},
            priority="high",
        )
        return self.send_push_notification(tokens=tokens, payload=payload, is_opted_in=is_opted_in)


# Singleton adapter instance
push_adapter = SandboxPushNotificationAdapter()
