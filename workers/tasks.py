"""Celery task queue application and task definitions."""

from celery import Celery

from api.config import settings

# Celery app configuration
app = Celery(
    "anpr",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 min hard limit
    task_soft_time_limit=25 * 60,  # 25 min soft limit (graceful shutdown)
    result_expires=3600,  # Expire results after 1 hour
)


@app.task(bind=True, max_retries=3)
def detect_batch(self, frames: list) -> dict:
    """
    Async task: detect plates in a batch of frames.

    Args:
        frames: List of frame dicts with image data, stream_id, timestamp.

    Returns:
        dict with detection results, write to DB via sync task.
    """
    try:
        # Stub: real implementation in Day 4
        return {"status": "ok", "frames_processed": len(frames)}
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@app.task(bind=True, max_retries=3)
def cleanup_old_detections(self, days: int = 30) -> dict:
    """
    Async task: clean up old detections older than N days.

    Args:
        days: Number of days to retain.

    Returns:
        dict with cleanup stats.
    """
    try:
        # Stub: real implementation in Day 4
        return {"status": "ok", "rows_deleted": 0}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
