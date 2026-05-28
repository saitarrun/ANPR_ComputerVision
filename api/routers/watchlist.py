"""Watchlist endpoints for alert pattern management."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import logging
import re
import signal

from api.deps import get_db_session, get_current_user_id
from db.models import Watchlist
from api.schemas.data import WatchlistIn, WatchlistOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/watchlist", tags=["watchlist"])

# Regex timeout threshold (seconds)
REGEX_TIMEOUT_SEC = 1


def _regex_timeout_handler(signum, frame):
    """Signal handler for regex timeout."""
    raise TimeoutError("Regex evaluation timeout (ReDoS protection)")


def validate_regex_pattern(pattern: str) -> bool:
    """Validate regex pattern compiles and doesn't timeout (ReDoS protection).

    Args:
        pattern: Regex pattern to validate

    Returns:
        True if pattern is valid and evaluates quickly, False otherwise
    """
    try:
        # Test compilation
        compiled = re.compile(pattern)

        # Test matching with timeout (Unix/Linux/macOS only)
        # This prevents catastrophic backtracking (ReDoS)
        try:
            signal.signal(signal.SIGALRM, _regex_timeout_handler)
            signal.alarm(REGEX_TIMEOUT_SEC)

            # Attempt a match on a test string to detect ReDoS patterns
            # Use a string that might trigger backtracking
            test_string = "A" * 50 + "INVALID"
            compiled.match(test_string)

            signal.alarm(0)  # Cancel alarm
        except TimeoutError:
            signal.alarm(0)  # Cancel alarm
            logger.warning(f"Regex pattern timed out (ReDoS risk): {pattern}")
            return False

        return True
    except re.error as e:
        logger.warning(f"Invalid regex pattern: {pattern} - {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating regex: {e}")
        return False


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    data: WatchlistIn,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new watchlist pattern.

    Args:
        data: Watchlist pattern data
        db: Database session
        user_id: Current user ID

    Returns:
        Created watchlist
    """
    if not validate_regex_pattern(data.plate_pattern):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {data.plate_pattern}",
        )

    watchlist = Watchlist(
        plate_pattern=data.plate_pattern,
        region_id=data.region_id,
        reason=data.reason,
        priority=data.priority,
        alert_enabled="Y" if data.alert_enabled else "N",
        alert_channel=data.alert_channel,
        dedup_window=300,
        hit_count=0,
        created_by_user_id=user_id,
    )

    db.add(watchlist)
    try:
        await db.commit()
        await db.refresh(watchlist)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create watchlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Watchlist pattern already exists for this region",
        )

    return WatchlistOut(
        id=str(watchlist.id),
        plate_pattern=watchlist.plate_pattern,
        region_id=str(watchlist.region_id),
        reason=watchlist.reason,
        priority=watchlist.priority,
        alert_enabled=watchlist.alert_enabled == "Y",
        alert_channel=watchlist.alert_channel,
        dedup_window=watchlist.dedup_window,
        last_hit=watchlist.last_hit,
        hit_count=watchlist.hit_count,
        created_by_user_id=str(watchlist.created_by_user_id),
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.get("", response_model=list[WatchlistOut])
async def list_watchlist(
    region_id: str | None = Query(None),
    enabled_only: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """List watchlist patterns.

    Args:
        region_id: Filter by region ID
        enabled_only: Show only enabled patterns
        db: Database session
        user_id: Current user ID

    Returns:
        List of watchlist patterns
    """
    conditions = []

    if region_id:
        conditions.append(Watchlist.region_id == region_id)

    if enabled_only:
        conditions.append(Watchlist.alert_enabled == "Y")

    stmt = select(Watchlist)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Watchlist.priority), Watchlist.plate_pattern)
    result = await db.execute(stmt)
    watchlists = result.scalars().all()

    return [
        WatchlistOut(
            id=str(w.id),
            plate_pattern=w.plate_pattern,
            region_id=str(w.region_id),
            reason=w.reason,
            priority=w.priority,
            alert_enabled=w.alert_enabled == "Y",
            alert_channel=w.alert_channel,
            dedup_window=w.dedup_window,
            last_hit=w.last_hit,
            hit_count=w.hit_count,
            created_by_user_id=str(w.created_by_user_id),
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w in watchlists
    ]


@router.get("/{watchlist_id}", response_model=WatchlistOut)
async def get_watchlist(
    watchlist_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        db: Database session

    Returns:
        Watchlist pattern
    """
    stmt = select(Watchlist).where(Watchlist.id == watchlist_id)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    return WatchlistOut(
        id=str(watchlist.id),
        plate_pattern=watchlist.plate_pattern,
        region_id=str(watchlist.region_id),
        reason=watchlist.reason,
        priority=watchlist.priority,
        alert_enabled=watchlist.alert_enabled == "Y",
        alert_channel=watchlist.alert_channel,
        dedup_window=watchlist.dedup_window,
        last_hit=watchlist.last_hit,
        hit_count=watchlist.hit_count,
        created_by_user_id=str(watchlist.created_by_user_id),
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.put("/{watchlist_id}", response_model=WatchlistOut)
async def update_watchlist(
    watchlist_id: str,
    data: WatchlistIn,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update a watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        data: Updated watchlist data
        db: Database session
        user_id: Current user ID

    Returns:
        Updated watchlist pattern
    """
    stmt = select(Watchlist).where(Watchlist.id == watchlist_id)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    if not validate_regex_pattern(data.plate_pattern):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {data.plate_pattern}",
        )

    watchlist.plate_pattern = data.plate_pattern
    watchlist.region_id = data.region_id
    watchlist.reason = data.reason
    watchlist.priority = data.priority
    watchlist.alert_enabled = "Y" if data.alert_enabled else "N"
    watchlist.alert_channel = data.alert_channel

    try:
        await db.commit()
        await db.refresh(watchlist)
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update watchlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update watchlist",
        )

    return WatchlistOut(
        id=str(watchlist.id),
        plate_pattern=watchlist.plate_pattern,
        region_id=str(watchlist.region_id),
        reason=watchlist.reason,
        priority=watchlist.priority,
        alert_enabled=watchlist.alert_enabled == "Y",
        alert_channel=watchlist.alert_channel,
        dedup_window=watchlist.dedup_window,
        last_hit=watchlist.last_hit,
        hit_count=watchlist.hit_count,
        created_by_user_id=str(watchlist.created_by_user_id),
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        db: Database session
        user_id: Current user ID
    """
    stmt = select(Watchlist).where(Watchlist.id == watchlist_id)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    await db.delete(watchlist)
    await db.commit()
