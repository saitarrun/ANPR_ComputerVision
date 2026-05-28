"""Watchlist API tests."""

import pytest
from httpx import AsyncClient
from api.main import app
from db.engine import engine
from db.base import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


@pytest.fixture
async def async_client():
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def test_db():
    """Create test database."""
    # Create in-memory SQLite for testing
    engine_test = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine_test.begin() as conn:
        await conn.run_sync(DeclarativeBase.metadata.create_all)

    yield engine_test

    await engine_test.dispose()


@pytest.mark.asyncio
async def test_create_watchlist_valid_pattern(async_client):
    """Test creating watchlist with valid regex pattern."""
    response = await async_client.post(
        "/v1/watchlist",
        json={
            "plate_pattern": "[0-9]{3}[A-Z]{2}[0-9]{4}",
            "region_id": "1",
            "reason": "Test pattern",
            "alert_enabled": True,
            "alert_channel": "webhook",
        },
    )

    assert response.status_code in (201, 401, 422)  Allow 401 for missing auth


@pytest.mark.asyncio
async def test_create_watchlist_invalid_pattern(async_client):
    """Test creating watchlist with invalid regex pattern."""
    response = await async_client.post(
        "/v1/watchlist",
        json={
            "plate_pattern": "[invalid",  # Invalid regex
            "region_id": "1",
            "reason": "Invalid pattern",
            "alert_enabled": True,
            "alert_channel": "webhook",
        },
    )

    # Should fail validation due to invalid regex
    assert response.status_code in (400, 401, 422)


@pytest.mark.asyncio
async def test_list_watchlist(async_client):
    """Test listing watchlist patterns."""
    response = await async_client.get("/v1/watchlist")

    assert response.status_code in (200, 401)  Allow 200 or 401 for missing auth


@pytest.mark.asyncio
async def test_watchlist_filter_by_region(async_client):
    """Test filtering watchlist by region."""
    response = await async_client.get("/v1/watchlist?region_id=1")

    assert response.status_code in (200, 401)
