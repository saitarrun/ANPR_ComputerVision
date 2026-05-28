"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Header
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
import redis.asyncio as aioredis
import logging

from api.deps import get_db_session, get_current_user, get_current_user_id
from api.schemas.auth import LoginRequest, TokenResponse, UserResponse
from api.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    extract_user_id_from_token,
    verify_token_type,
    add_token_to_blacklist,
    is_token_blacklisted,
)
from api.config import settings, UserRole
from api.exceptions import AuthenticationError, ValidationError
from db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
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
    if not user or not verify_password(request.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    # Generate tokens
    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )
    refresh_token = create_refresh_token(str(user.id))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.jwt_expire_minutes * 60,
    }


@router.post("/register", response_model=TokenResponse)
async def register(
    request: dict,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Register a new user.

    Rate limit: 3 requests per minute per IP

    Args:
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
    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
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
    request: dict = Depends(get_current_user),
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Refresh access token using refresh token.

    Validates:
    - Token type is "refresh" (not access)
    - Token is not blacklisted (revoked)

    Args:
        request: Token payload (from Authorization header)
        authorization: Raw Authorization header for blacklist check
        db: Database session

    Returns:
        New access token

    Raises:
        AuthenticationError: If token type is wrong, blacklisted, or user not found
    """
    user_id = request.get("user_id")
    token_type = request.get("type", "access")

    # Verify this is a refresh token, not an access token
    if token_type != "refresh":
        raise AuthenticationError("Invalid token type: expected refresh token")

    # Extract raw token for blacklist check
    raw_token = ""
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ")[1]

    # Check if token is blacklisted (revoked)
    if raw_token:
        try:
            redis_client = await aioredis.from_url(settings.redis_url)
            if await is_token_blacklisted(raw_token, redis_client):
                raise AuthenticationError("Token has been revoked")
        except Exception as e:
            if "Token has been revoked" in str(e):
                raise
            # Log but don't fail if Redis is unavailable; allow refresh to proceed
            logger.warning(f"Redis check failed: {e}")

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthenticationError("User not found")

    access_token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        expires_delta=timedelta(minutes=settings.jwt_expire_minutes),
    )

    return {
        "access_token": access_token,
        "refresh_token": request.get("refresh_token", ""),
        "expires_in": settings.jwt_expire_minutes * 60,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get current user information.

    Args:
        user_id: Current user ID
        db: Database session

    Returns:
        User information
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthenticationError("User not found")

    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "role": user.role.value,
        "created_at": user.created_at,
    }
