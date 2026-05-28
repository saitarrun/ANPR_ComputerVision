"""User-Stream access grant model (multi-tenant RBAC)."""
from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase, IDMixin


class UserStream(DeclarativeBase, IDMixin):
    """Grant user access to a specific camera."""

    __tablename__ = "user_streams"
    __table_args__ = (
        UniqueConstraint("user_id", "camera_id", name="uq_user_camera"),
        Index("ix_user_stream_user_id", "user_id"),
        Index("ix_user_stream_camera_id", "camera_id"),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String(20), nullable=False, default="read")
    granted_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<UserStream user_id={self.user_id} camera_id={self.camera_id} perm={self.permission}>"
