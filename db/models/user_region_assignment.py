"""User-region assignment model (multi-tenant access grant)."""

from sqlalchemy import Column, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase


class UserRegionAssignment(DeclarativeBase):  # type: ignore[misc]
    """Grant a user a role within a region."""

    __tablename__ = "user_region_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "region_id", name="uq_user_region"),
        Index("ix_user_region_user_id", "user_id"),
        Index("ix_user_region_region_id", "region_id"),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), primary_key=True)
    role = Column(String(20), nullable=False, default="viewer")

    def __repr__(self) -> str:
        return (
            f"<UserRegionAssignment user={self.user_id} region={self.region_id} role={self.role}>"
        )
