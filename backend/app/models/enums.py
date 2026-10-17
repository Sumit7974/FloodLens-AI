"""Core Enumerations matching FloodLens AI architectural contracts."""
import enum


class UserRole(str, enum.Enum):
    """User authorization roles."""
    CITIZEN = "citizen"
    AUTHORITY = "authority"
    ADMIN = "admin"


class OperationalMode(str, enum.Enum):
    """Operational mode for data, forecasts, and events."""
    HISTORICAL_DEMO = "historical_demo"
    TEST = "test"
    LIVE_OBSERVATION = "live_observation"
    MODEL_ESTIMATE = "model_estimate"


class RiskLevel(str, enum.Enum):
    """Risk severity levels."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DataQuality(str, enum.Enum):
    """Data quality and confidence indicators."""
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class AlertStatus(str, enum.Enum):
    """Alert review and lifecycle states."""
    DRAFT = "draft"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class AssistanceCategory(str, enum.Enum):
    """Citizen assistance request categories."""
    EVACUATION = "evacuation"
    MEDICAL = "medical"
    FOOD_WATER = "food_water"
    SHELTER = "shelter"
    OTHER = "other"


class AssistanceStatus(str, enum.Enum):
    """Status tracking for assistance requests."""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class EventType(str, enum.Enum):
    """Real-time WebSocket event types as defined in contract."""
    RISK_UPDATED = "risk.updated"
    SENSOR_UPDATED = "sensor.updated"
    FLOOD_EXTENT_UPDATED = "flood_extent.updated"
    ALERT_APPROVED = "alert.approved"
    ALERT_PUBLISHED = "alert.published"
    ASSISTANCE_CREATED = "assistance.created"
    ASSISTANCE_UPDATED = "assistance.updated"
    PROCESSING_COMPLETED = "processing.completed"
