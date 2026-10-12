"""Stream management endpoints.

Streams are backed by the Camera model (a stream is a camera/video source).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
import logging
from typing import Any
from uuid import UUID

from api.config import UserRole
from api.deps import get_db_session, get_current_user_id, require_role
from db.models import Camera, Detection, Region
from api.schemas.data import StreamIn, StreamOut, StreamListOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/streams", tags=["streams"])

# Role guard: only operators and admins may create/delete streams
manage_streams = require_role(UserRole.OPERATOR, UserRole.ADMIN)


def _parse_uuid_or_404(value: str, resource: str = "Stream") -> UUID:
    """Parse a UUID string, raising 404 for invalid values."""
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found",
        )


def _camera_to_stream_out(camera: Camera, stats: dict[str, Any] | None = None) -> StreamOut:
    """Convert a Camera ORM row to the stream response schema."""
    return StreamOut(
        id=str(camera.id),
        name=camera.name,
        rtsp_url=camera.url,
        region_id=str(camera.region_id),
        status=camera.status,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
        stats=stats,
    )


async def _stream_stats(camera_id: UUID, db: AsyncSession) -> dict[str, Any]:
    """Compute basic stats for a stream."""
    stmt = select(func.count()).where(Detection.stream_id == camera_id)
    result = await db.execute(stmt)
    detection_count = result.scalar_one()
    return {"detection_count": detection_count}


@router.get("", response_model=StreamListOut)
async def list_streams(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> StreamListOut:
    """List streams (paginated).

    Args:
        limit: Maximum streams to return
        offset: Pagination offset
        db: Database session
        user_id: Current user ID

    Returns:
        Paginated list of streams
    """
    total_stmt = select(func.count()).select_from(Camera)
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = select(Camera).order_by(Camera.name).limit(limit).offset(offset)
    result = await db.execute(stmt)
    cameras = result.scalars().all()

    return StreamListOut(
        items=[_camera_to_stream_out(c) for c in cameras],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StreamOut, status_code=status.HTTP_201_CREATED)
async def create_stream(
    data: StreamIn,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    _role: UserRole = Depends(manage_streams),
) -> StreamOut:
    """Create a new stream.

    Args:
        data: Stream data (name, rtsp_url, region_id)
        db: Database session
        user_id: Current user ID

    Returns:
        Created stream
    """
    try:
        region_uuid = UUID(str(data.region_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid region_id format",
        )

    stmt = select(Region).where(Region.id == region_uuid)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found",
        )

    camera = Camera(
        name=data.name,
        source_type="rtsp",
        url=data.rtsp_url,
        region_id=region_uuid,
        status="active",
    )
    db.add(camera)
    try:
        await db.commit()
        await db.refresh(camera)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create stream: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create stream",
        )

    return _camera_to_stream_out(camera, stats={"detection_count": 0})


@router.get("/{stream_id}", response_model=StreamOut)
async def get_stream(
    stream_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> StreamOut:
    """Get stream detail including stats.

    Args:
        stream_id: Stream ID
        db: Database session
        user_id: Current user ID

    Returns:
        Stream detail with stats
    """
    camera_uuid = _parse_uuid_or_404(stream_id)
    stmt = select(Camera).where(Camera.id == camera_uuid)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not found",
        )

    stats = await _stream_stats(camera_uuid, db)
    return _camera_to_stream_out(camera, stats=stats)


@router.delete("/{stream_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stream(
    stream_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    _role: UserRole = Depends(manage_streams),
) -> None:
    """Delete a stream, cascading to its detections.

    Args:
        stream_id: Stream ID
        db: Database session
        user_id: Current user ID
    """
    camera_uuid = _parse_uuid_or_404(stream_id)
    stmt = select(Camera).where(Camera.id == camera_uuid)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not found",
        )

    # Cascade: remove detections recorded for this stream
    await db.execute(delete(Detection).where(Detection.stream_id == camera_uuid))
    await db.delete(camera)
    await db.commit()
