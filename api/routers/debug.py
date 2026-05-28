"""Debug endpoints for testing (dev only)."""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from api.config import settings
from api.deps import get_current_user_id
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/debug", tags=["debug"])


@router.post("/publish-test-detection/{stream_id}")
async def publish_test_detection(
    stream_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Publish a test detection to Redis (for WebSocket testing).

    Args:
        stream_id: Stream ID to publish to
        user_id: Authenticated user

    Returns:
        Published detection
    """
    try:
        import redis.asyncio as aioredis

        redis = await aioredis.from_url(settings.redis_url)

        detection = {
            "id": str(uuid.uuid4()),
            "camera_id": stream_id.replace("camera-", ""),
            "plate_id": str(uuid.uuid4()),
            "frame_timestamp": datetime.now().isoformat(),
            "confidence": 0.95,
            "bbox": {"x1": 100, "y1": 100, "x2": 200, "y2": 150},
            "ocr_backend": "paddle",
            "quality_score": 0.92,
            "crop_url": None,
            "frame_url": None,
            "is_persisted": "Y",
            "tracking_id": "track-001",
        }

        # Publish to Redis
        channel = f"detections:{stream_id}"
        await redis.publish(channel, json.dumps(detection))
        await redis.close()

        logger.info(f"Published test detection to {channel}")
        return {"published": True, "detection": detection}
    except Exception as e:
        logger.error(f"Failed to publish test detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))
