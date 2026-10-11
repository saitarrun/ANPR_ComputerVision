"""Region model (license-plate region dimension)."""

from sqlalchemy import Column, String, Integer, UniqueConstraint, Index
from db.base import DeclarativeBase, IDMixin, TimestampMixin


class Region(DeclarativeBase, IDMixin, TimestampMixin):  # type: ignore[misc]
    """Geographic region with plate format rules."""

    __tablename__ = "regions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_regions_code"),
        Index("ix_regions_code", "code"),
    )

    code = Column(String(10), nullable=False)
    name = Column(String(100), nullable=False)
    regex = Column(String(255), nullable=False)
    charset = Column(String(255), nullable=False)
    retention_days = Column(Integer, nullable=False, default=30)

    def __repr__(self) -> str:
        return f"<Region {self.code} ({self.name})>"
