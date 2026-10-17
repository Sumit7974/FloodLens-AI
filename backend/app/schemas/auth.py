"""Authentication and user management schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.enums import UserRole


class UserRegisterRequest(BaseModel):
    """Citizen registration request payload. Authority role cannot be self-granted."""
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, description="Password minimum 8 characters")
    full_name: Optional[str] = Field(default=None, description="Citizen full name")
    phone: Optional[str] = Field(default=None, description="Optional contact phone")
    contact_consent: bool = Field(default=False, description="Consent to emergency SMS/WhatsApp notices")


class UserLoginRequest(BaseModel):
    """Login request credentials."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="Plaintext password")


class TokenResponse(BaseModel):
    """JWT Bearer token response."""
    access_token: str = Field(..., description="Signed JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in_seconds: int = Field(..., description="Token lifespan in seconds")
    user_id: str = Field(..., description="Authenticated user ID")
    role: UserRole = Field(..., description="User role: citizen, authority, or admin")


class TokenPayload(BaseModel):
    """Decoded JWT claims payload."""
    sub: str = Field(..., description="Subject user ID")
    role: str = Field(..., description="User authorization role")
    iat: Optional[int] = Field(default=None, description="Issued at timestamp")
    exp: Optional[int] = Field(default=None, description="Expiration timestamp")
    email: Optional[str] = Field(default=None, description="User email claim")


class UserResponse(BaseModel):
    """Public user response schema (excluding hashed passwords)."""
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    phone: Optional[str] = None
    contact_consent: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

