"""Audit log archive tracking model."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Index, UniqueConstraint, func
from db.base import DeclarativeBase, IDMixin


class AuditArchive(DeclarativeBase, IDMixin):
    """Track audit log exports to S3 with tamper-detection."""

    __tablename__ = "audit_archives"
    __table_args__ = (
        UniqueConstraint("s3_key", name="uq_audit_archive_s3_key"),
        Index("ix_audit_archive_archived_at", "archived_at"),
    )

    s3_key = Column(String(512), nullable=False)
    s3_signature = Column(String(128), nullable=False)
    row_count = Column(Integer, nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    verified_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditArchive {self.s3_key} ({self.row_count} rows)>"
