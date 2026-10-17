"""Base model utilities, timestamp mixins, and geospatial type decorators."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Text
from sqlalchemy.types import TypeDecorator


def generate_uuid() -> str:
    """Generate a UUID4 hex string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Mixin adding standard created_at and updated_at UTC timestamps."""
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class GeometryType(TypeDecorator):
    """PostGIS Geometry column on PostgreSQL; Text/WKT fallback on SQLite."""
    impl = Text
    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.geometry_type = geometry_type
        self.srid = srid

    def load_dialect_impl(self, dialect):
        if dialect is not None and getattr(dialect, "name", None) == "postgresql":
            from geoalchemy2 import Geometry
            return dialect.type_descriptor(Geometry(geometry_type=self.geometry_type, srid=self.srid))
        return dialect.type_descriptor(Text()) if dialect is not None else Text()

