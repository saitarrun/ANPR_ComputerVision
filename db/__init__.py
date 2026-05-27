"""Database module."""
from db.base import DeclarativeBase, IDMixin, TimestampMixin
from db.engine import get_db, init_db, close_db, engine, AsyncSessionLocal
from db.models import (
    User,
    Region,
    Camera,
    Plate,
    Detection,
    Watchlist,
    ReviewQueue,
    AuditLog,
    APIKey,
)

__all__ = [
    "DeclarativeBase",
    "IDMixin",
    "TimestampMixin",
    "get_db",
    "init_db",
    "close_db",
    "engine",
    "AsyncSessionLocal",
    "User",
    "Region",
    "Camera",
    "Plate",
    "Detection",
    "Watchlist",
    "ReviewQueue",
    "AuditLog",
    "APIKey",
]
