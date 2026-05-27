"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta

from api.deps import get_db_session, get_current_user, get_current_user_id
from api.schemas.auth import LoginRequest, TokenResponse, UserResponse
from api.security import hash_password, verify_password, create_access_token, create_refresh_token, extract_user_id_from_token
from api.config import settings, UserRole
from api.exceptions import AuthenticationError, ValidationError
from db.models import User

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Authenticate user with email and password.

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


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Refresh access token using refresh token.

    Args:
        request: Token payload
        db: Database session

    Returns:
        New access token
    """
    user_id = request.get("sub")
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
    }
