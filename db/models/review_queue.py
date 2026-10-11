"""Review queue model (detections awaiting human review)."""

from sqlalchemy import Column, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class ReviewQueue(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Detection queued for manual review."""

    __tablename__ = "review_queue"
    __table_args__ = (Index("ix_review_queue_status", "status"),)

    detection_id = Column(UUID(as_uuid=True), ForeignKey("detections.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    detection_blob = Column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return f"<ReviewQueue {self.id} ({self.status})>"
