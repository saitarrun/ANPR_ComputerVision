"""
Integration tests for authentication endpoints.

Coverage:
- POST /v1/auth/login: valid/invalid credentials
- POST /v1/auth/refresh: token refresh
- GET /v1/auth/me: current user info
- RBAC: role-based access control
"""

from __future__ import annotations

import pytest


class TestAuthLogin:
    """POST /v1/auth/login endpoint tests."""

    @pytest.mark.integration
    def test_login_valid_credentials(self, client, test_user):
        """Test login with valid email and password."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "viewer@test.local", "password": "secure-password-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "user_id" in data
        assert "role" in data

    @pytest.mark.integration
    def test_login_invalid_email(self, client):
        """Test login with non-existent email."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "nonexistent@test.local", "password": "password"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data or "error" in data

    @pytest.mark.integration
    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "viewer@test.local", "password": "wrong-password"},
        )
        assert response.status_code == 401

    @pytest.mark.integration
    def test_login_missing_email(self, client):
        """Test login without email."""
        response = client.post(
            "/v1/auth/login",
            json={"password": "password"},
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.integration
    def test_login_missing_password(self, client):
        """Test login without password."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422

    @pytest.mark.integration
    def test_login_empty_credentials(self, client):
        """Test login with empty email and password."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "", "password": ""},
        )
        assert response.status_code in [401, 422]

    @pytest.mark.integration
    def test_login_response_has_user_role(self, client, test_user):
        """Test that login response includes user role."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "viewer@test.local", "password": "secure-password-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "viewer"

    @pytest.mark.integration
    def test_login_operator_role(self, client, operator_user):
        """Test login for operator user."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "operator@test.local", "password": "secure-password-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "operator"

    @pytest.mark.integration
    def test_login_admin_role(self, client, admin_user):
        """Test login for admin user."""
        response = client.post(
            "/v1/auth/login",
            json={"email": "admin@test.local", "password": "secure-password-789"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"


class TestAuthRefresh:
    """POST /v1/auth/refresh endpoint tests."""

    @pytest.mark.integration
    def test_refresh_token_valid(self, client, refresh_token_factory, test_user):
        """Test token refresh with valid refresh token."""
        refresh_token = refresh_token_factory(user_id=test_user.id)
        response = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.integration
    def test_refresh_token_invalid(self, client):
        """Test token refresh with invalid token."""
        response = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert response.status_code == 401

    @pytest.mark.integration
    def test_refresh_token_missing(self, client):
        """Test refresh without token."""
        response = client.post(
            "/v1/auth/refresh",
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.integration
    def test_refresh_with_access_token_fails(self, client, auth_token_factory):
        """Test that access token cannot be used to refresh."""
        access_token = auth_token_factory()
        response = client.post(
            "/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        # Should fail because access token has type="access", not "refresh"
        assert response.status_code == 401


class TestAuthMe:
    """GET /v1/auth/me endpoint tests."""

    @pytest.mark.integration
    def test_auth_me_returns_current_user(self, authenticated_client, test_user):
        """Test getting current user info."""
        response = authenticated_client.get("/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["role"] == test_user.role

    @pytest.mark.integration
    def test_auth_me_no_auth_header(self, client):
        """Test that /auth/me requires authentication."""
        response = client.get("/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_auth_me_invalid_token(self, client):
        """Test with invalid token."""
        client.headers = {"Authorization": "Bearer invalid-token"}
        response = client.get("/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_auth_me_expired_token(self, client, jwt_secret: str):
        """Test with expired token."""
        from api.security import encode_jwt

        expired_token = encode_jwt(
            user_id="test-user",
            role="viewer",
            secret=jwt_secret,
            exp_seconds=-1,  # Already expired
        )
        client.headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/v1/auth/me")
        assert response.status_code == 401


class TestRBAC:
    """Role-Based Access Control tests."""

    @pytest.mark.integration
    def test_viewer_cannot_create_watchlist(self, authenticated_client):
        """Test that viewer role cannot create watchlist."""
        response = authenticated_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        assert response.status_code == 403

    @pytest.mark.integration
    def test_operator_can_create_watchlist(self, operator_client):
        """Test that operator role can create watchlist."""
        response = operator_client.post(
            "/v1/watchlist",
            json={"plate_pattern": "KA*"},
        )
        # 403 if watchlist endpoint returns 403 for invalid pattern
        # 201 if watchlist is created
        assert response.status_code in [201, 422, 400]

    @pytest.mark.integration
    def test_admin_can_view_audit_log(self, admin_client):
        """Test that only admin can view audit log."""
        response = admin_client.get("/v1/audit-log")
        # Should succeed (200 with empty list) or return results
        assert response.status_code in [200, 204]

    @pytest.mark.integration
    def test_viewer_cannot_view_audit_log(self, authenticated_client):
        """Test that viewer cannot view audit log."""
        response = authenticated_client.get("/v1/audit-log")
        assert response.status_code == 403

    @pytest.mark.integration
    def test_operator_cannot_view_audit_log(self, operator_client):
        """Test that operator cannot view audit log."""
        response = operator_client.get("/v1/audit-log")
        assert response.status_code == 403
