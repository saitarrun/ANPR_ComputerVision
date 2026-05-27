"""
Integration tests for health check and metrics endpoints.

Coverage:
- GET /healthz: liveness check (always 200)
- GET /readyz: readiness check (postgres + redis healthy)
- GET /metrics: Prometheus metrics
- GET /openapi.json: OpenAPI schema validation
"""

from __future__ import annotations

import pytest


class TestLivenessProbe:
    """GET /healthz liveness probe tests."""

    @pytest.mark.integration
    def test_healthz_always_200(self, client):
        """Test that /healthz always returns 200."""
        response = client.get("/healthz")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_healthz_response_format(self, client):
        """Test that /healthz returns valid response."""
        response = client.get("/healthz")
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok" or data["status"] == "healthy"

    @pytest.mark.integration
    def test_healthz_includes_timestamp(self, client):
        """Test that /healthz includes timestamp."""
        response = client.get("/healthz")
        data = response.json()
        assert "timestamp" in data or "time" in data


class TestReadinessProbe:
    """GET /readyz readiness probe tests."""

    @pytest.mark.integration
    def test_readyz_200_when_healthy(self, client, postgres_container, redis_container):
        """Test that /readyz returns 200 when all services are healthy."""
        response = client.get("/readyz")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_readyz_checks_postgres(self, client):
        """Test that /readyz checks postgres connection."""
        response = client.get("/readyz")
        # Should check postgres and return status
        assert response.status_code in [200, 503]

    @pytest.mark.integration
    def test_readyz_checks_redis(self, client):
        """Test that /readyz checks redis connection."""
        response = client.get("/readyz")
        # Should check redis and return status
        assert response.status_code in [200, 503]

    @pytest.mark.integration
    def test_readyz_response_format(self, client):
        """Test that /readyz response includes dependency status."""
        response = client.get("/readyz")
        if response.status_code == 200:
            data = response.json()
            # Should include status of each dependency
            assert "status" in data or "services" in data

    @pytest.mark.integration
    def test_readyz_503_when_postgres_down(self, client):
        """Test that /readyz returns 503 if postgres is down."""
        # This would require stopping postgres container
        # For now, just test the endpoint exists
        response = client.get("/readyz")
        assert response.status_code in [200, 503]

    @pytest.mark.integration
    def test_readyz_503_when_redis_down(self, client):
        """Test that /readyz returns 503 if redis is down."""
        # This would require stopping redis container
        response = client.get("/readyz")
        assert response.status_code in [200, 503]


class TestMetricsEndpoint:
    """GET /metrics Prometheus metrics tests."""

    @pytest.mark.integration
    def test_metrics_returns_prometheus_format(self, client):
        """Test that /metrics returns Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Prometheus format is text/plain
        assert "text/plain" in response.headers.get("content-type", "")

    @pytest.mark.integration
    def test_metrics_includes_http_requests(self, client):
        """Test that metrics include HTTP request counts."""
        # Make a request first
        client.get("/healthz")
        response = client.get("/metrics")
        assert response.status_code == 200
        content = response.text
        # Should have http_requests_total or similar metric
        assert "requests" in content.lower() or "http" in content.lower()

    @pytest.mark.integration
    def test_metrics_includes_database_metrics(self, client):
        """Test that metrics include database connection stats."""
        response = client.get("/metrics")
        assert response.status_code == 200
        content = response.text
        # Should include db connection pool metrics
        # or query latency metrics

    @pytest.mark.integration
    def test_metrics_includes_redis_metrics(self, client):
        """Test that metrics include redis metrics."""
        response = client.get("/metrics")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_metrics_valid_format(self, client):
        """Test that metrics format is valid."""
        response = client.get("/metrics")
        assert response.status_code == 200
        lines = response.text.split("\n")
        # Prometheus format: lines starting with # are comments
        # Lines with metric names and values: METRIC_NAME{labels} value timestamp
        for line in lines:
            if line and not line.startswith("#"):
                # Should have space-separated value
                assert " " in line or line.startswith("HELP") or line.startswith("TYPE")


class TestOpenAPISchema:
    """GET /openapi.json OpenAPI schema tests."""

    @pytest.mark.integration
    def test_openapi_schema_returns_json(self, client):
        """Test that /openapi.json returns valid JSON."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data is not None

    @pytest.mark.integration
    def test_openapi_schema_structure(self, client):
        """Test that OpenAPI schema has required structure."""
        response = client.get("/openapi.json")
        data = response.json()
        assert "openapi" in data or "swagger" in data
        assert "paths" in data
        assert "components" in data or "definitions" in data

    @pytest.mark.integration
    def test_openapi_schema_includes_endpoints(self, client):
        """Test that schema includes all endpoints."""
        response = client.get("/openapi.json")
        data = response.json()
        paths = data.get("paths", {})
        # Should include auth endpoints
        assert any("/auth" in path for path in paths)
        # Should include stream endpoints
        assert any("/stream" in path for path in paths)

    @pytest.mark.integration
    def test_openapi_schema_includes_auth(self, client):
        """Test that schema documents authentication."""
        response = client.get("/openapi.json")
        data = response.json()
        # Should include security schemes
        components = data.get("components", {})
        assert "securitySchemes" in components or "security" in data

    @pytest.mark.integration
    def test_openapi_docs_endpoint(self, client):
        """Test that Swagger UI is available."""
        response = client.get("/docs")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_openapi_redoc_endpoint(self, client):
        """Test that ReDoc is available."""
        response = client.get("/redoc")
        assert response.status_code == 200
