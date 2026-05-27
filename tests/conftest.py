"""
M6 Test Infrastructure: Async fixtures, testcontainers, auth, and database setup.

Provides:
- PostgreSQL + Redis containers (testcontainers)
- SQLAlchemy async session factory
- FastAPI TestClient and WebSocket fixtures
- JWT auth token factory
- User/stream/plate seed data
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator, Generator
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# ======================== Container Fixtures ========================


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Session-wide event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start PostgreSQL 15 container for the entire test session."""
    container = PostgresContainer("postgres:15-alpine", driver="psycopg")
    container.start()
    # Wait for postgres to be healthy
    import time
    time.sleep(2)
    yield container
    container.stop()


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Start Redis 7 container for the entire test session."""
    container = RedisContainer("redis:7-alpine")
    container.start()
    # Wait for redis to be healthy
    import time
    time.sleep(1)
    yield container
    container.stop()


@pytest.fixture(scope="session")
def postgres_url(postgres_container: PostgresContainer) -> str:
    """PostgreSQL connection URL from container."""
    url = postgres_container.get_connection_url()
    # Convert to async URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Redis connection URL from container."""
    parsed = urlparse(redis_container.get_connection_url())
    return f"redis://{parsed.hostname}:{parsed.port}/0"


# ======================== Database Session Fixtures ========================


@pytest_asyncio.fixture
async def db_engine(postgres_url: str):
    """Create async SQLAlchemy engine."""
    from db.base import Base

    engine = create_async_engine(
        postgres_url,
        echo=False,
        future=True,
        poolclass=NullPool,  # No connection pooling for tests
    )
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh database session for each test."""
    async_session = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with async_session() as session:
        yield session


@pytest.fixture
def db_session_sync(db_session):
    """Synchronous wrapper for tests that don't use async."""
    # For sync tests, return the event loop and session
    return db_session


# ======================== Security & Auth Fixtures ========================


@pytest.fixture
def jwt_secret() -> str:
    """JWT secret key for testing."""
    return os.environ.get("JWT_SECRET", "test-secret-key-min-32-chars-long-value-here-ok!")


@pytest.fixture
def auth_token_factory(jwt_secret: str):
    """Factory to create JWT tokens for different roles."""
    from api.security import encode_jwt

    def _create_token(
        user_id: str = "test-user-id",
        role: str = "viewer",
        exp_seconds: int = 900,
    ) -> str:
        return encode_jwt(
            user_id=user_id,
            role=role,
            secret=jwt_secret,
            exp_seconds=exp_seconds,
            token_type="access",
        )

    return _create_token


@pytest.fixture
def refresh_token_factory(jwt_secret: str):
    """Factory to create refresh tokens."""
    from api.security import encode_jwt

    def _create_token(user_id: str = "test-user-id") -> str:
        return encode_jwt(
            user_id=user_id,
            role="viewer",  # Role doesn't matter for refresh tokens
            secret=jwt_secret,
            exp_seconds=604800,
            token_type="refresh",
        )

    return _create_token


# ======================== FastAPI TestClient Fixtures ========================


@pytest.fixture
def app():
    """FastAPI application instance."""
    from api.main import create_app

    return create_app()


@pytest.fixture
def client(app, db_session, auth_token_factory):
    """FastAPI TestClient with mocked database dependency."""
    from fastapi.testclient import TestClient

    # Override the get_session dependency to use test session
    from api.deps import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client, auth_token_factory):
    """TestClient with Authorization header pre-set."""
    token = auth_token_factory(user_id="test-user", role="viewer")
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


@pytest.fixture
def operator_client(client, auth_token_factory):
    """TestClient with operator role token."""
    token = auth_token_factory(user_id="operator-user", role="operator")
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


@pytest.fixture
def admin_client(client, auth_token_factory):
    """TestClient with admin role token."""
    token = auth_token_factory(user_id="admin-user", role="admin")
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


# ======================== Test Data Fixtures ========================


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user in database."""
    from db.models import User
    from api.security import hash_password

    user = User(
        id="test-user",
        email="viewer@test.local",
        password_hash=hash_password("secure-password-123"),
        role="viewer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def operator_user(db_session):
    """Create a test operator in database."""
    from db.models import User
    from api.security import hash_password

    user = User(
        id="operator-user",
        email="operator@test.local",
        password_hash=hash_password("secure-password-456"),
        role="operator",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session):
    """Create a test admin in database."""
    from db.models import User
    from api.security import hash_password

    user = User(
        id="admin-user",
        email="admin@test.local",
        password_hash=hash_password("secure-password-789"),
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_region(db_session):
    """Create a test region."""
    from db.models import Region

    region = Region(
        id="IN",
        code="IN",
        name="India",
    )
    db_session.add(region)
    await db_session.commit()
    await db_session.refresh(region)
    return region


@pytest_asyncio.fixture
async def test_stream(db_session, test_user, test_region):
    """Create a test stream."""
    from db.models import Stream

    stream = Stream(
        id="test-stream-1",
        name="Test Stream 1",
        rtsp_url="rtsp://example.com/test",
        user_id=test_user.id,
        region_id=test_region.id,
    )
    db_session.add(stream)
    await db_session.commit()
    await db_session.refresh(stream)
    return stream


@pytest_asyncio.fixture
async def test_plate(db_session, test_region):
    """Create a test plate."""
    from db.models import Plate
    from cryptography.fernet import Fernet

    cipher_key = os.environ.get("PLATE_ENCRYPTION_KEY", Fernet.generate_key())
    cipher = Fernet(cipher_key)

    # Store encrypted plate string
    encrypted_plate = cipher.encrypt(b"KA01AB1234")

    plate = Plate(
        id="plate-1",
        region_id=test_region.id,
        plate_string_encrypted=encrypted_plate,
        confidence=0.95,
    )
    db_session.add(plate)
    await db_session.commit()
    await db_session.refresh(plate)
    return plate


# ======================== WebSocket Fixtures ========================


@pytest.fixture
def websocket_url(auth_token_factory):
    """WebSocket URL with auth token."""
    token = auth_token_factory()
    return f"ws://testserver/v1/stream/test-stream-1?token={token}"


# ======================== Utility Fixtures ========================


@pytest.fixture
def assert_status(client):
    """Helper to assert HTTP response status."""

    def _assert(response, expected_status: int):
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}. "
            f"Response: {response.text}"
        )

    return _assert


@pytest.fixture
def assert_schema(client):
    """Helper to validate response schema against expected keys."""

    def _assert(data: dict, required_keys: list[str]):
        for key in required_keys:
            assert (
                key in data
            ), f"Missing required key '{key}' in response. Got: {list(data.keys())}"

    return _assert


# ======================== Redis Fixture ========================


@pytest.fixture
def redis_client(redis_url: str):
    """Redis connection for tests."""
    import redis

    r = redis.from_url(redis_url, decode_responses=True)
    yield r
    r.flushdb()
    r.close()


# ======================== Marker Setup ========================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: unit tests")
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "e2e: end-to-end tests")
    config.addinivalue_line("markers", "slow: tests that take > 1s")
