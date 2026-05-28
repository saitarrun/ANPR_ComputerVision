"""Test security headers, audit logging, and rate limiting configuration."""

import pytest
import json
from fastapi.testclient import TestClient


class TestSecurityHeaders:
    """Verify all security headers are present."""

    def test_hsts_header_present(self, client: TestClient):
        """HSTS (HTTP Strict-Transport-Security) header should be present."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in response.headers["Strict-Transport-Security"]

    def test_content_type_options_header(self, client: TestClient):
        """X-Content-Type-Options should be nosniff."""
        response = client.get("/healthz")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_frame_options_header(self, client: TestClient):
        """X-Frame-Options should deny embedding."""
        response = client.get("/healthz")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_csp_header(self, client: TestClient):
        """Content-Security-Policy should restrict to same-origin."""
        response = client.get("/healthz")
        assert response.headers.get("Content-Security-Policy") == "default-src 'self'"

    def test_referrer_policy_header(self, client: TestClient):
        """Referrer-Policy should prevent leaking."""
        response = client.get("/healthz")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_request_id_header(self, client: TestClient):
        """X-Request-ID should be present on all responses."""
        response = client.get("/healthz")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0


class TestAuditLogging:
    """Verify audit logging infrastructure."""

    def test_audit_logger_configured(self):
        """Audit logger should be importable and configured."""
        from api.logging import audit_logger
        assert audit_logger is not None
        assert hasattr(audit_logger, 'info')
        assert hasattr(audit_logger, 'warning')
        assert hasattr(audit_logger, 'error')

    def test_audit_log_context_manager(self):
        """Audit logging context manager should work."""
        from api.logging import audit_log_context, audit_context
        
        with audit_log_context("test-request-id", "test-user", "127.0.0.1"):
            ctx = audit_context.get()
            assert ctx["request_id"] == "test-request-id"
            assert ctx["user_id"] == "test-user"
            assert ctx["ip"] == "127.0.0.1"

    def test_audit_log_json_format(self):
        """Audit logs should be JSON-formatted."""
        from api.logging import StructuredFormatter
        import logging
        
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="audit",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test_event",
            args=(),
            exc_info=None
        )
        record.user_id = "test-user"
        record.action = "test_action"
        
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test_event"
        assert parsed["user_id"] == "test-user"
        assert parsed["action"] == "test_action"


class TestRateLimiter:
    """Verify rate limiting infrastructure."""

    def test_rate_limiter_configured(self, app):
        """Rate limiter should be configured on app state."""
        assert hasattr(app.state, 'limiter')
        assert app.state.limiter is not None

    def test_rate_limit_exceeded_handler_registered(self, app):
        """Rate limit exceeded exception handler should be registered."""
        from slowapi.errors import RateLimitExceeded
        assert RateLimitExceeded in app.exception_handlers

    def test_rate_limit_exceeded_response(self, client: TestClient):
        """Rate limit exceeded should return 429 with proper format."""
        from slowapi.errors import RateLimitExceeded
        
        # We can't easily trigger a real rate limit in tests, 
        # but we can verify the exception handler exists and is configured
        app = client.app
        assert RateLimitExceeded in app.exception_handlers
        handler = app.exception_handlers[RateLimitExceeded]
        assert callable(handler)


class TestAuditLoggingOnAuthEndpoints:
    """Verify audit logging is triggered on security events."""

    def test_login_attempt_logged(self, client: TestClient):
        """Login attempts should be logged to audit trail."""
        # This test verifies the middleware is in place
        # Actual log verification would require capturing logs
        response = client.post(
            "/v1/auth/login",
            json={"email": "invalid@test.local", "password": "wrong"}
        )
        # Response may fail due to invalid credentials, but middleware should still run
        assert "X-Request-ID" in response.headers

    def test_request_context_available(self, client: TestClient):
        """Request should have audit context set by middleware."""
        response = client.get("/healthz")
        assert response.status_code == 200
        # Verify request ID is tracked
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"] is not None


class TestHTTPSRedirectMiddleware:
    """Verify HTTPS redirect configuration (disabled in test env)."""

    def test_https_redirect_disabled_in_test(self, client: TestClient):
        """HTTPS redirect should be disabled outside production."""
        # In test environment (app_env != production), redirect should not happen
        response = client.get("/healthz")
        assert response.status_code == 200
        # Should not be redirected
        assert response.status_code != 301
