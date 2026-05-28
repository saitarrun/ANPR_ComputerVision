"""Settings and admin endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import logging

from api.deps import get_db_session, get_current_user_id
from api.security import hash_password, verify_password
from db.models import User
from api.schemas.auth import (
    ChangePasswordRequest,
    UserSettingsOut,
    UserSettingsUpdate,
    AdminUserListItem,
    AdminUserUpdate,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["settings"])


@router.get("/auth/me", response_model=UserResponse)
async def get_current_user(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get current user info.

    Returns:
        Current user details
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Change password for current user.

    Args:
        data: Password change request
        db: Database session
        user_id: Current user ID
    """
    if data.new_password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match",
        )

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    user.hashed_password = hash_password(data.new_password)
    await db.commit()


@router.get("/settings", response_model=UserSettingsOut)
async def get_user_settings(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get user settings.

    Returns:
        User settings
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserSettingsOut(
        id=str(user.id),
        email=user.email,
        retention_days=30,  # Default
        alert_channels=["webhook"],
        export_redaction_enabled=False,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.put("/settings", response_model=UserSettingsOut)
async def update_user_settings(
    data: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update user settings.

    Args:
        data: Settings update request
        db: Database session
        user_id: Current user ID

    Returns:
        Updated settings
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Store settings in user metadata (simplified)
    # In production, this would use a separate settings table
    await db.commit()

    return UserSettingsOut(
        id=str(user.id),
        email=user.email,
        retention_days=data.retention_days or 30,
        alert_channels=data.alert_channels or ["webhook"],
        export_redaction_enabled=data.export_redaction_enabled or False,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.get("/users", response_model=list[AdminUserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """List all users (admin only).

    Returns:
        List of users
    """
    # Check if current user is admin
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    current_user = result.scalar_one_or_none()

    if not current_user or current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list users",
        )

    # Fetch all users
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        AdminUserListItem(
            id=str(u.id),
            email=u.email,
            username=u.username,
            role=u.role,
            created_at=u.created_at,
            last_login=u.last_login,
            is_active=True,
        )
        for u in users
    ]


@router.put("/users/{target_user_id}", response_model=AdminUserListItem)
async def update_user(
    target_user_id: str,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update user (admin only).

    Args:
        target_user_id: User ID to update
        data: User update request
        db: Database session
        user_id: Current user ID (must be admin)

    Returns:
        Updated user
    """
    # Check if current user is admin
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    current_user = result.scalar_one_or_none()

    if not current_user or current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update users",
        )

    stmt = select(User).where(User.id == target_user_id)
    result = await db.execute(stmt)
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if data.role:
        if data.role not in ("viewer", "operator", "admin"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role",
            )
        target_user.role = data.role

    if data.is_active is not None:
        # Store in metadata (simplified)
        pass

    await db.commit()
    await db.refresh(target_user)

    return AdminUserListItem(
        id=str(target_user.id),
        email=target_user.email,
        username=target_user.username,
        role=target_user.role,
        created_at=target_user.created_at,
        last_login=target_user.last_login,
        is_active=True,
    )


@router.get("/health/status", response_model=dict)
async def health_status(
    db: AsyncSession = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get system health status.

    Returns:
        Health status and component statuses
    """
    try:
        # Test database
        result = await db.execute(select(1))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "components": {
            "database": db_status,
            "redis": "unknown",
            "minio": "unknown",
        },
    }
