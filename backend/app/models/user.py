"""User database model supporting role-based access control."""
from sqlalchemy import Boolean, Column, Enum, String
from app.database import Base
from app.models.base import TimestampMixin, generate_uuid
from app.models.enums import UserRole


class User(Base, TimestampMixin):
    """User account entity for Citizens, Authorities, and Administrators."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(
        Enum(UserRole, values_callable=lambda obj: [e.value for e in obj], name="userrole"),
        default=UserRole.CITIZEN,
        nullable=False,
        index=True,
    )
    phone = Column(String(50), nullable=True)
    contact_consent = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
