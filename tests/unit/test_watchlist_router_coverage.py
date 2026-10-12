"""Unit tests for api.routers.watchlist helpers and endpoints.

Uses a fake AsyncSession — no database required. Covers the ReDoS-safe
regex validator (including the timeout branch), the ORM converter, and
every endpoint's happy path plus 400/404/422 branches.
"""

from __future__ import annotations

import re
import signal
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from api.routers import watchlist as watchlist_router
from api.schemas.data import WatchlistIn
from db.models import Watchlist
from fastapi import HTTPException


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
        self.deleted = []
        self.committed = False
        self._fail_commit = fail_commit

    async def execute(self, stmt):
        assert self._results, "fake session ran out of queued results"
        return self._results.pop(0)

    def add(self, obj):
        # Simulate DB-assigned defaults (uuid PK, server timestamps).
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        self.added.append(obj)

    async def commit(self):
        if self._fail_commit:
            raise RuntimeError("db down")
        self.committed = True

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self.deleted.append(obj)

    async def rollback(self):
        pass


def _watchlist(**kw):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    args = {
        "id": uuid.uuid4(),
        "plate_pattern": r"ABC\d+",
        "region_id": uuid.uuid4(),
        "created_by_user_id": "user-1",
        "reason": "stolen",
        "priority": 5,
        "alert_enabled": "Y",
        "alert_channel": "webhook",
        "dedup_window": 300,
        "match_count": 2,
        "created_at": now,
        "updated_at": now,
    }
    args.update(kw)
    return Watchlist(**args)


class TestParseUuidOrNone:
    def test_none(self):
        assert watchlist_router._parse_uuid_or_none(None) is None

    def test_empty(self):
        assert watchlist_router._parse_uuid_or_none("") is None

    def test_invalid(self):
        assert watchlist_router._parse_uuid_or_none("xyz") is None

    def test_valid(self):
        u = uuid.uuid4()
        assert watchlist_router._parse_uuid_or_none(str(u)) == u


class TestRegexTimeoutHandler:
    def test_raises_timeout_error(self):
        with pytest.raises(TimeoutError, match="ReDoS"):
            watchlist_router._regex_timeout_handler(signal.SIGALRM, None)


class TestValidateRegexPattern:
    def test_invalid_regex_returns_false(self):
        assert watchlist_router.validate_regex_pattern("([a-z+") is False

    def test_valid_pattern_returns_true(self):
        assert watchlist_router.validate_regex_pattern(r"ABC\d+") is True

    def test_redos_timeout_returns_false(self, monkeypatch):
        calls = []

        def _alarm(seconds):
            calls.append(seconds)
            if len(calls) == 1:
                raise TimeoutError("simulated ReDoS")
            return 0

        fake_signal = SimpleNamespace(SIGALRM=14, signal=lambda *a: None, alarm=_alarm)
        monkeypatch.setattr(watchlist_router, "signal", fake_signal)
        assert watchlist_router.validate_regex_pattern(r"(a+)+b") is False
        assert calls == [watchlist_router.REGEX_TIMEOUT_SEC, 0]

    def test_worker_thread_skips_signal_probe(self):
        import threading

        results = []
        thread = threading.Thread(
            target=lambda: results.append(watchlist_router.validate_regex_pattern(r"(a+)+b"))
        )
        thread.start()
        thread.join()
        assert results == [True]

    def test_re_error_during_match_returns_false(self, monkeypatch):
        class _BadRegex:
            def match(self, s):
                raise re.error("bad backtrack")

        fake_re = SimpleNamespace(compile=lambda p: _BadRegex(), error=re.error)
        fake_signal = SimpleNamespace(SIGALRM=14, signal=lambda *a: None, alarm=lambda s: 0)
        monkeypatch.setattr(watchlist_router, "re", fake_re)
        monkeypatch.setattr(watchlist_router, "signal", fake_signal)
        assert watchlist_router.validate_regex_pattern(r"ABC\d+") is False

    def test_unexpected_match_error_returns_false(self, monkeypatch):
        class _BadRegex:
            def match(self, s):
                raise RuntimeError("boom")

        fake_re = SimpleNamespace(compile=lambda p: _BadRegex(), error=re.error)
        fake_signal = SimpleNamespace(SIGALRM=14, signal=lambda *a: None, alarm=lambda s: 0)
        monkeypatch.setattr(watchlist_router, "re", fake_re)
        monkeypatch.setattr(watchlist_router, "signal", fake_signal)
        assert watchlist_router.validate_regex_pattern(r"ABC\d+") is False


class TestToOut:
    def test_full_fields(self):
        w = _watchlist()
        out = watchlist_router._to_out(w)
        assert out.plate_pattern == r"ABC\d+"
        assert out.region_id == str(w.region_id)
        assert out.reason == "stolen"
        assert out.priority == 5
        assert out.alert_enabled is True
        assert out.alert_channel == "webhook"
        assert out.dedup_window == 300
        assert out.match_count == 2
        assert out.created_by_user_id == "user-1"

    def test_nullable_defaults(self):
        w = _watchlist(
            region_id=None,
            created_by_user_id=None,
            priority=None,
            alert_enabled="N",
            dedup_window=None,
            match_count=None,
        )
        out = watchlist_router._to_out(w)
        assert out.region_id is None
        assert out.created_by_user_id is None
        assert out.priority == 0
        assert out.alert_enabled is False
        assert out.dedup_window == 300
        assert out.match_count == 0


class TestCreateWatchlist:
    async def test_empty_pattern_400(self):
        data = WatchlistIn(plate_pattern="   ")
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.create_watchlist(data=data, db=_FakeSession(), user_id="u")
        assert ei.value.status_code == 400

    async def test_invalid_regex_400(self):
        data = WatchlistIn(plate_pattern="([a-z+")
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.create_watchlist(data=data, db=_FakeSession(), user_id="u")
        assert ei.value.status_code == 400

    async def test_invalid_region_id_422(self):
        data = WatchlistIn(plate_pattern=r"ABC\d+", region_id="nope")
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.create_watchlist(data=data, db=_FakeSession(), user_id="u")
        assert ei.value.status_code == 422

    async def test_ok(self):
        rid = uuid.uuid4()
        data = WatchlistIn(
            plate_pattern=r"ABC\d+",
            region_id=str(rid),
            reason="stolen",
            priority=5,
            alert_enabled=True,
        )
        db = _FakeSession()
        out = await watchlist_router.create_watchlist(data=data, db=db, user_id="user-9")
        assert db.committed is True
        assert len(db.added) == 1
        assert out.plate_pattern == r"ABC\d+"
        assert out.region_id == str(rid)
        assert out.alert_enabled is True
        assert out.created_by_user_id == "user-9"
        assert out.match_count == 0

    async def test_alert_disabled_stored_as_n(self):
        data = WatchlistIn(plate_pattern=r"ABC\d+", alert_enabled=False)
        db = _FakeSession()
        out = await watchlist_router.create_watchlist(data=data, db=db, user_id="u")
        assert out.alert_enabled is False
        assert db.added[0].alert_enabled == "N"

    async def test_commit_failure_400(self):
        data = WatchlistIn(plate_pattern=r"ABC\d+")
        db = _FakeSession(fail_commit=True)
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.create_watchlist(data=data, db=db, user_id="u")
        assert ei.value.status_code == 400


class TestListWatchlist:
    async def test_no_filters(self):
        w = _watchlist()
        db = _FakeSession([_FakeResult(items=[w])])
        out = await watchlist_router.list_watchlist(db=db, user_id="u")
        assert len(out) == 1
        assert out[0].plate_pattern == r"ABC\d+"

    async def test_region_and_enabled_filters(self):
        w = _watchlist()
        db = _FakeSession([_FakeResult(items=[w])])
        out = await watchlist_router.list_watchlist(
            region_id=str(uuid.uuid4()), enabled_only=True, db=db, user_id="u"
        )
        assert len(out) == 1

    async def test_invalid_region_id_ignored(self):
        db = _FakeSession([_FakeResult(items=[])])
        out = await watchlist_router.list_watchlist(region_id="nope", db=db, user_id="u")
        assert out == []


class TestGetWatchlist:
    async def test_invalid_uuid_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.get_watchlist("nope", db=db, user_id="u")
        assert ei.value.status_code == 404

    async def test_not_found_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.get_watchlist(str(uuid.uuid4()), db=db, user_id="u")
        assert ei.value.status_code == 404

    async def test_ok(self):
        w = _watchlist()
        db = _FakeSession([_FakeResult(one=w)])
        out = await watchlist_router.get_watchlist(str(w.id), db=db, user_id="u")
        assert out.plate_pattern == r"ABC\d+"


class TestUpdateWatchlist:
    async def test_not_found_404(self):
        data = WatchlistIn(plate_pattern=r"ABC\d+")
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.update_watchlist(
                str(uuid.uuid4()), data=data, db=db, user_id="u"
            )
        assert ei.value.status_code == 404

    async def test_empty_pattern_400(self):
        w = _watchlist()
        data = WatchlistIn(plate_pattern="  ")
        db = _FakeSession([_FakeResult(one=w)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.update_watchlist(str(w.id), data=data, db=db, user_id="u")
        assert ei.value.status_code == 400

    async def test_invalid_regex_400(self):
        w = _watchlist()
        data = WatchlistIn(plate_pattern="([a-z+")
        db = _FakeSession([_FakeResult(one=w)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.update_watchlist(str(w.id), data=data, db=db, user_id="u")
        assert ei.value.status_code == 400

    async def test_invalid_region_422(self):
        w = _watchlist()
        data = WatchlistIn(plate_pattern=r"ABC\d+", region_id="nope")
        db = _FakeSession([_FakeResult(one=w)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.update_watchlist(str(w.id), data=data, db=db, user_id="u")
        assert ei.value.status_code == 422

    async def test_ok(self):
        w = _watchlist()
        data = WatchlistIn(
            plate_pattern=r"XYZ\d+",
            reason="updated",
            priority=9,
            alert_enabled=False,
            alert_channel="email",
        )
        db = _FakeSession([_FakeResult(one=w)])
        out = await watchlist_router.update_watchlist(str(w.id), data=data, db=db, user_id="u")
        assert db.committed is True
        assert out.plate_pattern == r"XYZ\d+"
        assert out.reason == "updated"
        assert out.priority == 9
        assert out.alert_enabled is False
        assert w.alert_channel == "email"

    async def test_commit_failure_400(self):
        w = _watchlist()
        data = WatchlistIn(plate_pattern=r"ABC\d+")
        db = _FakeSession([_FakeResult(one=w)], fail_commit=True)
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.update_watchlist(str(w.id), data=data, db=db, user_id="u")
        assert ei.value.status_code == 400


class TestDeleteWatchlist:
    async def test_invalid_uuid_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.delete_watchlist("nope", db=db, user_id="u")
        assert ei.value.status_code == 404

    async def test_not_found_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await watchlist_router.delete_watchlist(str(uuid.uuid4()), db=db, user_id="u")
        assert ei.value.status_code == 404

    async def test_ok(self):
        w = _watchlist()
        db = _FakeSession([_FakeResult(one=w)])
        result = await watchlist_router.delete_watchlist(str(w.id), db=db, user_id="u")
        assert result is None
        assert db.deleted == [w]
        assert db.committed is True
