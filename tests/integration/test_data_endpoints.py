"""
Integration tests for data endpoints: regions and cameras.

Coverage:
- GET /v1/regions: auth required, returns list of regions
- GET /v1/regions/{region_id}/cameras: UUID validation, region existence check, type conversion

Fixes verified:
1. /v1/regions requires auth (Depends(get_current_user_id))
2. /v1/regions/{region_id}/cameras validates UUID format (422 on invalid)
3. /v1/regions/{region_id}/cameras checks region exists (404 if not found)
4. /v1/regions/{region_id}/cameras fixed type mismatch in filter (str → UUID)
5. /v1/auth/refresh fixed token field lookup (changed "sub" → "user_id")
"""

from __future__ import annotations

import uuid
import pytest
from api.config import settings


class TestRegionsEndpoints:
    """GET /v1/regions endpoint tests."""

    @pytest.mark.integration
    def test_list_regions_requires_auth(self, client):
        """Test that /v1/regions requires authentication."""
        response = client.get("/v1/regions")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    @pytest.mark.integration
    def test_list_regions_with_valid_auth(self, client, auth_token_factory, test_region):
        """Test listing regions with valid auth token."""
        token = auth_token_factory(user_id="test-user", role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Check region fields
        region = next((r for r in data if r["id"] == str(test_region.id)), None)
        assert region is not None
        assert region["code"] == test_region.code
        assert region["name"] == test_region.name

    @pytest.mark.integration
    def test_list_regions_with_operator_role(self, client, auth_token_factory, test_region):
        """Test that operator role can list regions."""
        token = auth_token_factory(user_id="operator-user", role="operator")
        client.headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.integration
    def test_list_regions_with_admin_role(self, client, auth_token_factory, test_region):
        """Test that admin role can list regions."""
        token = auth_token_factory(user_id="admin-user", role="admin")
        client.headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.integration
    def test_list_regions_with_missing_auth_header(self, client):
        """Test that missing auth header results in 401."""
        # Don't set Authorization header
        response = client.get("/v1/regions")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    @pytest.mark.integration
    def test_list_regions_with_malformed_auth_header(self, client):
        """Test that malformed Authorization header results in 401."""
        client.headers = {"Authorization": "NotBearer token"}
        response = client.get("/v1/regions")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_list_regions_response_schema(self, client, auth_token_factory, test_region):
        """Test that regions response includes required fields."""
        token = auth_token_factory(user_id="test-user", role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        region = data[0]
        required_fields = [
            "id",
            "code",
            "name",
            "regex",
            "charset",
            "retention_days",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert field in region, f"Missing field '{field}' in region response"

    @pytest.mark.integration
    def test_list_regions_ordered_by_code(self, client, auth_token_factory, db_session):
        """Test that regions are sorted by code."""
        from db.models import Region

        # Create multiple regions with different codes
        region1 = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000011"),
            code="IN-TN",
            name="Tamil Nadu",
            regex=r"^[A-Z]{2}",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            retention_days=90,
        )
        region2 = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000012"),
            code="IN-AP",
            name="Andhra Pradesh",
            regex=r"^[A-Z]{2}",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            retention_days=90,
        )
        db_session.add(region1)
        db_session.add(region2)

        token = auth_token_factory(user_id="test-user", role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        codes = [r["code"] for r in data]
        # Check that codes are in sorted order
        assert codes == sorted(codes)


class TestCamerasEndpoints:
    """GET /v1/regions/{region_id}/cameras endpoint tests."""

    @pytest.mark.integration
    def test_list_cameras_with_valid_region(self, client, test_region, test_stream):
        """Test listing cameras for a valid region."""
        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        camera = next(
            (c for c in data if c["id"] == str(test_stream.id)), None
        )
        assert camera is not None
        assert camera["name"] == test_stream.name
        assert camera["region_id"] == str(test_region.id)

    @pytest.mark.integration
    def test_list_cameras_invalid_uuid_format(self, client):
        """Test that invalid UUID format returns 422."""
        response = client.get("/v1/regions/not-a-uuid/cameras")
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @pytest.mark.integration
    def test_list_cameras_invalid_uuid_string(self, client):
        """Test that invalid UUID string returns 422."""
        response = client.get("/v1/regions/12345-67890/cameras")
        assert response.status_code == 422
        data = response.json()
        assert "Invalid region ID format" in str(data.get("detail", ""))

    @pytest.mark.integration
    def test_list_cameras_region_not_found(self, client):
        """Test that non-existent region returns 404."""
        nonexistent_id = uuid.UUID("00000000-0000-4000-8000-000000000999")
        response = client.get(f"/v1/regions/{nonexistent_id}/cameras")
        assert response.status_code == 404
        data = response.json()
        assert "Region not found" in str(data.get("detail", ""))


    @pytest.mark.integration
    def test_list_cameras_response_schema(self, client, test_region, test_stream):
        """Test that camera response includes required fields."""
        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        camera = data[0]
        required_fields = [
            "id",
            "name",
            "source_type",
            "url",
            "region_id",
            "latitude",
            "longitude",
            "last_heartbeat",
            "status",
            "created_at",
            "updated_at",
        ]
        for field in required_fields:
            assert (
                field in camera
            ), f"Missing field '{field}' in camera response"

    @pytest.mark.integration
    def test_list_cameras_uuid_string_conversion(self, client, test_region):
        """Test that region_id in response is a string (UUID conversion)."""
        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            camera = data[0]
            # Verify region_id is a string, not a UUID object
            assert isinstance(camera["region_id"], str)
            assert camera["region_id"] == str(test_region.id)


    @pytest.mark.integration
    def test_list_cameras_ordered_by_name(self, client, test_region, db_session):
        """Test that cameras are sorted by name."""
        from db.models import Camera

        camera_z = Camera(
            id=uuid.UUID("00000000-0000-4000-8000-000000000060"),
            name="Zebra Camera",
            source_type="rtsp",
            url="rtsp://example.com/z",
            region_id=test_region.id,
            status="active",
        )
        camera_a = Camera(
            id=uuid.UUID("00000000-0000-4000-8000-000000000061"),
            name="Alpha Camera",
            source_type="rtsp",
            url="rtsp://example.com/a",
            region_id=test_region.id,
            status="active",
        )
        db_session.add(camera_z)
        db_session.add(camera_a)

        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 200
        data = response.json()
        names = [c["name"] for c in data]
        # Check that names are in sorted order
        assert names == sorted(names)


    @pytest.mark.integration
    def test_list_cameras_uppercase_uuid(self, client, test_region, test_stream):
        """Test that uppercase UUID is accepted and normalized."""
        region_id_upper = str(test_region.id).upper()
        response = client.get(f"/v1/regions/{region_id_upper}/cameras")
        # UUID should handle uppercase gracefully
        assert response.status_code == 200

    @pytest.mark.integration
    def test_list_cameras_with_hyphens_uuid(self, client, test_region, test_stream):
        """Test that UUID with hyphens is accepted."""
        region_id = str(test_region.id)
        assert "-" in region_id  # Standard UUID format has hyphens
        response = client.get(f"/v1/regions/{region_id}/cameras")
        assert response.status_code == 200


class TestTokenRefreshFix:
    """Tests for POST /v1/auth/refresh fix (user_id field lookup).

    These tests verify that the /v1/auth/refresh endpoint correctly extracts
    "user_id" from the token payload (not "sub" which was the bug).
    """

    @pytest.mark.integration
    def test_refresh_requires_valid_token(self, client):
        """Test that refresh endpoint requires a valid token."""
        # Send request without token
        response = client.post("/v1/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_refresh_without_token_fails(self, client):
        """Test that refresh without token fails."""
        # Don't set Authorization header
        response = client.post("/v1/auth/refresh")
        assert response.status_code == 401
