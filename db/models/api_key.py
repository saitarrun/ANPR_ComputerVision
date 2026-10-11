"""API key model (machine credentials)."""
from sqlalchemy import Column, String, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class APIKey(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Hashed API key bound to a user."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_user_id", "user_id"),)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    permissions = Column(Text, nullable=False, default="")

    def __repr__(self) -> str:
        return f"<APIKey {self.id} user={self.user_id}>"
