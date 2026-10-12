"""Integration tests for the settings router (user settings + admin user mgmt)."""

import uuid

import pytest

from api.config import UserRole
from api.security import hash_password
from db.models import User


@pytest.fixture
async def admin_user(db_session):
    user = User(
        id=uuid.uuid4(),
        email="admin@test.local",
        username="admin_user",
        hashed_password=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
        is_active="Y",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _token_for(client, auth_token_factory, user, role):
    token = auth_token_factory(user_id=str(user.id), role=role)
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


class TestUserSettings:
    def test_get_settings(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        r = client.get("/v1/settings")
        assert r.status_code == 200
        assert r.json()["email"] == test_user.email

    def test_get_settings_no_auth(self, client):
        assert client.get("/v1/settings").status_code == 401

    def test_update_settings(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        r = client.put("/v1/settings", json={"retention_days": 60})
        assert r.status_code == 200
        assert r.json()["retention_days"] == 60

    def test_update_settings_empty_body(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        r = client.put("/v1/settings", json={})
        assert r.status_code == 200


class TestAdminUsers:
    def test_list_users_as_admin(self, client, auth_token_factory, admin_user):
        _token_for(client, auth_token_factory, admin_user, "admin")
        r = client.get("/v1/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_list_users_as_viewer_forbidden(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        assert client.get("/v1/users").status_code == 403

    def test_list_users_no_auth(self, client):
        assert client.get("/v1/users").status_code == 401

    def test_update_user_as_admin(self, client, auth_token_factory, admin_user, test_user):
        _token_for(client, auth_token_factory, admin_user, "admin")
        r = client.put(f"/v1/users/{test_user.id}", json={"role": "operator"})
        assert r.status_code in (200, 422)

    def test_update_user_as_viewer_forbidden(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        r = client.put(f"/v1/users/{test_user.id}", json={"role": "operator"})
        assert r.status_code == 403


class TestHealthStatus:
    def test_health_status(self, client, auth_token_factory, test_user):
        _token_for(client, auth_token_factory, test_user, "viewer")
        r = client.get("/v1/health/status")
        assert r.status_code == 200
