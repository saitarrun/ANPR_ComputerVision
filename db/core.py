"""SQLAlchemy database engine and session factory."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)


class Database:
    """Database connection and session management."""

    def __init__(self, database_url: str) -> None:
        """Initialize database engine.

        Args:
            database_url: PostgreSQL async URL (postgresql+asyncpg://...)
        """
        self.engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=NullPool,  # Use NullPool for serverless; adjust for prod
        )
        self.SessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a database session for dependency injection."""
        async with self.SessionLocal() as session:
            yield session

    async def health_check(self) -> bool:
        """Test database connectivity.

        Returns:
            True if DB is healthy.
        """
        try:
            async with self.engine.begin() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close all connections."""
        await self.engine.dispose()
