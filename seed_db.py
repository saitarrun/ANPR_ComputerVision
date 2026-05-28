"""Database seeding for testing."""

import asyncio
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.engine import AsyncSessionLocal, init_db
from db.models import Region, Camera, Plate, Detection, User
from api.security import hash_password


async def seed_database():
    """Seed database with test data."""
    await init_db()

    async with AsyncSessionLocal() as session:
        # Create regions
        regions = [
            Region(
                id=str(uuid.uuid4()),
                code="IN-KA",
                name="Karnataka, India",
                regex=r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$",
                charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                retention_days=90,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Region(
                id=str(uuid.uuid4()),
                code="US-CA",
                name="California, USA",
                regex=r"^[A-Z0-9]{7}$",
                charset="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                retention_days=90,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        for region in regions:
            session.add(region)

        await session.flush()

        # Create test user
        from api.config import UserRole
        user = User(
            id=uuid.uuid4(),
            email="test@example.com",
            username="testuser",
            hashed_password=hash_password("password123"),
            role=UserRole.OPERATOR,
            is_active="Y",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(user)
        await session.flush()

        # Create cameras
        cameras = [
            Camera(
                id=str(uuid.uuid4()),
                name="Highway Cam 1",
                source_type="rtsp",
                url="rtsp://example.com/stream1",
                region_id=regions[0].id,
                latitude=12.9716,
                longitude=77.5946,
                status="active",
                last_heartbeat=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Camera(
                id=str(uuid.uuid4()),
                name="Street Cam 2",
                source_type="rtsp",
                url="rtsp://example.com/stream2",
                region_id=regions[0].id,
                latitude=12.9750,
                longitude=77.5900,
                status="active",
                last_heartbeat=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Camera(
                id=str(uuid.uuid4()),
                name="Interstate 5",
                source_type="rtsp",
                url="rtsp://example.com/stream3",
                region_id=regions[1].id,
                latitude=34.0522,
                longitude=-118.2437,
                status="active",
                last_heartbeat=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        for camera in cameras:
            session.add(camera)

        await session.flush()

        # Create plates
        plates = [
            Plate(
                id=str(uuid.uuid4()),
                plate_string="KA01AB1234",
                region_id=regions[0].id,
                detection_count=5,
                first_seen_at=datetime.now() - timedelta(hours=2),
                last_seen_at=datetime.now() - timedelta(minutes=30),
                avg_confidence=0.94,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Plate(
                id=str(uuid.uuid4()),
                plate_string="KA02CD5678",
                region_id=regions[0].id,
                detection_count=3,
                first_seen_at=datetime.now() - timedelta(hours=1),
                last_seen_at=datetime.now(),
                avg_confidence=0.91,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Plate(
                id=str(uuid.uuid4()),
                plate_string="5ABC123",
                region_id=regions[1].id,
                detection_count=2,
                first_seen_at=datetime.now() - timedelta(minutes=15),
                last_seen_at=datetime.now() - timedelta(minutes=10),
                avg_confidence=0.88,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        for plate in plates:
            session.add(plate)

        await session.flush()

        # Create detections
        detections = [
            Detection(
                id=str(uuid.uuid4()),
                camera_id=cameras[0].id,
                plate_id=plates[0].id,
                frame_timestamp=datetime.now() - timedelta(hours=1),
                confidence=0.96,
                bbox={"x1": 100, "y1": 50, "x2": 250, "y2": 150},
                ocr_backend="paddle",
                quality_score=0.95,
                crop_url="s3://anpr-crops/crop-001.jpg",
                frame_url="s3://anpr-frames/frame-001.jpg",
                is_persisted="Y",
                tracking_id="track-001",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            Detection(
                id=str(uuid.uuid4()),
                camera_id=cameras[1].id,
                plate_id=plates[1].id,
                frame_timestamp=datetime.now() - timedelta(minutes=45),
                confidence=0.91,
                bbox={"x1": 120, "y1": 60, "x2": 280, "y2": 160},
                ocr_backend="crnn",
                quality_score=0.89,
                crop_url="s3://anpr-crops/crop-002.jpg",
                frame_url="s3://anpr-frames/frame-002.jpg",
                is_persisted="Y",
                tracking_id="track-002",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]

        for detection in detections:
            session.add(detection)

        await session.commit()
        print("✓ Database seeded successfully")
        print(f"  - {len(regions)} regions")
        print(f"  - {len(cameras)} cameras")
        print(f"  - {len(plates)} plates")
        print(f"  - {len(detections)} detections")
        print(f"  - 1 test user: test@example.com / password123")


if __name__ == "__main__":
    asyncio.run(seed_database())
