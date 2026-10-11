"""Watchlist model (plate patterns of interest)."""
from sqlalchemy import Column, String, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Watchlist(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Watched plate pattern within a region."""

    __tablename__ = "watchlist"
    __table_args__ = (Index("ix_watchlist_region_id", "region_id"),)

    plate_pattern = Column(String(255), nullable=False)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_active = Column(String(1), nullable=False, default="Y")

    def __repr__(self) -> str:
        return f"<Watchlist {self.plate_pattern}>"
