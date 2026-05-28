"""Authentication dependencies."""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.exceptions import AuthenticationError, AuthorizationError
from api.security import verify_token, extract_user_id_from_token, extract_role_from_token
from api.config import UserRole
from db.engine import AsyncSessionLocal
from db.models import User


async def get_current_user(
    authorization: str = Header(None),
) -> dict:
    """Extract and verify JWT from Authorization header.

    Args:
        authorization: Authorization header (Bearer <token>)

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token invalid or missing
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.split(" ")[1]
    try:
        return verify_token(token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
        )


async def get_current_user_id(token: dict = Depends(get_current_user)) -> str:
    """Extract user ID from token."""
    user_id = token.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )
    return user_id


async def get_current_user_role(token: dict = Depends(get_current_user)) -> UserRole:
    """Extract user role from token."""
    role_str = token.get("role")
    if not role_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing role",
        )
    return UserRole(role_str)


async def require_role(*roles: UserRole):
    """Dependency factory for role-based access control.

    Args:
        roles: Allowed roles

    Returns:
        Dependency function
    """
    async def check_role(current_role: UserRole = Depends(get_current_user_role)) -> UserRole:
        if current_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of: {', '.join([r.value for r in roles])}",
            )
        return current_role
    return check_role
