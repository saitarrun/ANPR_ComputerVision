"""Watchlist model (plate patterns of interest)."""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Watchlist(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Watched plate pattern within a region."""

    __tablename__ = "watchlist"
    __table_args__ = (Index("ix_watchlist_region_id", "region_id"),)

    plate_pattern = Column(String(255), nullable=False)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=True)
    # Subject that created the entry. Stored as text because API tokens may
    # carry non-UUID subjects (e.g. service accounts); UUID subjects are
    # stored in their canonical string form.
    created_by_user_id = Column(String(100), nullable=False)
    is_active = Column(String(1), nullable=False, default="Y")
    reason = Column(String(512), nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    alert_enabled = Column(String(1), nullable=False, default="Y")
    alert_channel = Column(String(50), nullable=True)
    dedup_window = Column(Integer, nullable=False, default=300)
    last_hit = Column(DateTime(timezone=True), nullable=True)
    match_count = Column(Integer, nullable=False, default=0)

    @validates("created_by_user_id")
    def _coerce_created_by(self, key: str, value: object) -> object:
        """Normalize UUID subjects to their string form."""
        if value is None:
            return None
        return str(value)

    def __repr__(self) -> str:
        return f"<Watchlist {self.plate_pattern}>"
