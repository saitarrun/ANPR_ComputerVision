"""Password hashing and JWT token management."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext

from api.config import settings

# Password hashing context (bcrypt with cost factor 12)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """Hash password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from DB

    Returns:
        True if password matches
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: str,
    role,  # UserRole enum
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT access token.

    Args:
        user_id: User UUID as string
        role: UserRole enum
        expires_delta: Token expiry delta

    Returns:
        Signed JWT token
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expire_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "role": role.value,
        "exp": expire,
        "iat": now,
        "aud": "anpr-api",
        "iss": "anpr-issuer",
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def create_refresh_token(user_id: str) -> str:
    """Create JWT refresh token (longer expiry).

    Args:
        user_id: User UUID as string

    Returns:
        Signed JWT refresh token
    """
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    # Create a dummy role for refresh token
    class DummyRole:
        value = "viewer"
    return create_access_token(user_id, DummyRole(), expires_delta)


def verify_token(token: str) -> dict:
    """Verify and decode JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict

    Raises:
        Exception: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="anpr-api",
            issuer="anpr-issuer",
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        raise Exception("Token expired") from e
    except jwt.InvalidTokenError as e:
        raise Exception(f"Invalid token: {str(e)}") from e


def extract_user_id_from_token(token: str) -> str:
    """Extract user_id (sub claim) from token.

    Args:
        token: JWT token string

    Returns:
        User ID (UUID string)
    """
    payload = verify_token(token)
    return payload.get("sub")


def extract_role_from_token(token: str) -> str:
    """Extract role from token.

    Args:
        token: JWT token string

    Returns:
        Role string
    """
    payload = verify_token(token)
    return payload.get("role")
