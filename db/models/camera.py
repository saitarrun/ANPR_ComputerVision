"""Camera model (video source)."""

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Camera(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Camera / video stream source."""

    __tablename__ = "cameras"
    __table_args__ = (Index("ix_cameras_region_id", "region_id"),)

    name = Column(String(255), nullable=False)
    source_type = Column(String(20), nullable=False, default="rtsp")
    url = Column(Text, nullable=True)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False)
    status = Column(String(20), nullable=False, default="inactive")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Camera {self.name} ({self.source_type})>"
