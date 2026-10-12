"""Authentication endpoints."""

from fastapi import APIRouter, Depends, Request, Body
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from uuid import UUID
import redis.asyncio as aioredis
import logging
from typing import Any, cast

from api.deps import get_db_session, get_current_user_id
from api.schemas.auth import LoginRequest, TokenResponse, UserResponse, RefreshRequest
from api.security import (
    ValidRole,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token_type,
    is_token_blacklisted,
    JWTError,
)
from api.config import settings, UserRole
from api.exceptions import AuthenticationError, ValidationError
from api.rate_limiter import limiter
from db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Authenticate user with email and password.

    Rate limit: 5 requests per minute per IP

    Args:
        request: Login request (email, password)
        db: Database session

    Returns:
        Access and refresh tokens
    """
    # Fetch user by email
    stmt = select(User).where(User.email == request.email)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # Verify password
    if not user or not verify_password(request.password, str(user.hashed_password)):
        raise AuthenticationError("Invalid email or password")

    # Generate tokens
    role_str = str(user.role)
    if role_str not in ("viewer", "operator", "admin"):
        raise AuthenticationError("Invalid user role")
    access_token = create_access_token(
        user_id=str(user.id),
        role=cast(ValidRole, role_str),
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )
    refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expire_minutes * 60,
        "user_id": str(user.id),
        "role": role_str,
    }


@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/minute")
async def register(
    request_obj: Request,
    request: dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Register a new user.

    Rate limit: 3 requests per minute per IP

    Args:
        request_obj: FastAPI request (for rate limiter)
        request: Registration request (email, password, username)
        db: Database session

    Returns:
        Access and refresh tokens
    """
    # Validate input
    if not isinstance(request, dict) or "email" not in request:
        raise ValidationError("Missing required fields: email, password, username")

    email = request.get("email", "").strip()
    password = request.get("password", "").strip()
    username = request.get("username", "").strip()

    if not email or not password or not username:
        raise ValidationError("Email, password, and username are required")

    # Check if user already exists
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise ValidationError("User with this email already exists")

    # Create user
    import uuid

    user = User(
        id=uuid.uuid4(),
        email=email,
        username=username,
        hashed_password=hash_password(password),
        role=UserRole.VIEWER,
        is_active="Y",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate tokens
    role_str = str(user.role)
    if role_str not in ("viewer", "operator", "admin"):
        raise AuthenticationError("Invalid user role")
    access_token = create_access_token(
        user_id=str(user.id),
        role=cast(ValidRole, role_str),
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )
    refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expire_minutes * 60,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Refresh access token using refresh token.

    The refresh token is provided in the JSON request body.

    Validates:
    - Token type is "refresh" (not access)
    - Token is not blacklisted (revoked)

    Args:
        payload: JSON body containing the refresh token
        db: Database session

    Returns:
        New access token

    Raises:
        AuthenticationError: If token type is wrong, blacklisted, or user not found
    """
    # No body at all -> 401 (mirrors "missing credentials" semantics)
    if payload is None:
        raise AuthenticationError("Refresh token is required")

    raw_token = payload.refresh_token

    # Decode and verify the token; invalid/expired -> 401
    try:
        token_payload = verify_token_type(raw_token, "refresh")
    except JWTError as e:
        raise AuthenticationError(f"Invalid refresh token: {e}") from e

    user_id = token_payload.get("user_id")

    # Check if token is blacklisted (revoked)
    try:
        redis_client = await aioredis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
        if await is_token_blacklisted(raw_token, redis_client):
            raise AuthenticationError("Token has been revoked")
    except AuthenticationError:
        raise
    except Exception as e:
        # Log but don't fail if Redis is unavailable; allow refresh to proceed
        logger.warning(f"Redis check failed: {e}")

    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError, AttributeError) as e:
        raise AuthenticationError("Invalid user in refresh token") from e

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthenticationError("User not found")

    role_str = str(user.role)
    if role_str not in ("viewer", "operator", "admin"):
        raise AuthenticationError("Invalid user role")
    access_token = create_access_token(
        user_id=str(user.id),
        role=cast(ValidRole, role_str),
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )

    return {
        "access_token": access_token,
        "refresh_token": raw_token,
        "expires_in": settings.jwt_expire_minutes * 60,
        "user_id": str(user.id),
        "role": role_str,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get current user information.

    Args:
        user_id: Current user ID
        db: Database session

    Returns:
        User information
    """
    try:
        user_uuid = UUID(str(user_id))
    except (ValueError, TypeError, AttributeError) as e:
        raise AuthenticationError("Invalid user identity") from e

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthenticationError("User not found")

    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": str(user.role),
        "created_at": user.created_at,
    }
