"""FastAPI dependencies: database session, authentication, and role authorization."""
from typing import Callable, List, Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> dict:
    """Validate Bearer token and return its decoded payload."""
    if not credentials or not credentials.credentials:
        raise UnauthorizedError(message="Bearer token required", code="UNAUTHORIZED")

    try:
        payload = decode_access_token(credentials.credentials)
        return payload
    except Exception as exc:
        raise UnauthorizedError(message="Invalid or expired access token", code="INVALID_TOKEN")


async def get_current_user(
    payload: dict = Depends(get_current_user_token_payload),
    db: Session = Depends(get_db),
) -> User:
    """Retrieve currently authenticated user from database."""
    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError(message="Token subject missing", code="INVALID_TOKEN")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError(message="Authenticated user record not found", code="USER_NOT_FOUND")

    if not user.is_active:
        raise ForbiddenError(message="User account is inactive", code="ACCOUNT_INACTIVE")

    return user


def require_roles(allowed_roles: List[UserRole]) -> Callable:
    """Dependency factory checking that the current user possesses one of the allowed roles."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(
                message=f"Access restricted to roles: {[r.value for r in allowed_roles]}",
                code="INSUFFICIENT_ROLE",
            )
        return current_user

    return role_checker
