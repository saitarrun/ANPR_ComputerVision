"""Unit tests for api.routers.data helpers and endpoints.

Uses a fake AsyncSession — no database required. Covers UUID helpers,
region scoping, plate validation, dict converters, and every endpoint's
happy path plus 403/404/422 branches.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from api.routers import data as data_router
from db.models import Camera, Detection, Plate, Region, User
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
    """Minimal async session stub returning queued results."""

    def __init__(self, results=()):
        self._results = list(results)
        self.added = []

    async def execute(self, stmt):
        assert self._results, "fake session ran out of queued results"
        return self._results.pop(0)


def _region(**kw):
    args = {
        "id": uuid.uuid4(),
        "code": "IN",
        "name": "India",
        "regex": "^[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}$",
        "charset": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "retention_days": 30,
    }
    args.update(kw)
    return Region(**args)


def _user(**kw):
    args = {
        "id": uuid.uuid4(),
        "email": "u@example.com",
        "username": "u",
        "hashed_password": "x",
        "role": "viewer",
    }
    args.update(kw)
    return User(**args)


def _camera(region_id, **kw):
    args = {
        "id": uuid.uuid4(),
        "name": "cam-1",
        "source_type": "rtsp",
        "url": "rtsp://x",
        "region_id": region_id,
        "status": "active",
    }
    args.update(kw)
    return Camera(**args)


def _plate(region_id, **kw):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    args = {
        "id": uuid.uuid4(),
        "plate_string": "MH12AB1234",
        "region_id": region_id,
        "detection_count": 3,
        "first_seen_at": now,
        "last_seen_at": now,
        "avg_confidence": 0.91,
    }
    args.update(kw)
    return Plate(**args)


def _detection(camera_id, plate_id, **kw):
    args = {
        "id": uuid.uuid4(),
        "camera_id": camera_id,
        "plate_id": plate_id,
        "frame_timestamp": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "confidence": 0.88,
        "bbox": {"x": 1},
        "ocr_backend": None,
        "quality_score": None,
        "is_persisted": "N",
    }
    args.update(kw)
    return Detection(**args)


def _scoped_db(user, assignments):
    """Fake session primed for _scoped_region_ids (user lookup + assignments)."""
    return _FakeSession([_FakeResult(one=user), _FakeResult(items=assignments)])


class TestValidateUuid:
    def test_valid_uuid(self):
        u = str(uuid.uuid4())
        assert data_router.validate_uuid(u, "region ID") == uuid.UUID(u)

    def test_invalid_raises_422(self):
        with pytest.raises(HTTPException) as ei:
            data_router.validate_uuid("not-a-uuid", "camera ID")
        assert ei.value.status_code == 422
        assert "camera ID" in ei.value.detail


class TestParseUuidOrNone:
    def test_none(self):
        assert data_router._parse_uuid_or_none(None) is None

    def test_empty_string(self):
        assert data_router._parse_uuid_or_none("") is None

    def test_invalid(self):
        assert data_router._parse_uuid_or_none("xyz") is None

    def test_valid(self):
        u = uuid.uuid4()
        assert data_router._parse_uuid_or_none(str(u)) == u


class TestScopedRegionIds:
    async def test_invalid_user_id_returns_none_without_db(self):
        db = _FakeSession()
        assert await data_router._scoped_region_ids("not-a-uuid", db) is None
        assert db._results == []

    async def test_unknown_user_returns_none(self):
        db = _FakeSession([_FakeResult(one=None)])
        assert await data_router._scoped_region_ids(str(uuid.uuid4()), db) is None

    async def test_user_without_assignments_returns_empty(self):
        user = _user()
        db = _scoped_db(user, [])
        assert await data_router._scoped_region_ids(str(user.id), db) == []

    async def test_user_with_assignments(self):
        user = _user()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        db = _scoped_db(user, [r1, r2])
        assert await data_router._scoped_region_ids(str(user.id), db) == [r1, r2]


class TestRequireRegionAccess:
    def test_none_region_ids_is_noop(self):
        data_router._require_region_access(None, uuid.uuid4())

    def test_allowed_region(self):
        rid = uuid.uuid4()
        data_router._require_region_access([rid], rid)

    def test_string_region_id_normalized(self):
        rid = uuid.uuid4()
        data_router._require_region_access([rid], str(rid))

    def test_denied_raises_403(self):
        with pytest.raises(HTTPException) as ei:
            data_router._require_region_access([uuid.uuid4()], uuid.uuid4())
        assert ei.value.status_code == 403

    def test_custom_detail(self):
        with pytest.raises(HTTPException) as ei:
            data_router._require_region_access(
                [uuid.uuid4()], uuid.uuid4(), detail="nope"
            )
        assert ei.value.detail == "nope"


class TestRequireAnyRegionAccess:
    def test_none_is_noop(self):
        data_router._require_any_region_access(None)

    def test_non_empty_ok(self):
        data_router._require_any_region_access([uuid.uuid4()])

    def test_empty_raises_403(self):
        with pytest.raises(HTTPException) as ei:
            data_router._require_any_region_access([])
        assert ei.value.status_code == 403


class TestValidatePlateString:
    async def test_region_not_found(self):
        db = _FakeSession([_FakeResult(items=[])])
        with pytest.raises(HTTPException) as ei:
            await data_router.validate_plate_string("MH12AB1234", uuid.uuid4(), db)
        assert ei.value.status_code == 404

    async def test_invalid_plate_format(self):
        region = _region()
        db = _FakeSession([_FakeResult(items=[region])])
        with pytest.raises(HTTPException) as ei:
            await data_router.validate_plate_string("NOPE", region.id, db)
        assert ei.value.status_code == 422
        assert region.code in ei.value.detail

    async def test_valid_plate_returns_none(self):
        region = _region()
        db = _FakeSession([_FakeResult(items=[region])])
        assert (
            await data_router.validate_plate_string("MH12AB1234", region.id, db) is None
        )


class TestDictConverters:
    def test_camera_to_dict(self):
        rid = uuid.uuid4()
        c = _camera(rid, latitude=12.9, longitude=77.6)
        d = data_router._camera_to_dict(c)
        assert d["region_id"] == str(rid)
        assert d["latitude"] == 12.9
        assert d["name"] == "cam-1"

    def test_detection_to_dict_defaults(self):
        d = _detection(uuid.uuid4(), uuid.uuid4())
        out = data_router._detection_to_dict(d)
        assert out["bbox"] == {"x": 1}
        assert out["ocr_backend"] == "unknown"
        assert out["quality_score"] == 0.0
        assert out["is_persisted"] == "N"

    def test_plate_to_dict(self):
        rid = uuid.uuid4()
        p = _plate(rid)
        out = data_router._plate_to_dict(p)
        assert out["plate_string"] == "MH12AB1234"
        assert out["region_id"] == str(rid)
        assert out["confidence"] == 0.91
        assert out["detection_count"] == 3


class TestListRegions:
    async def test_unscoped_returns_all(self):
        r1, r2 = _region(code="IN"), _region(code="US")
        db = _FakeSession([_FakeResult(items=[r1, r2])])
        out = await data_router.list_regions(db=db, user_id="not-a-uuid")
        assert [r["code"] for r in out] == ["IN", "US"]

    async def test_scoped_returns_assigned_only(self):
        user = _user()
        r1 = _region(code="IN")
        db = _FakeSession(
            [
                _FakeResult(one=user),
                _FakeResult(items=[r1.id]),
                _FakeResult(items=[r1]),
            ]
        )
        out = await data_router.list_regions(db=db, user_id=str(user.id))
        assert [r["code"] for r in out] == ["IN"]

    async def test_scoped_without_assignments_forbidden(self):
        user = _user()
        db = _scoped_db(user, [])
        with pytest.raises(HTTPException) as ei:
            await data_router.list_regions(db=db, user_id=str(user.id))
        assert ei.value.status_code == 403


class TestListCamerasForRegion:
    async def test_invalid_uuid_422(self):
        with pytest.raises(HTTPException) as ei:
            await data_router.list_cameras_for_region(
                "bad", db=_FakeSession(), user_id="x"
            )
        assert ei.value.status_code == 422

    async def test_region_not_found_404(self):
        db = _FakeSession([_FakeResult(items=[])])
        with pytest.raises(HTTPException) as ei:
            await data_router.list_cameras_for_region(
                str(uuid.uuid4()), db=db, user_id="not-a-uuid"
            )
        assert ei.value.status_code == 404

    async def test_ok(self):
        region = _region()
        cam = _camera(region.id)
        db = _FakeSession([_FakeResult(items=[region]), _FakeResult(items=[cam])])
        out = await data_router.list_cameras_for_region(
            str(region.id), db=db, user_id="not-a-uuid"
        )
        assert len(out) == 1
        assert out[0]["name"] == "cam-1"


class TestGetCamera:
    async def test_invalid_uuid_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await data_router.get_camera("nope", db=db, user_id="not-a-uuid")
        assert ei.value.status_code == 404

    async def test_forbidden_region_403(self):
        user = _user()
        cam = _camera(uuid.uuid4())
        db = _FakeSession(
            [
                _FakeResult(one=cam),
                _FakeResult(one=user),
                _FakeResult(items=[uuid.uuid4()]),
            ]
        )
        with pytest.raises(HTTPException) as ei:
            await data_router.get_camera(str(cam.id), db=db, user_id=str(user.id))
        assert ei.value.status_code == 403

    async def test_ok(self):
        cam = _camera(uuid.uuid4())
        db = _FakeSession([_FakeResult(one=cam)])
        out = await data_router.get_camera(str(cam.id), db=db, user_id="not-a-uuid")
        assert out["id"] == str(cam.id)


class TestListDetections:
    async def test_invalid_camera_uuid_422(self):
        with pytest.raises(HTTPException) as ei:
            await data_router.list_detections(
                camera_id="bad",
                region_id=None,
                limit=100,
                offset=0,
                db=_FakeSession(),
                user_id="x",
            )
        assert ei.value.status_code == 422

    async def test_camera_not_found_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await data_router.list_detections(
                camera_id=str(uuid.uuid4()),
                region_id=None,
                limit=100,
                offset=0,
                db=db,
                user_id="not-a-uuid",
            )
        assert ei.value.status_code == 404

    async def test_camera_region_forbidden_403(self):
        user = _user()
        cam = _camera(uuid.uuid4())
        db = _FakeSession(
            [
                _FakeResult(one=user),
                _FakeResult(items=[uuid.uuid4()]),
                _FakeResult(one=cam),
            ]
        )
        with pytest.raises(HTTPException) as ei:
            await data_router.list_detections(
                camera_id=str(cam.id),
                region_id=None,
                limit=100,
                offset=0,
                db=db,
                user_id=str(user.id),
            )
        assert ei.value.status_code == 403

    async def test_ok_with_camera_filter(self):
        cid = uuid.uuid4()
        cam = _camera(cid)
        det = _detection(cid, uuid.uuid4())
        db = _FakeSession([_FakeResult(one=cam), _FakeResult(items=[det])])
        out = await data_router.list_detections(
            region_id=None,
            camera_id=str(cid),
            db=db,
            user_id="not-a-uuid",
            limit=100,
            offset=0,
        )
        assert len(out) == 1

    async def test_ok_with_region_filter(self):
        rid = uuid.uuid4()
        det = _detection(uuid.uuid4(), uuid.uuid4())
        db = _FakeSession([_FakeResult(items=[det])])
        out = await data_router.list_detections(
            region_id=str(rid),
            camera_id=None,
            db=db,
            user_id="not-a-uuid",
            limit=10,
            offset=5,
        )
        assert len(out) == 1
        assert out[0]["confidence"] == 0.88


class TestListPlates:
    async def test_ok_with_search_and_dates(self):
        p = _plate(uuid.uuid4())
        db = _FakeSession([_FakeResult(items=[p])])
        out = await data_router.list_plates(
            q="MH12",
            date_from="2026-01-01T00:00:00Z",
            date_to="2026-12-31T00:00:00Z",
            region_id=None,
            region=None,
            camera_id=None,
            limit=100,
            offset=0,
            db=db,
            user_id="not-a-uuid",
        )
        assert len(out) == 1
        assert out[0]["plate_string"] == "MH12AB1234"

    async def test_invalid_dates_ignored(self):
        p = _plate(uuid.uuid4())
        db = _FakeSession([_FakeResult(items=[p])])
        out = await data_router.list_plates(
            date_from="not-a-date",
            date_to="also-bad",
            region_id=None,
            region=None,
            camera_id=None,
            q=None,
            limit=100,
            offset=0,
            db=db,
            user_id="not-a-uuid",
        )
        assert len(out) == 1

    async def test_region_and_camera_filters(self):
        rid, cid = uuid.uuid4(), uuid.uuid4()
        p = _plate(rid)
        db = _FakeSession([_FakeResult(items=[p])])
        out = await data_router.list_plates(
            region_id=str(rid),
            camera_id=str(cid),
            region=None,
            q=None,
            date_from=None,
            date_to=None,
            limit=100,
            offset=0,
            db=db,
            user_id="not-a-uuid",
        )
        assert len(out) == 1

    async def test_scoped_region_filter(self):
        user = _user()
        rid = uuid.uuid4()
        det = _detection(uuid.uuid4(), uuid.uuid4())
        db = _FakeSession(
            [
                _FakeResult(one=user),
                _FakeResult(items=[rid]),
                _FakeResult(items=[det]),
            ]
        )
        out = await data_router.list_detections(
            region_id=str(rid),
            camera_id=None,
            db=db,
            user_id=str(user.id),
            limit=100,
            offset=0,
        )
        assert len(out) == 1

    async def test_region_alias_with_search(self):
        rid = uuid.uuid4()
        p = _plate(rid)
        db = _FakeSession([_FakeResult(items=[p])])
        out = await data_router.list_plates(
            region=str(rid),
            q="MH12",
            region_id=None,
            camera_id=None,
            date_from=None,
            date_to=None,
            limit=100,
            offset=0,
            db=db,
            user_id="not-a-uuid",
        )
        assert len(out) == 1

    async def test_scoped_user_restricts_to_assignments(self):
        user = _user()
        rid = uuid.uuid4()
        p = _plate(rid)
        db = _FakeSession(
            [
                _FakeResult(one=user),
                _FakeResult(items=[rid]),
                _FakeResult(items=[p]),
            ]
        )
        out = await data_router.list_plates(
            region_id=None,
            region=None,
            camera_id=None,
            q=None,
            date_from=None,
            date_to=None,
            limit=100,
            offset=0,
            db=db,
            user_id=str(user.id),
        )
        assert len(out) == 1

    async def test_region_alias_param(self):
        rid = uuid.uuid4()
        p = _plate(rid)
        db = _FakeSession([_FakeResult(items=[p])])
        out = await data_router.list_plates(
            region=str(rid),
            region_id=None,
            camera_id=None,
            q=None,
            date_from=None,
            date_to=None,
            limit=100,
            offset=0,
            db=db,
            user_id="not-a-uuid",
        )
        assert len(out) == 1


class TestGetPlateDetail:
    async def test_not_found_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await data_router.get_plate_detail("nope", db=db, user_id="not-a-uuid")
        assert ei.value.status_code == 404

    async def test_forbidden_403(self):
        user = _user()
        plate = _plate(uuid.uuid4())
        db = _FakeSession(
            [
                _FakeResult(one=plate),
                _FakeResult(one=user),
                _FakeResult(items=[uuid.uuid4()]),
            ]
        )
        with pytest.raises(HTTPException) as ei:
            await data_router.get_plate_detail(
                str(plate.id), db=db, user_id=str(user.id)
            )
        assert ei.value.status_code == 403

    async def test_ok(self):
        plate = _plate(uuid.uuid4())
        db = _FakeSession([_FakeResult(one=plate)])
        out = await data_router.get_plate_detail(
            str(plate.id), db=db, user_id="not-a-uuid"
        )
        assert out["plate_string"] == "MH12AB1234"


class TestGetPlateEvents:
    async def test_plate_not_found_404(self):
        db = _FakeSession([_FakeResult(one=None)])
        with pytest.raises(HTTPException) as ei:
            await data_router.get_plate_events(
                "nope", limit=100, offset=0, db=db, user_id="not-a-uuid"
            )
        assert ei.value.status_code == 404

    async def test_ok_adds_timestamp_alias(self):
        plate = _plate(uuid.uuid4())
        det = _detection(uuid.uuid4(), plate.id)
        db = _FakeSession([_FakeResult(one=plate), _FakeResult(items=[det])])
        out = await data_router.get_plate_events(
            str(plate.id), limit=100, offset=0, db=db, user_id="not-a-uuid"
        )
        assert len(out) == 1
        assert out[0]["timestamp"] == "2026-01-02T03:04:05+00:00"

    async def test_non_datetime_timestamp_skipped(self):
        plate = _plate(uuid.uuid4())
        det = _detection(uuid.uuid4(), plate.id, frame_timestamp="not-a-datetime")
        db = _FakeSession([_FakeResult(one=plate), _FakeResult(items=[det])])
        out = await data_router.get_plate_events(
            str(plate.id), limit=100, offset=0, db=db, user_id="not-a-uuid"
        )
        assert "timestamp" not in out[0]
