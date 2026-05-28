#!/usr/bin/env python
"""
Initialize local development environment after docker-compose up.

Runs Alembic migrations and seeds database with sample data.

Usage:
  python scripts/init_dev_env.py
  python scripts/init_dev_env.py --reset  (drops all tables, recreates from scratch)
"""

import asyncio
import sys
import subprocess
from pathlib import Path
from typing import Optional
import argparse

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def run_migrations() -> bool:
    """Run Alembic migrations."""
    logger.info("Running Alembic migrations...")
    try:
        result = subprocess.run(
            ["alembic", "-c", "db/alembic.ini", "upgrade", "head"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("✓ Alembic migrations completed")
            return True
        else:
            logger.error(f"✗ Alembic failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("✗ Alembic migrations timed out")
        return False
    except Exception as e:
        logger.error(f"✗ Alembic error: {e}")
        return False


async def seed_database() -> bool:
    """Seed database with test data."""
    logger.info("Seeding database with test data...")
    try:
        from seed_db import seed_database as seed_func

        await seed_func()
        logger.info("✓ Database seeded successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Seeding failed: {e}")
        return False


async def init_db_fresh() -> bool:
    """Create all tables from scratch (destructive)."""
    logger.warning("Dropping all tables and recreating schema...")
    try:
        from db.engine import engine
        from db.base import DeclarativeBase

        # Drop all tables
        async with engine.begin() as conn:
            await conn.run_sync(DeclarativeBase.metadata.drop_all)
        logger.info("✓ All tables dropped")

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(DeclarativeBase.metadata.create_all)
        logger.info("✓ Schema created from models")

        await engine.dispose()
        return True
    except Exception as e:
        logger.error(f"✗ Fresh init failed: {e}")
        return False


async def health_check() -> bool:
    """Verify database and Redis connectivity."""
    logger.info("Checking service health...")
    try:
        from db.engine import engine
        import redis

        # Check PostgreSQL
        async with engine.begin() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("✓ PostgreSQL is healthy")

        # Check Redis
        from api.config import settings

        r = redis.from_url(settings.redis_url)
        r.ping()
        r.close()
        logger.info("✓ Redis is healthy")

        await engine.dispose()
        return True
    except Exception as e:
        logger.error(f"✗ Health check failed: {e}")
        return False


async def main():
    """Main initialization flow."""
    parser = argparse.ArgumentParser(description="Initialize ANPR local development environment")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables and recreate schema (destructive)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ANPR Local Development Environment Initialization")
    logger.info("=" * 60)

    # Step 1: Health check
    if not await health_check():
        logger.error("\n✗ Services are not healthy. Did you run 'docker-compose up'?")
        sys.exit(1)

    # Step 2: Initialize database
    if args.reset:
        if not await init_db_fresh():
            sys.exit(1)
    else:
        if not await run_migrations():
            logger.warning("⚠ Migrations failed, attempting fresh schema creation...")
            if not await init_db_fresh():
                sys.exit(1)

    # Step 3: Seed test data
    if not await seed_database():
        logger.warning("⚠ Seeding failed (continuing anyway)")

    logger.info("=" * 60)
    logger.info("✓ Development environment ready!")
    logger.info("=" * 60)
    logger.info("\nEndpoints:")
    logger.info("  API:             http://localhost:8000")
    logger.info("  API Docs:        http://localhost:8000/docs")
    logger.info("  pgAdmin:         http://localhost:5050")
    logger.info("  Redis Commander: http://localhost:8081")
    logger.info("  MinIO Console:   http://localhost:9001")
    logger.info("\nTest user credentials:")
    logger.info("  Email:    test@example.com")
    logger.info("  Password: password123")
    logger.info("\nNext steps:")
    logger.info("  1. Run tests:        make test")
    logger.info("  2. View API docs:    open http://localhost:8000/docs")
    logger.info("  3. Check logs:       docker-compose logs -f api")


if __name__ == "__main__":
    asyncio.run(main())
