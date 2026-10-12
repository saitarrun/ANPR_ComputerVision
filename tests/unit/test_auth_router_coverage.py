"""Unit tests for api.routers.auth endpoints.

Security helpers and the DB session are mocked — no database, no Redis,
no real crypto needed. Covers login, register, refresh, and me endpoints
including every 401/422 branch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from api.exceptions import AuthenticationError, ValidationError
from api.routers import auth as auth_router
from api.schemas.auth import LoginRequest, RefreshRequest


class _FakeScalars:
    def __init__(self, items):
        self._items = list(items)

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _FakeResult:
    def __init__(self, items=None, one=None):
        self._items = items
        self._one = one

    def scalars(self):
        return _FakeScalars(self._items or [])

    def scalar_one_or_none(self):
        return self._one


class _FakeSession:
    def __init__(self, results=(), fail_commit=False):
        self._results = list(results)
        self.added = []
        self.committed = False
        self._fail_commit = fail_commit

    async def execute(self, stmt):
        assert self._results, "fake session ran out of queued results"
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        if self._fail_commit:
            raise RuntimeError("db down")
        self.committed = True

    async def refresh(self, obj):
        pass

    async def rollback(self):
        pass


def _user(**kw):
    base = {
        "id": uuid.uuid4(),
        "email": "u@example.com",
        "username": "u",
        "hashed_password": "hashed:secret",
        "role": "viewer",
        "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }
    base.update(kw)
    return SimpleNamespace(**base)


class TestLogin:
    async def test_user_not_found_401(self):
        db = _FakeSession([_FakeResult(items=[])])
        with pytest.raises(AuthenticationError) as ei:
            await auth_router.login(LoginRequest(email="nobody@example.com", password="pw"), db=db)
        assert ei.value.status_code == 401

    async def test_wrong_password_401(self, monkeypatch):
        db = _FakeSession([_FakeResult(items=[_user()])])
        monkeypatch.setattr(auth_router, "verify_password", lambda p, h: False)
        with pytest.raises(AuthenticationError):
            await auth_router.login(LoginRequest(email="u@example.com", password="bad"), db=db)

    async def test_invalid_role_401(self):
        db = _FakeSession([_FakeResult(items=[_user(role="superadmin")])])
        with pytest.raises(AuthenticationError) as ei:
            await auth_router.login(LoginRequest(email="u@example.com", password="secret"), db=db)
        assert "role" in ei.value.message

    async def test_ok_returns_tokens(self, monkeypatch):
        user = _user(role="operator")
        db = _FakeSession([_FakeResult(items=[user])])
        monkeypatch.setattr(auth_router, "create_access_token", lambda *a, **kw: "AT")
        monkeypatch.setattr(auth_router, "create_refresh_token", lambda *a, **kw: "RT")
        out = await auth_router.login(LoginRequest(email="u@example.com", password="secret"), db=db)
        assert out["access_token"] == "AT"
        assert out["refresh_token"] == "RT"
        assert out["role"] == "operator"
        assert out["user_id"] == str(user.id)
        assert out["expires_in"] > 0


class TestRegister:
    async def test_non_dict_422(self):
        with pytest.raises(ValidationError) as ei:
            await auth_router.register.__wrapped__(
                request_obj=None, request="nope", db=_FakeSession()
            )
        assert ei.value.status_code == 422

    async def test_missing_email_422(self):
        with pytest.raises(ValidationError):
            await auth_router.register.__wrapped__(
                request_obj=None,
                request={"password": "pw", "username": "u"},
                db=_FakeSession(),
            )

    async def test_blank_fields_422(self):
        with pytest.raises(ValidationError):
            await auth_router.register.__wrapped__(
                request_obj=None,
                request={"email": "  ", "password": "pw", "username": "u"},
                db=_FakeSession(),
            )

    async def test_existing_user_422(self):
        db = _FakeSession([_FakeResult(items=[_user()])])
        with pytest.raises(ValidationError) as ei:
            await auth_router.register.__wrapped__(
                request_obj=None,
                request={"email": "u@example.com", "password": "pw", "username": "u"},
                db=db,
            )
        assert "already exists" in ei.value.message

    async def test_ok_creates_user(self, monkeypatch):
        db = _FakeSession([_FakeResult(items=[])])
        monkeypatch.setattr(auth_router, "hash_password", lambda p: "hashed:" + p)
        monkeypatch.setattr(auth_router, "create_access_token", lambda *a, **kw: "AT")
        monkeypatch.setattr(auth_router, "create_refresh_token", lambda *a, **kw: "RT")
        out = await auth_router.register.__wrapped__(
            request_obj=None,
            request={
                "email": "new@example.com",
                "password": "pw",
                "username": "newbie",
            },
            db=db,
        )
        assert db.committed is True
        assert len(db.added) == 1
        created = db.added[0]
        assert created.email == "new@example.com"
        assert created.username == "newbie"
        assert created.hashed_password == "hashed:pw"
        assert out["access_token"] == "AT"
        assert out["refresh_token"] == "RT"


class TestRefresh:
    async def test_missing_payload_401(self):
        with pytest.raises(AuthenticationError):
            await auth_router.refresh(payload=None, db=_FakeSession())

    async def test_invalid_token_401(self, monkeypatch):
        def _bad(token, expected):
            raise auth_router.JWTError("bad token")

        monkeypatch.setattr(auth_router, "verify_token_type", _bad)
        with pytest.raises(AuthenticationError) as ei:
            await auth_router.refresh(
                payload=RefreshRequest(refresh_token="junk"), db=_FakeSession()
            )
        assert "Invalid refresh token" in ei.value.message

    async def test_blacklisted_token_401(self, monkeypatch):
        user = _user()
        monkeypatch.setattr(
            auth_router,
            "verify_token_type",
            lambda t, typ: {"user_id": str(user.id), "type": typ},
        )

        async def _from_url(url):
            return SimpleNamespace()

        async def _blacklisted(token, client):
            return True

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_from_url))
        monkeypatch.setattr(auth_router, "is_token_blacklisted", _blacklisted)
        with pytest.raises(AuthenticationError) as ei:
            await auth_router.refresh(
                payload=RefreshRequest(refresh_token="tok"), db=_FakeSession()
            )
        assert "revoked" in ei.value.message

    async def test_redis_down_proceeds(self, monkeypatch):
        user = _user()
        monkeypatch.setattr(
            auth_router,
            "verify_token_type",
            lambda t, typ: {"user_id": str(user.id), "type": typ},
        )

        async def _down(url):
            raise RuntimeError("redis down")

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_down))
        db = _FakeSession([_FakeResult(items=[user])])
        out = await auth_router.refresh(payload=RefreshRequest(refresh_token="tok"), db=db)
        assert out["access_token"] == "access-token"
        assert out["refresh_token"] == "tok"

    async def test_invalid_user_id_401(self, monkeypatch):
        monkeypatch.setattr(
            auth_router, "verify_token_type", lambda t, typ: {"user_id": "not-a-uuid"}
        )

        async def _from_url(url):
            return SimpleNamespace()

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_from_url))
        with pytest.raises(AuthenticationError):
            await auth_router.refresh(
                payload=RefreshRequest(refresh_token="tok"), db=_FakeSession()
            )

    async def test_user_not_found_401(self, monkeypatch):
        monkeypatch.setattr(
            auth_router,
            "verify_token_type",
            lambda t, typ: {"user_id": str(uuid.uuid4()), "type": typ},
        )

        async def _from_url(url):
            return SimpleNamespace()

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_from_url))
        db = _FakeSession([_FakeResult(items=[])])
        with pytest.raises(AuthenticationError):
            await auth_router.refresh(payload=RefreshRequest(refresh_token="tok"), db=db)

    async def test_invalid_role_401(self, monkeypatch):
        user = _user(role="superadmin")
        monkeypatch.setattr(
            auth_router,
            "verify_token_type",
            lambda t, typ: {"user_id": str(user.id), "type": typ},
        )

        async def _from_url(url):
            return SimpleNamespace()

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_from_url))
        db = _FakeSession([_FakeResult(items=[user])])
        with pytest.raises(AuthenticationError):
            await auth_router.refresh(payload=RefreshRequest(refresh_token="tok"), db=db)

    async def test_ok(self, monkeypatch):
        user = _user(role="admin")
        monkeypatch.setattr(
            auth_router,
            "verify_token_type",
            lambda t, typ: {"user_id": str(user.id), "type": typ},
        )

        async def _from_url(url):
            return SimpleNamespace()

        monkeypatch.setattr(auth_router, "aioredis", SimpleNamespace(from_url=_from_url))
        monkeypatch.setattr(auth_router, "create_access_token", lambda *a, **kw: "NEWAT")
        db = _FakeSession([_FakeResult(items=[user])])
        out = await auth_router.refresh(payload=RefreshRequest(refresh_token="tok"), db=db)
        assert out["access_token"] == "NEWAT"
        assert out["refresh_token"] == "tok"
        assert out["role"] == "admin"
        assert out["user_id"] == str(user.id)


class TestGetCurrentUserInfo:
    async def test_invalid_identity_401(self):
        with pytest.raises(AuthenticationError):
            await auth_router.get_current_user_info(user_id="nope", db=_FakeSession())

    async def test_not_found_401(self):
        db = _FakeSession([_FakeResult(items=[])])
        with pytest.raises(AuthenticationError):
            await auth_router.get_current_user_info(user_id=str(uuid.uuid4()), db=db)

    async def test_ok(self):
        user = _user()
        db = _FakeSession([_FakeResult(items=[user])])
        out = await auth_router.get_current_user_info(user_id=str(user.id), db=db)
        assert out["email"] == "u@example.com"
        assert out["username"] == "u"
        assert out["role"] == "viewer"
        assert out["id"] == str(user.id)
