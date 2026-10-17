"""Pytest fixtures for FloodLens AI backend test suite."""
import os
import sys
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-chars-minimum-length-floodlens")

# Dynamically select PostgreSQL if DATABASE_URL or TEST_DATABASE_URL is provided, else fallback to SQLite in-memory
CONFIGURED_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
if CONFIGURED_DB_URL and ("postgresql" in CONFIGURED_DB_URL or "postgres" in CONFIGURED_DB_URL):
    TEST_DB_URL = CONFIGURED_DB_URL
    os.environ["DATABASE_URL"] = TEST_DB_URL
    from sqlalchemy import create_engine, text
    test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
else:
    TEST_DB_URL = "sqlite:///:memory:"
    os.environ["DATABASE_URL"] = TEST_DB_URL
    from sqlalchemy import create_engine, text
    test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import create_application
from app.models.enums import UserRole
from app.models.user import User

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all database tables and extensions before test suite executes."""
    if "postgresql" in str(test_engine.url):
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)



@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide transactional database session that rolls back after each test."""
    from sqlalchemy import event

    connection = test_engine.connect()
    transaction = connection.begin()
    nested = [connection.begin_nested()]
    session = TestingSessionLocal(bind=connection)

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if not connection.closed and not nested[0].is_active:
            nested[0] = connection.begin_nested()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()




@pytest.fixture
def is_postgres() -> bool:
    """True if tests are executing against live PostgreSQL/PostGIS database."""
    return "postgresql" in str(test_engine.url)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:

    """TestClient configured with overridden get_db dependency."""
    app = create_application()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_citizen_user(db_session: Session) -> User:
    """Fixture creating a verified citizen user."""
    user = User(
        email="citizen@example.com",
        hashed_password=hash_password("citizenpassword123"),
        full_name="Citizen Tester",
        role=UserRole.CITIZEN,
        contact_consent=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_authority_user(db_session: Session) -> User:
    """Fixture creating an authorized responder user."""
    user = User(
        email="authority@floodlens.org",
        hashed_password=hash_password("authoritysecure456"),
        full_name="Authority Commander",
        role=UserRole.AUTHORITY,
        contact_consent=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def citizen_token(test_citizen_user: User) -> str:
    """Valid JWT token for citizen user."""
    return create_access_token(subject=test_citizen_user.id, role=test_citizen_user.role.value)


@pytest.fixture
def authority_token(test_authority_user: User) -> str:
    """Valid JWT token for authority user."""
    return create_access_token(subject=test_authority_user.id, role=test_authority_user.role.value)
