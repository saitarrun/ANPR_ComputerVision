"""Data endpoints for regions, cameras, detections, and plates."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import logging
from typing import Any
import re
from uuid import UUID
from datetime import datetime

from api.deps import get_db_session, get_current_user_id
from db.models import Region, Camera, Detection, Plate, User, UserRegionAssignment
from api.schemas.data import RegionOut, CameraOut, DetectionOut, PlateOut

logger = logging.getLogger(__name__)


def validate_uuid(uuid_string: str, field_name: str) -> UUID:
    """Validate and convert string to UUID.

    Args:
        uuid_string: String to validate
        field_name: Field name for error messages (e.g., 'region ID', 'camera ID')

    Returns:
        Valid UUID object

    Raises:
        HTTPException: 422 if not a valid UUID
    """
    try:
        return UUID(uuid_string)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name} format",
        )


def _parse_uuid_or_none(value: str | None) -> UUID | None:
    """Parse a UUID string, returning None for missing/invalid values."""
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def _scoped_region_ids(user_id: str, db: AsyncSession) -> list[UUID] | None:
    """Resolve the region IDs a subject is allowed to access.

    Returns:
        - None: the subject is not a database user (e.g. a service/test token).
          Such subjects keep unscoped read access (legacy behavior).
        - A (possibly empty) list of assigned region IDs for database users.

    Callers treat an empty list as "no access" and raise 403.
    """
    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        return None

    user_stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(user_stmt)
    if result.scalar_one_or_none() is None:
        return None

    assign_stmt = select(UserRegionAssignment.region_id).where(
        UserRegionAssignment.user_id == user_uuid
    )
    result = await db.execute(assign_stmt)
    return list(result.scalars().all())


def _require_region_access(
    region_ids: list[UUID] | None,
    region_id: Any,
    detail: str = "User does not have access to this region",
) -> None:
    """Raise 403 if a scoped subject lacks access to the region."""
    normalized = region_id if isinstance(region_id, UUID) else UUID(str(region_id))
    if region_ids is not None and normalized not in region_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


def _require_any_region_access(region_ids: list[UUID] | None) -> None:
    """Raise 403 if a scoped subject has no region assignments at all."""
    if region_ids is not None and not region_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to any regions",
        )


async def validate_plate_string(plate_string: str, region_id: UUID, db: AsyncSession) -> None:
    """Validate plate string against region's plate_regex.

    Args:
        plate_string: Plate to validate
        region_id: Region ID for regex lookup
        db: Database session

    Raises:
        HTTPException: 404 if region not found, 422 if plate invalid
    """
    stmt = select(Region).where(Region.id == region_id)
    result = await db.execute(stmt)
    region = result.scalars().first()

    if not region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found",
        )

    if not re.match(str(region.regex), plate_string):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plate format invalid for region {region.code}",
        )


def _camera_to_dict(c: Camera) -> dict[str, Any]:
    """Convert a Camera ORM row to a CameraOut-compatible dict."""
    return {
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


def _detection_to_dict(d: Detection) -> dict[str, Any]:
    """Convert a Detection ORM row to a DetectionOut-compatible dict."""
    return {
        "id": str(d.id),
        "camera_id": str(d.camera_id),
        "plate_id": str(d.plate_id),
        "frame_timestamp": d.frame_timestamp,
        "confidence": d.confidence,
        "bbox": d.bbox or {},
        "ocr_backend": d.ocr_backend or "unknown",
        "quality_score": d.quality_score if d.quality_score is not None else 0.0,
        "crop_url": d.crop_url,
        "frame_url": d.frame_url,
        "is_persisted": d.is_persisted or "Y",
        "tracking_id": d.tracking_id,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _plate_to_dict(p: Plate) -> dict[str, Any]:
    """Convert a Plate ORM row to a PlateOut-compatible dict."""
    return {
        "id": str(p.id),
        "plate_string": p.plate_string,
        "region_id": str(p.region_id),
        "detection_count": p.detection_count,
        "first_seen_at": p.first_seen_at,
        "last_seen_at": p.last_seen_at,
        "avg_confidence": p.avg_confidence,
        "confidence": p.avg_confidence,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


router = APIRouter(prefix="/v1", tags=["data"])


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List regions the caller may access.

    Database users only see their assigned regions; other subjects see all.

    Returns:
        List of regions with metadata
    """
    region_ids = await _scoped_region_ids(user_id, db)
    _require_any_region_access(region_ids)

    stmt = select(Region)
    if region_ids is not None:
        stmt = stmt.where(Region.id.in_(region_ids))
    stmt = stmt.order_by(Region.code)
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
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List cameras for a specific region.

    Args:
        region_id: Region ID

    Returns:
        List of cameras in region

    Raises:
        HTTPException: 422 if region_id is invalid UUID, 404 if region not found
    """
    region_uuid = validate_uuid(region_id, "region ID")

    region_ids = await _scoped_region_ids(user_id, db)
    _require_region_access(region_ids, region_uuid)

    stmt = select(Region).where(Region.id == region_uuid)
    result = await db.execute(stmt)
    region = result.scalars().first()

    if not region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Region not found",
        )

    stmt = select(Camera).where(Camera.region_id == region_uuid).order_by(Camera.name)
    result = await db.execute(stmt)
    cameras = result.scalars().all()

    return [_camera_to_dict(c) for c in cameras]


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera(
    camera_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Get a single camera by ID.

    Args:
        camera_id: Camera ID

    Returns:
        Camera details

    Raises:
        HTTPException: 404 if camera not found, 403 if no region access
    """
    camera_uuid = _parse_uuid_or_none(camera_id)
    stmt = select(Camera).where(Camera.id == camera_uuid)
    result = await db.execute(stmt)
    camera = result.scalar_one_or_none()

    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )

    region_ids = await _scoped_region_ids(user_id, db)
    _require_region_access(
        region_ids,
        camera.region_id,
        detail="User does not have access to this camera's region",
    )

    return _camera_to_dict(camera)


@router.get("/detections", response_model=list[DetectionOut])
async def list_detections(
    region_id: str | None = Query(None),
    camera_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List detections with optional filters.

    Args:
        region_id: Filter by region ID
        camera_id: Filter by camera ID
        limit: Maximum detections to return
        offset: Pagination offset
        db: Database session
        user_id: Current user ID

    Returns:
        List of recent detections

    Raises:
        HTTPException: 422 if camera_id is invalid UUID
    """
    region_ids = await _scoped_region_ids(user_id, db)
    _require_any_region_access(region_ids)

    conditions = []

    if camera_id:
        camera_uuid = validate_uuid(camera_id, "camera ID")
        stmt = select(Camera).where(Camera.id == camera_uuid)
        result = await db.execute(stmt)
        camera = result.scalar_one_or_none()
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found",
            )
        _require_region_access(region_ids, camera.region_id)
        conditions.append(Detection.camera_id == camera_uuid)

    if region_id:
        region_uuid = validate_uuid(region_id, "region ID")
        _require_region_access(region_ids, region_uuid)
        conditions.append(Camera.region_id == region_uuid)

    stmt = select(Detection).join(Camera, Detection.camera_id == Camera.id)
    if region_ids is not None:
        conditions.append(Camera.region_id.in_(region_ids))

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Detection.frame_timestamp)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    detections = result.scalars().all()

    return [_detection_to_dict(d) for d in detections]


@router.get("/plates", response_model=list[PlateOut])
async def list_plates(
    region_id: str | None = Query(None),
    region: str | None = Query(None),
    camera_id: str | None = Query(None),
    q: str | None = Query(None),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """List plates with optional filters.

    Args:
        region_id: Filter by region ID
        region: Filter by region ID (alias)
        camera_id: Filter by camera ID (detections)
        q: Search by plate string
        date_from: Filter by first seen date (ISO 8601)
        date_to: Filter by last seen date (ISO 8601)
        limit: Maximum plates to return
        offset: Pagination offset
        db: Database session
        user_id: Current user ID

    Returns:
        List of detected plates

    Raises:
        HTTPException: 422 if region_id is invalid UUID
    """
    region_ids = await _scoped_region_ids(user_id, db)
    _require_any_region_access(region_ids)

    conditions = []

    region_filter = region_id or region
    if region_filter:
        region_uuid = validate_uuid(region_filter, "region ID")
        _require_region_access(region_ids, region_uuid)
        conditions.append(Plate.region_id == region_uuid)
    elif region_ids is not None:
        conditions.append(Plate.region_id.in_(region_ids))

    if camera_id:
        camera_uuid = validate_uuid(camera_id, "camera ID")
        conditions.append(
            Plate.id.in_(select(Detection.plate_id).where(Detection.camera_id == camera_uuid))
        )

    if q:
        conditions.append(Plate.plate_string.ilike(f"%{q}%"))

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            conditions.append(Plate.last_seen_at >= dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            conditions.append(Plate.last_seen_at <= dt_to)
        except ValueError:
            pass

    stmt = select(Plate)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Plate.last_seen_at)).limit(limit).offset(offset)
    result = await db.execute(stmt)
    plates = result.scalars().all()

    return [_plate_to_dict(p) for p in plates]


@router.get("/plates/{plate_id}", response_model=PlateOut)
async def get_plate_detail(
    plate_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Get a single plate by ID.

    Args:
        plate_id: Plate ID
        db: Database session
        user_id: Current user ID

    Returns:
        Plate details including region info and confidence

    Raises:
        HTTPException: 404 if plate not found, 403 if no region access
    """
    plate_uuid = _parse_uuid_or_none(plate_id)
    stmt = select(Plate).where(Plate.id == plate_uuid)
    result = await db.execute(stmt)
    plate = result.scalar_one_or_none()

    if not plate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plate not found",
        )

    region_ids = await _scoped_region_ids(user_id, db)
    _require_region_access(region_ids, plate.region_id)

    return _plate_to_dict(plate)


@router.get("/plates/{plate_id}/events")
async def get_plate_events(
    plate_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """Get detection history for a plate.

    Args:
        plate_id: Plate ID
        limit: Maximum events to return
        offset: Pagination offset
        db: Database session
        user_id: Current user ID

    Returns:
        List of detection events for the plate

    Raises:
        HTTPException: 404 if plate not found, 403 if no region access
    """
    plate_uuid = _parse_uuid_or_none(plate_id)
    stmt = select(Plate).where(Plate.id == plate_uuid)
    result = await db.execute(stmt)
    plate = result.scalar_one_or_none()

    if not plate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plate not found",
        )

    region_ids = await _scoped_region_ids(user_id, db)
    _require_region_access(region_ids, plate.region_id)

    stmt = (
        select(Detection)
        .where(Detection.plate_id == plate_uuid)
        .order_by(desc(Detection.frame_timestamp))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    detections = result.scalars().all()

    events = []
    for d in detections:
        event = _detection_to_dict(d)
        # Backwards-compatible timestamp alias expected by some clients
        if isinstance(d.frame_timestamp, datetime):
            event["timestamp"] = d.frame_timestamp.isoformat()
        events.append(event)
    return events
