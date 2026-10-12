"""Watchlist endpoints for alert pattern management."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
import logging
import re
import signal
import threading
from typing import Any
from uuid import UUID

from api.config import UserRole
from api.deps import get_db_session, get_current_user_id, require_role
from db.models import Watchlist
from api.schemas.data import WatchlistIn, WatchlistOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/watchlist", tags=["watchlist"])

# Regex timeout threshold (seconds)
REGEX_TIMEOUT_SEC = 1

# Role guard: only operators and admins may mutate the watchlist
manage_watchlist = require_role(UserRole.OPERATOR, UserRole.ADMIN)


def _parse_uuid_or_none(value: str | None) -> UUID | None:
    """Parse a UUID string, returning None for missing/invalid values."""
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _regex_timeout_handler(signum: int, frame: Any) -> None:
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
    except re.error as e:
        logger.warning(f"Invalid regex pattern: {pattern} - {e}")
        return False

    # The SIGALRM-based ReDoS probe only works on the main thread (signal
    # handlers can only be registered there). In worker threads (e.g. the
    # TestClient portal or uvicorn workers) fall back to the compile check.
    if threading.current_thread() is not threading.main_thread():
        return True

    try:
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


def _to_out(watchlist: Watchlist) -> WatchlistOut:
    """Convert a Watchlist ORM row to its response schema."""
    return WatchlistOut(
        id=str(watchlist.id),
        plate_pattern=watchlist.plate_pattern,
        region_id=str(watchlist.region_id) if watchlist.region_id else None,
        reason=watchlist.reason,
        priority=watchlist.priority or 0,
        alert_enabled=watchlist.alert_enabled == "Y",
        alert_channel=watchlist.alert_channel,
        dedup_window=watchlist.dedup_window or 300,
        last_hit=watchlist.last_hit,
        match_count=watchlist.match_count or 0,
        created_by_user_id=str(watchlist.created_by_user_id)
        if watchlist.created_by_user_id
        else None,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    data: WatchlistIn,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    _role: UserRole = Depends(manage_watchlist),
) -> WatchlistOut:
    """Create a new watchlist pattern.

    Args:
        data: Watchlist pattern data
        db: Database session
        user_id: Current user ID

    Returns:
        Created watchlist
    """
    if not data.plate_pattern or not data.plate_pattern.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plate_pattern must not be empty",
        )

    if not validate_regex_pattern(data.plate_pattern):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {data.plate_pattern}",
        )

    region_uuid = _parse_uuid_or_none(data.region_id)
    if data.region_id and region_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid region_id format",
        )

    watchlist = Watchlist(
        plate_pattern=data.plate_pattern,
        region_id=region_uuid,
        reason=data.reason,
        priority=data.priority,
        alert_enabled="Y" if data.alert_enabled else "N",
        alert_channel=data.alert_channel,
        dedup_window=300,
        match_count=0,
        created_by_user_id=str(user_id),
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

    return _to_out(watchlist)


@router.get("", response_model=list[WatchlistOut])
async def list_watchlist(
    region_id: str | None = Query(None),
    enabled_only: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> list[WatchlistOut]:
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

    region_uuid = _parse_uuid_or_none(region_id)
    if region_id:
        conditions.append(Watchlist.region_id == region_uuid)

    if enabled_only:
        conditions.append(Watchlist.alert_enabled == "Y")

    stmt = select(Watchlist)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(desc(Watchlist.priority), Watchlist.plate_pattern)
    result = await db.execute(stmt)
    watchlists = result.scalars().all()

    return [_to_out(w) for w in watchlists]


@router.get("/{watchlist_id}", response_model=WatchlistOut)
async def get_watchlist(
    watchlist_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
) -> WatchlistOut:
    """Get a specific watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        db: Database session
        user_id: Current user ID

    Returns:
        Watchlist pattern
    """
    entry_uuid = _parse_uuid_or_none(watchlist_id)
    stmt = select(Watchlist).where(Watchlist.id == entry_uuid)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    return _to_out(watchlist)


@router.put("/{watchlist_id}", response_model=WatchlistOut)
async def update_watchlist(
    watchlist_id: str,
    data: WatchlistIn,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    _role: UserRole = Depends(manage_watchlist),
) -> WatchlistOut:
    """Update a watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        data: Updated watchlist data
        db: Database session
        user_id: Current user ID

    Returns:
        Updated watchlist pattern
    """
    entry_uuid = _parse_uuid_or_none(watchlist_id)
    stmt = select(Watchlist).where(Watchlist.id == entry_uuid)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    if not data.plate_pattern or not data.plate_pattern.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plate_pattern must not be empty",
        )

    if not validate_regex_pattern(data.plate_pattern):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {data.plate_pattern}",
        )

    region_uuid = _parse_uuid_or_none(data.region_id)
    if data.region_id and region_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid region_id format",
        )

    watchlist.plate_pattern = data.plate_pattern  # type: ignore[assignment]
    watchlist.region_id = region_uuid  # type: ignore[assignment]
    watchlist.reason = data.reason  # type: ignore[assignment]
    watchlist.priority = data.priority  # type: ignore[assignment]
    watchlist.alert_enabled = "Y" if data.alert_enabled else "N"  # type: ignore[assignment]
    watchlist.alert_channel = data.alert_channel  # type: ignore[assignment]

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

    return _to_out(watchlist)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: str,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
    _role: UserRole = Depends(manage_watchlist),
) -> None:
    """Delete a watchlist pattern.

    Args:
        watchlist_id: Watchlist ID
        db: Database session
        user_id: Current user ID
    """
    entry_uuid = _parse_uuid_or_none(watchlist_id)
    stmt = select(Watchlist).where(Watchlist.id == entry_uuid)
    result = await db.execute(stmt)
    watchlist = result.scalar_one_or_none()

    if not watchlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist pattern not found",
        )

    await db.delete(watchlist)
    await db.commit()
