"""Data endpoints for regions, cameras, detections, and plates."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import logging

from api.deps import get_db_session, get_current_user_id
from db.models import Region, Camera, Detection, Plate
from api.schemas.data import RegionOut, CameraOut, DetectionOut, PlateOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["data"])


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(db: AsyncSession = Depends(get_db_session)):
    """List all regions.

    Returns:
        List of regions with metadata
    """
    stmt = select(Region).order_by(Region.code)
    result = await db.execute(stmt)
    regions = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "code": r.code,
            "name": r.name,
            "regex": r.regex,
            "charset": r.charset,
            "retention_days": r.retention_days,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in regions
    ]


@router.get("/regions/{region_id}/cameras", response_model=list[CameraOut])
async def list_cameras_for_region(
    region_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List cameras for a specific region.

    Args:
        region_id: Region ID

    Returns:
        List of cameras in region
    """
    stmt = select(Camera).where(Camera.region_id == region_id).order_by(Camera.name)
    result = await db.execute(stmt)
    cameras = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "source_type": c.source_type,
            "url": c.url,
            "region_id": str(c.region_id),
            "latitude": c.latitude,
            "longitude": c.longitude,
            "last_heartbeat": c.last_heartbeat,
            "status": c.status,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in cameras
    ]


@router.get("/detections", response_model=list[DetectionOut])
async def list_detections(
    region_id: str | None = Query(None),
    camera_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_session),
):
    """List detections with optional filters.

    Args:
        region_id: Filter by region ID
        camera_id: Filter by camera ID
        limit: Maximum detections to return

    Returns:
        List of recent detections
    """
    conditions = []

    if camera_id:
        conditions.append(Detection.camera_id == camera_id)

    stmt = select(Detection)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Detection.frame_timestamp)).limit(limit)
    result = await db.execute(stmt)
    detections = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "camera_id": str(d.camera_id),
            "plate_id": str(d.plate_id),
            "frame_timestamp": d.frame_timestamp,
            "confidence": d.confidence,
            "bbox": d.bbox,
            "ocr_backend": d.ocr_backend,
            "quality_score": d.quality_score,
            "crop_url": d.crop_url,
            "frame_url": d.frame_url,
            "is_persisted": d.is_persisted,
            "tracking_id": d.tracking_id,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }
        for d in detections
    ]


@router.get("/plates", response_model=list[PlateOut])
async def list_plates(
    region_id: str | None = Query(None),
    camera_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db_session),
):
    """List plates with optional filters.

    Args:
        region_id: Filter by region ID
        camera_id: Filter by camera ID (detections)
        limit: Maximum plates to return

    Returns:
        List of detected plates
    """
    conditions = []

    if region_id:
        conditions.append(Plate.region_id == region_id)

    stmt = select(Plate)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Plate.last_seen_at)).limit(limit)
    result = await db.execute(stmt)
    plates = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "plate_string": p.plate_string,
            "region_id": str(p.region_id),
            "detection_count": p.detection_count,
            "first_seen_at": p.first_seen_at,
            "last_seen_at": p.last_seen_at,
            "avg_confidence": p.avg_confidence,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        }
        for p in plates
    ]
