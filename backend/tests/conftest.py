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
os.environ["DATABASE_URL"] = "sqlite:///./test_floodlens.db"
os.environ["JWT_SECRET"] = "test-secret-key-32-chars-minimum-length-floodlens"

from app.config import get_settings
from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import create_application
from app.models.enums import UserRole
from app.models.user import User

# Test in-memory SQLite engine
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all database tables before test suite executes."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide transactional database session that rolls back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


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
