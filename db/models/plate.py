"""Plate model."""
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Plate(DeclarativeBase, IDMixin, TimestampMixin):
    """Detected license plate (deduplicated)."""

    __tablename__ = "plates"
    __table_args__ = (
        UniqueConstraint("plate_string", "region_id", name="uq_plate_region"),
    )

    plate_string = Column(String(255), nullable=False, index=True)  # Encrypted in DB
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False)
    detection_count = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    avg_confidence = Column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<Plate {self.plate_string[-6:]} ({self.detection_count} detections)>"
