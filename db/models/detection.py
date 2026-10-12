"""Detection model (single frame detection event)."""

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import synonym
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
    stream_id = Column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    frame_timestamp = Column(DateTime(timezone=True), nullable=False)
    confidence = Column(Float, nullable=False)
    bbox = Column(JSONB, nullable=True)
    # Alias kept for callers that use the longer name
    bounding_box = synonym("bbox")
    ocr_backend = Column(String(50), nullable=True)
    quality_score = Column(Float, nullable=True)
    crop_url = Column(String(1024), nullable=True)
    frame_url = Column(String(1024), nullable=True)
    tracking_id = Column(String(100), nullable=True)
    is_persisted = Column(String(1), nullable=False, default="Y")

    def __repr__(self) -> str:
        return f"<Detection {self.id} conf={self.confidence}>"
