"""User model (identity)."""
from enum import Enum
from sqlalchemy import Column, String, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates
from db.base import DeclarativeBase, IDMixin, TimestampMixin

_VALID_ROLES = frozenset({"viewer", "operator", "admin"})


class User(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Application user with RBAC role."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
    )

    email = Column(String(255), nullable=False)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    is_active = Column(String(1), nullable=False, default="Y")

    @validates("role")
    def validate_role(self, key: str, value: object) -> str:
        """Accept a UserRole enum member or its value; reject anything else."""
        role = value.value if isinstance(value, Enum) else str(value)
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role: {value!r}")
        return str(role)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
