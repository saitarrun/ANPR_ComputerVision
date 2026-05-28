"""Review queue endpoints for human verification of low-confidence detections."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import logging

from api.deps import get_db_session, get_current_user_id
from db.models import ReviewQueue, Detection
from api.schemas.data import ReviewQueueOut, ReviewQueueResolve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/review-queue", tags=["review"])


@router.get("", response_model=list[ReviewQueueOut])
async def list_review_queue(
    status_filter: str | None = Query(None),
    confidence_min: float | None = Query(None),
    confidence_max: float | None = Query(None),
    region_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """List review queue items with optional filters.

    Args:
        status_filter: Filter by status (pending, approved, rejected, flagged)
        confidence_min: Minimum confidence (0-1)
        confidence_max: Maximum confidence (0-1)
        region_id: Filter by region ID
        limit: Maximum items to return
        db: Database session
        user_id: Current user ID

    Returns:
        List of review queue items
    """
    conditions = []

    if status_filter:
        conditions.append(ReviewQueue.status == status_filter)

    # Join with detection to filter by confidence
    stmt = select(ReviewQueue)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(ReviewQueue.created_at)).limit(limit)
    result = await db.execute(stmt)
    review_items = result.scalars().all()

    items = []
    for item in review_items:
        # Filter by confidence if specified
        detection_blob = item.detection_blob
        if detection_blob:
            confidence = detection_blob.get('confidence', 0)
            if confidence_min and confidence < confidence_min:
                continue
            if confidence_max and confidence > confidence_max:
                continue
            if region_id and detection_blob.get('region_id') != region_id:
                continue

        items.append(
            ReviewQueueOut(
                id=str(item.id),
                detection_id=str(item.detection_id),
                status=item.status,
                reviewer_id=str(item.reviewer_id) if item.reviewer_id else None,
                detection_blob=item.detection_blob,
                notes=item.notes,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    return items


@router.post("/{review_id}/resolve", response_model=ReviewQueueOut)
async def resolve_review_item(
    review_id: str,
    data: ReviewQueueResolve,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Resolve a review queue item (approve/reject/flag).

    Args:
        review_id: Review queue item ID
        data: Resolution action and notes
        db: Database session
        user_id: Current user ID

    Returns:
        Updated review queue item
    """
    valid_statuses = {"approved", "rejected", "flagged"}
    if data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    stmt = select(ReviewQueue).where(ReviewQueue.id == review_id)
    result = await db.execute(stmt)
    review_item = result.scalar_one_or_none()

    if not review_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review queue item not found",
        )

    review_item.status = data.status
    review_item.reviewer_id = user_id
    review_item.notes = data.notes

    # If flagged, store corrected plate
    if data.status == "flagged" and data.corrected_plate:
        if review_item.detection_blob is None:
            review_item.detection_blob = {}
        review_item.detection_blob["corrected_plate"] = data.corrected_plate

    await db.commit()
    await db.refresh(review_item)

    return ReviewQueueOut(
        id=str(review_item.id),
        detection_id=str(review_item.detection_id),
        status=review_item.status,
        reviewer_id=str(review_item.reviewer_id) if review_item.reviewer_id else None,
        detection_blob=review_item.detection_blob,
        notes=review_item.notes,
        created_at=review_item.created_at,
        updated_at=review_item.updated_at,
    )


@router.get("/stats", response_model=dict)
async def review_queue_stats(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get review queue statistics.

    Returns:
        Statistics: pending_count, approved_count, rejected_count, flagged_count, avg_confidence
    """
    stmt = select(ReviewQueue)
    result = await db.execute(stmt)
    all_items = result.scalars().all()

    stats = {
        "pending": 0,
        "approved": 0,
        "rejected": 0,
        "flagged": 0,
        "avg_confidence": 0.0,
    }

    confidences = []
    for item in all_items:
        status = item.status
        if status in stats:
            stats[status] += 1

        blob = item.detection_blob or {}
        if "confidence" in blob:
            confidences.append(float(blob["confidence"]))

    if confidences:
        stats["avg_confidence"] = sum(confidences) / len(confidences)

    return stats
