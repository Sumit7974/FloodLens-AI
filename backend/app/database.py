"""Database session and connection management with PostgreSQL and PostGIS support."""
import logging
import time
from typing import Any, Dict, Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Engine creation based on dialect
if settings.is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=settings.debug,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> Dict[str, Any]:
    """Check database connectivity and PostGIS extension status.

    Returns a status dict containing connectivity state, latency, and PostGIS version if available.
    """
    start_time = time.time()
    result = {
        "connected": False,
        "database_type": "sqlite" if settings.is_sqlite else "postgresql",
        "postgis_installed": False,
        "postgis_version": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            result["connected"] = True
            result["latency_ms"] = round((time.time() - start_time) * 1000, 2)

            # Check PostGIS extension if PostgreSQL
            if not settings.is_sqlite:
                try:
                    version_row = connection.execute(text("SELECT PostGIS_Version();")).fetchone()
                    if version_row:
                        result["postgis_installed"] = True
                        result["postgis_version"] = str(version_row[0])
                except Exception as pg_err:
                    logger.warning("PostGIS extension check failed: %s", str(pg_err))
                    result["postgis_installed"] = False
                    result["postgis_version"] = None

    except Exception as exc:
        logger.error("Database connection check failed: %s", str(exc))
        result["connected"] = False
        result["error"] = str(exc)

    return result
