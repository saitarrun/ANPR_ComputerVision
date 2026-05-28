"""E2E test fixtures - connects to real running services."""

import pytest
import httpx


@pytest.fixture
def http_client() -> httpx.Client:
    """HTTP client for E2E tests against real running API."""
    return httpx.Client(timeout=30.0, base_url="http://localhost:8000")
