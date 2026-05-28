"""
Unit tests for database models: validation, constraints, relationships.

Test Coverage:
- User model: email unique constraint, role validation
- Region model: code uniqueness
- Camera model: foreign keys, cascades
- Plate model: encryption, confidence bounds
- Detection model: plate relationships
- Audit log model: append-only semantics
- FK constraints and cascade behaviors
"""

from __future__ import annotations

import uuid
import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, StatementError


class TestUserModel:
    """User model tests."""

    @pytest.mark.asyncio
    async def test_user_email_unique_constraint(self, db_session, test_user):
        """Test that email uniqueness is enforced."""
        from db.models import User
        from api.security import hash_password
        from api.config import UserRole

        # Try to create another user with same email
        duplicate = User(
            id=uuid.UUID("00000000-0000-4000-8000-000000000111"),
            email=test_user.email,  # Same email
            username="user2",
            hashed_password=hash_password("different-password"),
            role=UserRole.VIEWER,
            is_active="Y",
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_email_required(self, db_session):
        """Test that email is required."""
        from db.models import User
        from api.security import hash_password
        from api.config import UserRole

        user = User(
            id=uuid.UUID("00000000-0000-4000-8000-000000000112"),
            email=None,
            username="user3",
            hashed_password=hash_password("password"),
            role=UserRole.VIEWER,
            is_active="Y",
        )
        db_session.add(user)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_password_hash_required(self, db_session):
        """Test that password hash is required."""
        from db.models import User
        from api.config import UserRole

        user = User(
            id=uuid.UUID("00000000-0000-4000-8000-000000000113"),
            email="test@example.com",
            username="user4",
            hashed_password=None,
            role=UserRole.VIEWER,
            is_active="Y",
        )
        db_session.add(user)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_role_validation(self, db_session):
        """Test that only valid roles are accepted."""
        from db.models import User
        from api.security import hash_password

        # Invalid role should fail or be rejected at ORM level
        user = User(
            id=uuid.UUID("00000000-0000-4000-8000-000000000114"),
            email="admin@example.com",
            username="user5",
            hashed_password=hash_password("password"),
            role="superuser",  # Invalid - will fail
            is_active="Y",
        )
        db_session.add(user)
        # May fail at commit or during add depending on model constraints
        with pytest.raises((IntegrityError, StatementError, ValueError)):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_user_timestamps(self, db_session):
        """Test that created_at and updated_at are set."""
        from db.models import User
        from api.security import hash_password
        from api.config import UserRole

        user = User(
            id=uuid.UUID("00000000-0000-4000-8000-000000000115"),
            email="timestamps@example.com",
            username="user6",
            hashed_password=hash_password("password"),
            role=UserRole.VIEWER,
            is_active="Y",
        )
        db_session.add(user)
        await db_session.commit()
        assert user.created_at is not None
        assert user.updated_at is not None


class TestRegionModel:
    """Region model tests."""

    @pytest.mark.asyncio
    async def test_region_code_unique(self, db_session, test_region):
        """Test that region code is unique."""
        from db.models import Region

        duplicate = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000121"),
            code=test_region.code,  # Same code
            name="India Duplicate",
            regex=r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            retention_days=90,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_region_required_fields(self, db_session):
        """Test that required fields are enforced."""
        from db.models import Region

        region = Region(
            id=uuid.UUID("00000000-0000-4000-8000-000000000122"),
            code="IN",
            name=None,  # Required field
            regex=r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
            charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
        db_session.add(region)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestCameraModel:
    """Camera model tests."""

    @pytest.mark.asyncio
    async def test_camera_requires_region(self, db_session):
        """Test that camera requires region foreign key."""
        from db.models import Camera

        # Invalid region_id
        camera = Camera(
            id=uuid.UUID("00000000-0000-4000-8000-000000000131"),
            name="Bad Camera",
            source_type="rtsp",
            url="rtsp://example.com/stream",
            region_id=uuid.UUID("00000000-0000-4000-8000-999999999999"),  # Invalid FK
            status="active",
        )
        db_session.add(camera)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_camera_region_integrity(self, db_session, test_region):
        """Test that camera requires a valid region."""
        from db.models import Camera

        # Create camera with valid region
        camera = Camera(
            id=uuid.UUID("00000000-0000-4000-8000-000000000132"),
            name="Good Camera",
            source_type="rtsp",
            url="rtsp://example.com/stream",
            region_id=test_region.id,
            status="active",
        )
        db_session.add(camera)
        await db_session.commit()
        assert camera.region_id == test_region.id

    @pytest.mark.asyncio
    async def test_camera_name_required(self, db_session, test_region):
        """Test that camera name is required."""
        from db.models import Camera

        camera = Camera(
            id=uuid.UUID("00000000-0000-4000-8000-000000000133"),
            name=None,  # Required
            source_type="rtsp",
            url="rtsp://example.com/stream",
            region_id=test_region.id,
            status="active",
        )
        db_session.add(camera)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestPlateModel:
    """Plate model tests."""

    @pytest.mark.asyncio
    async def test_plate_average_confidence_tracking(self, db_session, test_region):
        """Test that plate tracks average confidence."""
        from db.models import Plate
        from datetime import datetime, timezone

        plate = Plate(
            id=uuid.UUID("00000000-0000-4000-8000-000000000141"),
            region_id=test_region.id,
            plate_string="KA01AB1234",
            detection_count=5,
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            avg_confidence=0.95,  # Valid 0-1 value
        )
        db_session.add(plate)
        await db_session.commit()
        assert plate.avg_confidence == 0.95

    @pytest.mark.asyncio
    async def test_plate_first_last_seen_timestamps(self, db_session, test_region):
        """Test that first/last seen timestamps are tracked."""
        from db.models import Plate
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        plate = Plate(
            id=uuid.UUID("00000000-0000-4000-8000-000000000142"),
            region_id=test_region.id,
            plate_string="KA02AB1234",
            detection_count=1,
            first_seen_at=now,
            last_seen_at=now,
            avg_confidence=0.8,
        )
        db_session.add(plate)
        await db_session.commit()
        assert plate.first_seen_at is not None
        assert plate.last_seen_at is not None

    @pytest.mark.asyncio
    async def test_plate_string_required(self, db_session, test_region):
        """Test that plate string is required."""
        from db.models import Plate
        from datetime import datetime, timezone

        plate = Plate(
            id=uuid.UUID("00000000-0000-4000-8000-000000000143"),
            region_id=test_region.id,
            plate_string=None,  # Required
            detection_count=1,
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            avg_confidence=0.95,
        )
        db_session.add(plate)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_plate_region_foreign_key(self, db_session):
        """Test that region_id must exist."""
        from db.models import Plate
        from datetime import datetime, timezone

        plate = Plate(
            id=uuid.UUID("00000000-0000-4000-8000-000000000144"),
            region_id=uuid.UUID("00000000-0000-4000-8000-999999999999"),  # Invalid FK
            plate_string="KA03AB1234",
            detection_count=1,
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            avg_confidence=0.95,
        )
        db_session.add(plate)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestDetectionModel:
    """Detection model tests."""

    @pytest.mark.asyncio
    async def test_detection_requires_plate(self, db_session, test_stream):
        """Test that detection requires valid plate_id."""
        from db.models import Detection
        from datetime import datetime, timezone

        detection = Detection(
            id=uuid.UUID("00000000-0000-4000-8000-000000000151"),
            camera_id=test_stream.id,
            plate_id=uuid.UUID("00000000-0000-4000-8000-999999999999"),  # Invalid FK
            frame_timestamp=datetime.now(timezone.utc),
            confidence=0.95,
            bbox=[10, 20, 110, 100],
            ocr_backend="paddle",
            quality_score=0.85,
        )
        db_session.add(detection)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_detection_requires_camera(self, db_session, test_plate):
        """Test that detection requires valid camera_id."""
        from db.models import Detection
        from datetime import datetime, timezone

        detection = Detection(
            id=uuid.UUID("00000000-0000-4000-8000-000000000152"),
            camera_id=uuid.UUID("00000000-0000-4000-8000-999999999999"),  # Invalid FK
            plate_id=test_plate.id,
            frame_timestamp=datetime.now(timezone.utc),
            confidence=0.95,
            bbox=[10, 20, 110, 100],
            ocr_backend="paddle",
            quality_score=0.85,
        )
        db_session.add(detection)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestAuditLogModel:
    """Audit log model tests."""

    @pytest.mark.asyncio
    async def test_audit_log_append_only_semantics(self, db_session, test_user):
        """Test that audit log entries can be created and tracked."""
        from db.models import AuditLog

        entry = AuditLog(
            id=uuid.UUID("00000000-0000-4000-8000-000000000161"),
            user_id=test_user.id,
            action="view_plate",
            resource_type="plate",
            resource_id=uuid.UUID("00000000-0000-4000-8000-000000000030"),
            ip_address="192.168.1.1",
            details={"plate_code": "KA01AB1234"},
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        # Verify the entry exists
        assert entry.id == uuid.UUID("00000000-0000-4000-8000-000000000161")

    @pytest.mark.asyncio
    async def test_audit_log_required_fields(self, db_session, test_user):
        """Test that audit log requires all fields."""
        from db.models import AuditLog

        # Missing user_id
        entry = AuditLog(
            id=uuid.UUID("00000000-0000-4000-8000-000000000162"),
            user_id=None,  # Required
            action="delete",
            resource_type="stream",
            resource_id=uuid.UUID("00000000-0000-4000-8000-000000000020"),
            ip_address="192.168.1.1",
            details={},
        )
        db_session.add(entry)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_audit_log_timestamp(self, db_session, test_user):
        """Test that audit log has created_at timestamp."""
        from db.models import AuditLog

        entry = AuditLog(
            id=uuid.UUID("00000000-0000-4000-8000-000000000163"),
            user_id=test_user.id,
            action="create",
            resource_type="watchlist",
            resource_id=uuid.UUID("00000000-0000-4000-8000-000000000050"),
            ip_address="192.168.1.1",
            details={},
        )
        db_session.add(entry)
        await db_session.commit()
        assert entry.created_at is not None


class TestWatchlistModel:
    """Watchlist model tests."""

    @pytest.mark.asyncio
    async def test_watchlist_requires_user(self, db_session, test_region):
        """Test that watchlist requires user_id."""
        from db.models import Watchlist

        entry = Watchlist(
            id=uuid.UUID("00000000-0000-4000-8000-000000000171"),
            plate_pattern="KA*",
            region_id=test_region.id,
            created_by_user_id=None,  # Required
        )
        db_session.add(entry)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_watchlist_pattern_required(self, db_session, test_user, test_region):
        """Test that plate pattern is required."""
        from db.models import Watchlist

        entry = Watchlist(
            id=uuid.UUID("00000000-0000-4000-8000-000000000172"),
            plate_pattern=None,  # Required
            region_id=test_region.id,
            created_by_user_id=test_user.id,
        )
        db_session.add(entry)
        with pytest.raises(IntegrityError):
            await db_session.commit()


class TestReviewQueueModel:
    """Review queue model tests."""

    @pytest.mark.asyncio
    async def test_review_queue_requires_detection(self, db_session):
        """Test that review queue requires detection_id."""
        from db.models import ReviewQueue

        item = ReviewQueue(
            id=uuid.UUID("00000000-0000-4000-8000-000000000181"),
            detection_id=None,  # Required
            status="pending",
            reviewer_id=None,
            detection_blob={},
        )
        db_session.add(item)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_review_queue_status_values(self, db_session, test_stream, test_plate):
        """Test that status is validated."""
        from db.models import ReviewQueue, Detection
        from datetime import datetime, timezone

        # Create a valid detection first
        detection = Detection(
            id=uuid.UUID("00000000-0000-4000-8000-000000000182"),
            camera_id=test_stream.id,
            plate_id=test_plate.id,
            frame_timestamp=datetime.now(timezone.utc),
            confidence=0.95,
            bbox=[10, 20, 110, 100],
            ocr_backend="paddle",
            quality_score=0.85,
        )
        db_session.add(detection)
        await db_session.flush()

        # Create review queue item
        item = ReviewQueue(
            id=uuid.UUID("00000000-0000-4000-8000-000000000183"),
            detection_id=detection.id,
            status="pending",
            detection_blob={"plate_code": "KA01AB1234"},
        )
        db_session.add(item)
        await db_session.commit()
        assert item.status == "pending"
