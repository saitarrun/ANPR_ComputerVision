"""Role-Based Access Control (RBAC) layer (F15)."""

from enum import Enum
from typing import List, Callable, Optional
from functools import wraps

from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import UserRole
from api.deps import get_current_user, get_db
from db.models import User, Camera


class RBACAction(str, Enum):
    """Actions that can be restricted by role."""

    READ_LIVE = "read_live"
    READ_PLATES = "read_plates"
    MANAGE_WATCHLIST = "manage_watchlist"
    REVIEW_DETECTIONS = "review_detections"
    MANAGE_STREAMS = "manage_streams"
    MANAGE_USERS = "manage_users"
    EXPORT_DATA = "export_data"
    VIEW_AUDIT_LOG = "view_audit_log"


# Role-to-actions mapping
ROLE_PERMISSIONS = {
    UserRole.VIEWER: {
        RBACAction.READ_LIVE,
        RBACAction.READ_PLATES,
    },
    UserRole.OPERATOR: {
        RBACAction.READ_LIVE,
        RBACAction.READ_PLATES,
        RBACAction.MANAGE_WATCHLIST,
        RBACAction.REVIEW_DETECTIONS,
        RBACAction.EXPORT_DATA,
        RBACAction.VIEW_AUDIT_LOG,
    },
    UserRole.ADMIN: {
        RBACAction.READ_LIVE,
        RBACAction.READ_PLATES,
        RBACAction.MANAGE_WATCHLIST,
        RBACAction.REVIEW_DETECTIONS,
        RBACAction.MANAGE_STREAMS,
        RBACAction.MANAGE_USERS,
        RBACAction.EXPORT_DATA,
        RBACAction.VIEW_AUDIT_LOG,
    },
}


async def require_role(
    required_roles: List[str] = None,
    required_action: Optional[RBACAction] = None,
) -> Callable:
    """Dependency to enforce role-based access.

    Args:
        required_roles: List of allowed roles (e.g., ['operator', 'admin']).
        required_action: Action that must be permitted for user's role.

    Usage:
        @router.get("/protected")
        async def endpoint(
            user: User = Depends(require_role(['operator', 'admin']))
        ):
            ...

    Raises:
        HTTPException 403 if user lacks required role/action.
    """

    async def check_role(user: User = Depends(get_current_user)) -> User:
        if required_roles and user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {required_roles}",
            )

        if required_action:
            allowed_actions = ROLE_PERMISSIONS.get(UserRole(user.role), set())
            if required_action not in allowed_actions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Action '{required_action}' not permitted for role '{user.role}'",
                )

        return user

    return check_role


async def check_camera_access(
    user: User,
    camera_id: str,
    db_session: AsyncSession,
) -> bool:
    """Check if user has access to a specific camera (multi-tenant).

    Args:
        user: Authenticated user.
        camera_id: Camera ID to check.
        db_session: Database session.

    Returns:
        True if user owns or has been granted access to camera.
    """
    from sqlalchemy import select
    from db.models import UserStream

    # Admins see all cameras
    if user.role == UserRole.ADMIN:
        return True

    # Check ownership (created by user)
    stmt = select(Camera).where(
        (Camera.id == camera_id)
    )
    result = await db_session.execute(stmt)
    camera = result.scalar_one_or_none()
    
    if camera and hasattr(camera, 'created_by_user_id') and camera.created_by_user_id == user.id:
        return True

    # Check user_streams junction table for granted access
    stmt = select(UserStream).where(
        (UserStream.user_id == user.id) &
        (UserStream.camera_id == camera_id)
    )
    result = await db_session.execute(stmt)
    return result.scalar_one_or_none() is not None
