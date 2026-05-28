"""Celery task definitions."""
import base64
import io
import logging
import time
from typing import Any

import cv2
import numpy as np

from anpr_core.pipeline.orchestrator import ANPROrchestrator
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Global orchestrator instance (lazy-loaded on first task)
_orchestrator: ANPROrchestrator | None = None


def _get_orchestrator() -> ANPROrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        logger.info("Initializing ANPROrchestrator...")
        _orchestrator = ANPROrchestrator(use_gpu=True, device="auto")
        logger.info("✓ ANPROrchestrator ready")
    return _orchestrator


@celery_app.task(name="process_frame", bind=True)
def process_frame(self: Any, stream_id: str, frame_bytes_b64: str, camera_id: str) -> dict:
    """
    Process a frame through the ANPR pipeline (M2–M5).

    Args:
        stream_id: Stream identifier
        frame_bytes_b64: Frame bytes as base64
        camera_id: Camera identifier

    Returns:
        Dictionary with:
        - status: "success" | "error"
        - detections: list of {track_id, text, conf, region, should_persist, reasons}
        - frame_id: Frame number
        - timestamp: Processing timestamp
        - latency_ms: Total pipeline latency
        - error: Error message (if status="error")
    """
    task_start = time.time()

    try:
        # Decode frame
        frame_bytes = base64.b64decode(frame_bytes_b64)
        frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        image = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)

        if image is None:
            logger.error(f"Failed to decode frame from stream {stream_id}")
            return {
                "status": "error",
                "error": "Failed to decode frame",
                "frame_id": None,
                "timestamp": time.time(),
                "latency_ms": (time.time() - task_start) * 1000,
            }

        # Get orchestrator
        orchestrator = _get_orchestrator()

        # Process frame
        pipeline_output = orchestrator.process_frame(
            image=image,
            frame_id=None,
            timestamp=time.time(),
        )

        # Format output for WebSocket + storage
        detections = []
        for det in pipeline_output.detections:
            detections.append(
                {
                    "track_id": det.track_id,
                    "bbox": det.bbox,
                    "text": det.plate_text,
                    "confidence": det.plate_confidence,
                    "char_confidences": det.char_confidences,
                    "region": det.region,
                    "should_persist": det.should_persist,
                    "reject_reasons": det.reject_reasons,
                    "postproc_fixes": det.postproc_fixes,
                }
            )

        return {
            "status": "success",
            "stream_id": stream_id,
            "camera_id": camera_id,
            "frame_id": pipeline_output.frame_id,
            "timestamp": pipeline_output.timestamp,
            "num_raw_detections": pipeline_output.num_raw_detections,
            "num_passed_quality": pipeline_output.num_passed_quality,
            "num_tracked": pipeline_output.num_tracked,
            "num_persisted": pipeline_output.num_persisted,
            "detections": detections,
            "latency_ms": (time.time() - task_start) * 1000,
        }

    except Exception as e:
        logger.error(f"process_frame error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "stream_id": stream_id,
            "camera_id": camera_id,
            "frame_id": None,
            "timestamp": time.time(),
            "latency_ms": (time.time() - task_start) * 1000,
        }


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
