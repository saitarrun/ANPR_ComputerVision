"""Audit log model (append-only security audit trail)."""
from sqlalchemy import Column, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class AuditLog(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Immutable audit log entry."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_user_id", "user_id"),)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    ip_address = Column(String(45), nullable=True)
    details = Column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} on {self.resource_type}>"
