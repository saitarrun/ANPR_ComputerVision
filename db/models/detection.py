"""Detection model (single frame detection event)."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Detection(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """A single plate detection in a frame."""

    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_plate_id", "plate_id"),
        Index("ix_detections_camera_id", "camera_id"),
    )

    camera_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=False)
    plate_id = Column(UUID(as_uuid=True), ForeignKey("plates.id"), nullable=False)
    frame_timestamp = Column(DateTime(timezone=True), nullable=False)
    confidence = Column(Float, nullable=False)
    bbox = Column(JSONB, nullable=True)
    ocr_backend = Column(String(50), nullable=True)
    quality_score = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Detection {self.id} conf={self.confidence}>"
