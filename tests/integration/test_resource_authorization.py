"""
Integration tests for resource-based authorization in data endpoints.

Coverage:
- User region assignments control access to regions, cameras, detections, plates
- Unauthorized users (no assignments) receive 403 Forbidden
- Users can only query data from assigned regions
- Authorization checks on all data endpoints
"""

from __future__ import annotations

import uuid
import pytest


class TestResourceAuthorization:
    """Test resource-based access control."""

    @pytest.mark.integration
    async def test_list_regions_requires_assignment(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that users with no region assignments cannot list regions."""
        # User has no region assignments yet
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/regions")
        assert response.status_code == 403
        data = response.json()
        assert "does not have access to any regions" in data["detail"]

    @pytest.mark.integration
    async def test_list_regions_with_assignment(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that assigned users can list regions."""
        from db.models import UserRegionAssignment

        # Grant user access to region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        region = next((r for r in data if r["id"] == str(test_region.id)), None)
        assert region is not None

    @pytest.mark.integration
    async def test_list_regions_only_assigned(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that users only see assigned regions."""
        from db.models import Region, UserRegionAssignment

        # Create a second region user doesn't have access to
        other_region = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000011"),
            code="IN-TN",
            name="Tamil Nadu",
            regex=r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            retention_days=90,
        )
        db_session.add(other_region)

        # Grant user access to only test_region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        # Should only see test_region, not other_region
        region_ids = [r["id"] for r in data]
        assert str(test_region.id) in region_ids
        assert str(other_region.id) not in region_ids

    @pytest.mark.integration
    async def test_list_cameras_requires_region_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, db_session
    ):
        """Test that users without region access cannot list cameras."""
        # User has no region assignments
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 403
        data = response.json()
        assert "does not have access to this region" in data["detail"]

    @pytest.mark.integration
    async def test_list_cameras_with_region_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, db_session
    ):
        """Test that users with region access can list cameras."""
        from db.models import UserRegionAssignment

        # Grant user access to region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/regions/{test_region.id}/cameras")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        camera = next((c for c in data if c["id"] == str(test_stream.id)), None)
        assert camera is not None

    @pytest.mark.integration
    async def test_get_camera_requires_region_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, db_session
    ):
        """Test that users without region access cannot get camera."""
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/cameras/{test_stream.id}")
        assert response.status_code == 403
        data = response.json()
        assert "does not have access" in data["detail"]

    @pytest.mark.integration
    async def test_get_camera_with_region_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, db_session
    ):
        """Test that users with region access can get camera."""
        from db.models import UserRegionAssignment

        # Grant user access to region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/cameras/{test_stream.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_stream.id)
        assert data["region_id"] == str(test_region.id)

    @pytest.mark.integration
    async def test_list_detections_requires_auth(
        self, client, test_region, db_session
    ):
        """Test that /v1/detections requires authentication."""
        response = client.get("/v1/detections")
        assert response.status_code == 401

    @pytest.mark.integration
    async def test_list_detections_requires_region_access(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that users without region access cannot list detections."""
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/detections")
        assert response.status_code == 403

    @pytest.mark.integration
    async def test_list_detections_with_region_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, test_plate, db_session
    ):
        """Test that users with region access can list detections."""
        from db.models import UserRegionAssignment, Detection
        from datetime import datetime, timezone

        # Grant user access to region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)

        # Create a detection
        detection = Detection(
            id=uuid.UUID("00000000-0000-4000-8000-000000000040"),
            camera_id=test_stream.id,
            plate_id=test_plate.id,
            frame_timestamp=datetime.now(timezone.utc),
            confidence=0.95,
            bbox=[0, 0, 100, 100],
            ocr_backend="paddle",
            quality_score=0.9,
        )
        db_session.add(detection)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/detections")
        assert response.status_code == 200
        data = response.json()
        # Verify detection is in response
        assert len(data) >= 1
        det = next((d for d in data if d["id"] == str(detection.id)), None)
        assert det is not None

    @pytest.mark.integration
    async def test_list_detections_by_camera_requires_access(
        self, client, auth_token_factory, test_user, test_region, test_stream, db_session
    ):
        """Test that filtering by camera still requires region access."""
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/detections?camera_id={test_stream.id}")
        assert response.status_code == 403

    @pytest.mark.integration
    async def test_list_plates_requires_auth(
        self, client, test_region, db_session
    ):
        """Test that /v1/plates requires authentication."""
        response = client.get("/v1/plates")
        assert response.status_code == 401

    @pytest.mark.integration
    async def test_list_plates_requires_region_access(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that users without region access cannot list plates."""
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/plates")
        assert response.status_code == 403

    @pytest.mark.integration
    async def test_list_plates_with_region_access(
        self, client, auth_token_factory, test_user, test_region, test_plate, db_session
    ):
        """Test that users with region access can list plates."""
        from db.models import UserRegionAssignment

        # Grant user access to region
        assignment = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        db_session.add(assignment)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/plates")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        plate = next((p for p in data if p["id"] == str(test_plate.id)), None)
        assert plate is not None

    @pytest.mark.integration
    async def test_list_plates_by_region_requires_access(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that filtering by region still requires access."""
        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get(f"/v1/plates?region_id={test_region.id}")
        assert response.status_code == 403

    @pytest.mark.integration
    async def test_multi_region_access(
        self, client, auth_token_factory, test_user, test_region, db_session
    ):
        """Test that users with multiple region assignments see all assigned regions."""
        from db.models import Region, UserRegionAssignment

        # Create second region
        region2 = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000012"),
            code="IN-AP",
            name="Andhra Pradesh",
            regex=r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            retention_days=90,
        )
        db_session.add(region2)

        # Grant access to both regions
        assignment1 = UserRegionAssignment(
            user_id=test_user.id,
            region_id=test_region.id,
            role="viewer",
        )
        assignment2 = UserRegionAssignment(
            user_id=test_user.id,
            region_id=region2.id,
            role="operator",
        )
        db_session.add(assignment1)
        db_session.add(assignment2)
        await db_session.commit()

        token = auth_token_factory(user_id=str(test_user.id), role="viewer")
        client.headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/v1/regions")
        assert response.status_code == 200
        data = response.json()
        region_ids = [r["id"] for r in data]
        assert str(test_region.id) in region_ids
        assert str(region2.id) in region_ids
        assert len(data) == 2
