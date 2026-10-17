"""Automated tests for authentication, authorization, and password security."""
from fastapi import status
from fastapi.testclient import TestClient
from app.core.security import hash_password, verify_password


def test_password_hashing():
    """Verify bcrypt password hashing and verification behavior."""
    secret = "NepalFloodPrep2026!"
    hashed = hash_password(secret)
    assert hashed != secret
    assert verify_password(secret, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_citizen_registration_flow(client: TestClient):
    """Verify citizen registration creates account and assigns citizen role."""
    reg_payload = {
        "email": "newcitizen@example.com",
        "password": "SecurePassword123!",
        "full_name": "Hari Bahadur",
        "phone": "+977-9800000000",
        "contact_consent": True,
    }
    response = client.post("/api/v1/auth/register", json=reg_payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == "newcitizen@example.com"
    assert data["role"] == "citizen"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data

    # Test duplicate registration rejection
    dup_response = client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_response.status_code == status.HTTP_409_CONFLICT
    err = dup_response.json()
    assert err["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_login_flow(client: TestClient, test_citizen_user):
    """Verify login with valid and invalid credentials."""
    # Valid login
    login_payload = {
        "email": test_citizen_user.email,
        "password": "citizenpassword123",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_200_OK
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["role"] == "citizen"

    # Invalid login
    bad_payload = {
        "email": test_citizen_user.email,
        "password": "IncorrectPassword!",
    }
    bad_response = client.post("/api/v1/auth/login", json=bad_payload)
    assert bad_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert bad_response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_auth_me_endpoint(client: TestClient, citizen_token: str):
    """Verify /auth/me returns authenticated user details when token is valid."""
    headers = {"Authorization": f"Bearer {citizen_token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "citizen@example.com"
    assert data["role"] == "citizen"


def test_unauthenticated_access_denied(client: TestClient):
    """Verify protected endpoints reject requests without token using standard error format."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    err = response.json()
    assert "error" in err
    assert err["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in err["error"]
