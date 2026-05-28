"""SQLAlchemy base model and mixins."""
from datetime import datetime
from typing import Any
from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.orm import declarative_base, declared_attr
from sqlalchemy.dialects.postgresql import UUID
import uuid


class Base:
    """Mixin for all models."""

    @declared_attr
    def __tablename__(cls) -> str:
        """Auto-generate table name from class name."""
        return cls.__name__.lower() + "s"

    __allow_unmapped__ = True


# Create declarative base
DeclarativeBase = declarative_base(cls=Base)


class IDMixin:
    """Mixin for UUID primary key."""

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


class TimestampMixin:
    """Mixin for created/updated timestamps."""

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
