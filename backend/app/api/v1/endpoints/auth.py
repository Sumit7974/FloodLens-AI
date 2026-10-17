"""Authentication routes: registration, login, token refresh, and identity inspection."""
from datetime import timedelta
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_current_user_token_payload
from app.config import get_settings
from app.core.exceptions import ConflictError, FloodLensAPIException, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new citizen account",
    description="Registers a citizen user. Authority and Admin roles cannot be self-granted.",
)
async def register(request: UserRegisterRequest, db: Session = Depends(get_db)) -> User:
    """Citizen self-registration endpoint."""
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise FloodLensAPIException(
            code="EMAIL_ALREADY_EXISTS",
            message="A user with this email address already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    new_user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        phone=request.phone,
        contact_consent=request.contact_consent,
        role=UserRole.CITIZEN,  # Enforce citizen role only
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User login with email and password",
)
async def login(request: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate credentials and issue JWT bearer token."""
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise UnauthorizedError(
            message="Invalid email or password credentials.",
            code="INVALID_CREDENTIALS",
        )

    if not user.is_active:
        raise FloodLensAPIException(
            code="ACCOUNT_INACTIVE",
            message="User account is deactivated.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        expires_delta=expires_delta,
        claims={"email": user.email},
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_seconds=settings.access_token_expire_minutes * 60,
        user_id=user.id,
        role=user.role,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
)
async def refresh_token(payload: dict = Depends(get_current_user_token_payload), db: Session = Depends(get_db)) -> TokenResponse:
    """Issue a fresh access token for an active user session."""
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise UnauthorizedError(message="User not found or inactive", code="USER_INACTIVE")

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    new_token = create_access_token(
        subject=user.id,
        role=user.role.value,
        expires_delta=expires_delta,
        claims={"email": user.email},
    )

    return TokenResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in_seconds=settings.access_token_expire_minutes * 60,
        user_id=user.id,
        role=user.role,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authorized profile",
)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return currently authenticated user identity and role."""
    return current_user
