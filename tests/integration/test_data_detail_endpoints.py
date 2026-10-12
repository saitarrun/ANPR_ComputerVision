"""Integration tests for data router detail endpoints and filters."""

import pytest


def _auth(client, auth_token_factory, test_user):
    token = auth_token_factory(user_id=str(test_user.id), role="viewer")
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


@pytest.fixture
async def region_access(db_session, test_user, test_region):
    from db.models import UserRegionAssignment

    db_session.add(
        UserRegionAssignment(user_id=test_user.id, region_id=test_region.id, role="viewer")
    )
    await db_session.commit()


class TestCameraDetail:
    def test_get_camera(self, client, auth_token_factory, test_user, test_stream, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get(f"/v1/cameras/{test_stream.id}")
        assert r.status_code == 200
        assert r.json()["id"] == str(test_stream.id)

    def test_get_camera_not_found(self, client, auth_token_factory, test_user, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/cameras/00000000-0000-4000-8000-000000009999")
        assert r.status_code == 404

    def test_get_camera_invalid_uuid(self, client, auth_token_factory, test_user, region_access):
        _auth(client, auth_token_factory, test_user)
        assert client.get("/v1/cameras/not-a-uuid").status_code == 404

    def test_get_camera_no_auth(self, client, test_stream):
        assert client.get(f"/v1/cameras/{test_stream.id}").status_code == 401


class TestPlateDetail:
    def test_get_plate(self, client, auth_token_factory, test_user, test_plate, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get(f"/v1/plates/{test_plate.id}")
        assert r.status_code == 200
        assert r.json()["plate_string"] == "KA01AB1234"

    def test_get_plate_not_found(self, client, auth_token_factory, test_user, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/plates/00000000-0000-4000-8000-000000009999")
        assert r.status_code == 404

    def test_get_plate_events(
        self, client, auth_token_factory, test_user, test_plate, region_access
    ):
        _auth(client, auth_token_factory, test_user)
        r = client.get(f"/v1/plates/{test_plate.id}/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_plate_events_not_found(self, client, auth_token_factory, test_user, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/plates/00000000-0000-4000-8000-000000009999/events")
        assert r.status_code == 404


class TestPlateFilters:
    def test_filter_by_q(self, client, auth_token_factory, test_user, test_plate, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/plates?q=KA01")
        assert r.status_code == 200
        assert any(p["plate_string"] == "KA01AB1234" for p in r.json())

    def test_filter_by_q_no_match(
        self, client, auth_token_factory, test_user, test_plate, region_access
    ):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/plates?q=ZZZZZZ")
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_by_region_alias(
        self,
        client,
        auth_token_factory,
        test_user,
        test_plate,
        test_region,
        region_access,
    ):
        _auth(client, auth_token_factory, test_user)
        r = client.get(f"/v1/plates?region={test_region.id}")
        assert r.status_code == 200

    def test_pagination(self, client, auth_token_factory, test_user, test_plate, region_access):
        _auth(client, auth_token_factory, test_user)
        r = client.get("/v1/plates?limit=1&offset=0")
        assert r.status_code == 200
        assert len(r.json()) <= 1


class TestRegionAccessEnforcement:
    """403 paths for DB users without region assignments."""

    def test_list_plates_no_region_access(self, client, auth_token_factory, test_user, test_plate):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/v1/plates")
        assert r.status_code == 403

    def test_get_plate_no_region_access(self, client, auth_token_factory, test_user, test_plate):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/v1/plates/{test_plate.id}")
        assert r.status_code == 403

    def test_list_detections_no_region_access(self, client, auth_token_factory, test_user):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/v1/detections")
        assert r.status_code == 403


class TestPlateDateFilters:
    def test_filter_from_date(
        self, client, auth_token_factory, test_user, test_plate, region_access
    ):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/v1/plates?from=2020-01-01T00:00:00Z")
        assert r.status_code == 200

    def test_filter_to_date(self, client, auth_token_factory, test_user, test_plate, region_access):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/v1/plates?to=2030-01-01T00:00:00Z")
        assert r.status_code == 200
        assert any(p["plate_string"] == "KA01AB1234" for p in r.json())

    def test_filter_invalid_date_ignored(
        self, client, auth_token_factory, test_user, test_plate, region_access
    ):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get("/v1/plates?from=not-a-date")
        assert r.status_code == 200

    def test_filter_by_camera_id(
        self,
        client,
        auth_token_factory,
        test_user,
        test_plate,
        test_stream,
        region_access,
    ):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/v1/plates?camera_id={test_stream.id}")
        assert r.status_code == 200

    def test_filter_by_region_id_param(
        self,
        client,
        auth_token_factory,
        test_user,
        test_plate,
        test_region,
        region_access,
    ):
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        r = client.get(f"/v1/plates?region_id={test_region.id}")
        assert r.status_code == 200
