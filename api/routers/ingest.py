"""Frame ingest endpoint for ANPR pipeline."""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
import base64
import logging

from workers.tasks import process_frame
from api.deps.auth import get_current_user
from api.deps import get_current_user_id
from api.crypto import encrypt_frame
from api.logging import audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    """Frame ingest request."""
    stream_id: str
    frame_b64_jpeg: str
    camera_id: str


class IngestResponse(BaseModel):
    """Ingest response with task ID."""
    task_id: str
    status: str = "queued"


@router.post("/frame", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_frame(
    request: IngestRequest,
    user_id: str = Depends(get_current_user_id),
) -> IngestResponse:
    """Enqueue frame for processing.

    Rate limit: 10 requests per minute per authenticated user

    Args:
        request: Frame data (stream_id, frame_b64_jpeg, camera_id)
        req: HTTP request for rate limiting
        user_id: Authenticated user (from JWT)

    Returns:
        Task ID for polling status (HTTP 202 Accepted)
    """
    try:
        # Validate and decode base64
        frame_bytes = base64.b64decode(request.frame_b64_jpeg)
    except Exception as e:
        logger.error(f"Invalid base64 frame: {e}")
        audit_logger.warning(
            "ingest_frame_invalid_format",
            extra={
                "action": "ingest_attempt",
                "resource": "ingest/frame",
                "status": 400,
            }
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid frame format")

    try:
        # Encrypt frame for Redis transmission
        encrypted_frame = encrypt_frame(frame_bytes)

        # Enqueue Celery task with encrypted frame
        task = process_frame.delay(request.stream_id, encrypted_frame, request.camera_id)
        logger.info(f"Enqueued frame task={task.id} stream={request.stream_id} user={user_id}")
        
        audit_logger.info(
            "frame_ingested",
            extra={
                "action": "frame_ingest",
                "resource": f"ingest/frame/{task.id}",
                "status": 202,
            }
        )
        
        return IngestResponse(task_id=task.id, status="queued")
    except Exception as e:
        logger.error(f"Failed to enqueue task: {e}")
        audit_logger.error(
            "ingest_frame_failed",
            extra={
                "action": "ingest_attempt",
                "resource": "ingest/frame",
                "status": 500,
            }
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enqueue task")


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, user_id: str = Depends(get_current_user_id)) -> dict:
    """Poll task status.

    Args:
        task_id: Celery task ID
        user_id: Authenticated user

    Returns:
        Task state, result, or error
    """
    try:
        task = process_frame.AsyncResult(task_id)
        result = {
            "task_id": task.id,
            "state": task.state,
            "result": task.result if task.state == "SUCCESS" else None,
        }
        if task.state == "FAILURE":
            result["error"] = str(task.info)
        
        audit_logger.info(
            "task_status_checked",
            extra={
                "action": "task_poll",
                "resource": f"ingest/task/{task_id}",
                "status": 200,
            }
        )
        
        return result
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        audit_logger.error(
            "task_status_failed",
            extra={
                "action": "task_poll",
                "resource": f"ingest/task/{task_id}",
                "status": 500,
            }
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get task status")
