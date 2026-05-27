"""Celery task definitions."""
from workers.celery_app import celery_app


@celery_app.task(name="process_frame")
def process_frame(stream_id: str, frame_bytes_b64: str, camera_id: str) -> dict:
    """Process a frame through the ANPR pipeline.

    Args:
        stream_id: Stream identifier
        frame_bytes_b64: Frame bytes as base64
        camera_id: Camera identifier

    Returns:
        Detection results
    """
    # Implemented by ml-engineer in M3-M5
    raise NotImplementedError("ML engineer will implement inference")


@celery_app.task(name="check_watchlist_match")
def check_watchlist_match(plate_id: str) -> dict:
    """Check if detected plate matches any watchlist entries.

    Args:
        plate_id: Plate identifier

    Returns:
        Watchlist match details
    """
    # TODO: Implement watchlist matching
    return {"matched": False}


@celery_app.task(name="purge_expired_detections")
def purge_expired_detections() -> dict:
    """Nightly task: purge old detections per retention policy.

    Returns:
        Purge stats
    """
    # TODO: Implement retention-based purge
    return {"deleted_count": 0}


@celery_app.task(name="archive_audit_log_to_s3")
def archive_audit_log_to_s3() -> dict:
    """Nightly task: export audit log to S3, then delete old records.

    Returns:
        Archive stats
    """
    # TODO: Implement audit log archival
    return {"archived_count": 0}
