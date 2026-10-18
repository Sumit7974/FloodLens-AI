"""Push notification adapter for test-only sandboxes (Expo / FCM).

Strict Safety Constraints:
- Dispatches are strictly restricted to opted-in test devices and sandbox simulations.
- Never issue operational disaster warnings.
- Device tokens and credentials are masked in all logs and audit outputs.
"""
from datetime import datetime, timezone
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Token patterns
EXPO_TOKEN_PATTERN = re.compile(r"^ExponentPushToken\[[A-Za-z0-9_\-\+]{10,}\]$|^[A-Za-z0-9_\-]{20,}$")
FCM_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_\-:\.]{30,}$")


class DeliveryStatus(str, Enum):
    """Delivery status outcomes for sandbox/test push dispatches."""
    DELIVERED_SANDBOX = "delivered_sandbox"
    DELIVERED = "delivered"
    INVALID_TOKEN = "invalid_token"
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
    """Receipt summarizing delivery outcome for a single device token."""
    token_masked: str
    status: DeliveryStatus
    provider: str = "expo"
    is_sandbox: bool = True
    receipt_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SandboxPushNotificationAdapter:
    """Safe push notification adapter for Expo and FCM sandbox testing."""

    def __init__(self, default_provider: str = "expo") -> None:
        self.default_provider = default_provider

    def validate_token(self, token: str) -> bool:
        """Validate format of Expo or FCM device push token."""
        if not token or not isinstance(token, str):
            return False
        clean = token.strip()
        return bool(EXPO_TOKEN_PATTERN.match(clean) or FCM_TOKEN_PATTERN.match(clean))

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
        """Dispatch test push notifications to target tokens under sandbox constraints.

        Args:
            tokens: List of mobile device push tokens.
            payload: Notification headline, body, and metadata dictionary.
            is_opted_in: Must be True; indicates explicit consent for test/sandbox dispatch.

        Returns:
            List of PushDeliveryReceipts with honest delivery statuses and masked tokens.
        """
        receipts: List[PushDeliveryReceipt] = []

        if not is_opted_in:
            logger.warning("Push dispatch rejected: Device recipient has not explicitly opted into test dispatch.")
            for token in tokens:
                receipts.append(
                    PushDeliveryReceipt(
                        token_masked=mask_device_token(token),
                        status=DeliveryStatus.OPT_OUT_SKIPPED,
                        provider=self.detect_provider(token),
                        is_sandbox=True,
                        error="Recipient has not explicitly opted into test sandbox alerts.",
                    )
                )
            return receipts

        for raw_token in tokens:
            masked = mask_device_token(raw_token)
            provider = self.detect_provider(raw_token)

            # 1. Format validation
            if not self.validate_token(raw_token):
                logger.warning("Invalid push token format: %s (provider=%s)", masked, provider)
                receipts.append(
                    PushDeliveryReceipt(
                        token_masked=masked,
                        status=DeliveryStatus.INVALID_TOKEN,
                        provider=provider,
                        is_sandbox=True,
                        error="Malformed or unrecognized device push token format.",
                    )
                )
                continue

            # 2. Honest Sandbox Delivery Simulation
            # In sandbox/demo environments, record successful simulated dispatch
            receipt_id = f"rcpt_sbx_{uuid4().hex[:12]}"
            logger.info(
                "Delivered test sandbox push notification to %s (provider=%s, receipt=%s)",
                masked,
                provider,
                receipt_id,
            )
            receipts.append(
                PushDeliveryReceipt(
                    token_masked=masked,
                    status=DeliveryStatus.DELIVERED_SANDBOX,
                    provider=provider,
                    is_sandbox=True,
                    receipt_id=receipt_id,
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
        """Convenience method for dispatching a test emergency alert."""
        payload = PushNotificationPayload(
            title=title,
            body=message,
            data=metadata or {},
            priority="high",
        )
        return self.send_push_notification(tokens=tokens, payload=payload, is_opted_in=is_opted_in)


# Singleton adapter instance
push_adapter = SandboxPushNotificationAdapter()
