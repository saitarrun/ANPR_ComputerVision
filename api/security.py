"""Password hashing, JWT token management, and encryption."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Literal
from jose import jwt as jose_jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet

from api.config import settings


# ============================================================================
# EXCEPTIONS
# ============================================================================


class PasswordHashError(Exception):
    """Raised when password hashing fails."""
    pass


class JWTError(Exception):
    """Raised when JWT operations fail."""
    pass


# ============================================================================
# PASSWORD HASHING
# ============================================================================


# Password hashing context (argon2)
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


def validate_password_strength(password: str) -> None:
    """Validate password meets security requirements.

    Requirements:
    - At least 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*)

    Args:
        password: Plain text password

    Raises:
        PasswordHashError: If password doesn't meet requirements
    """
    import re
    if not password:
        raise PasswordHashError("Password cannot be empty")
    if len(password) < 12:
        raise PasswordHashError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise PasswordHashError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise PasswordHashError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise PasswordHashError("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*]", password):
        raise PasswordHashError("Password must contain at least one special character (!@#$%^&*)")


def hash_password(password: str) -> str:
    """Hash password using argon2.

    Args:
        password: Plain text password

    Returns:
        Hashed password

    Raises:
        PasswordHashError: If hashing fails
    """
    try:
        validate_password_strength(password)
        return pwd_context.hash(password)
    except PasswordHashError:
        raise
    except Exception as e:
        raise PasswordHashError(f"Failed to hash password: {str(e)}") from e


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from DB

    Returns:
        True if password matches, False otherwise

    Raises:
        PasswordHashError: If verification fails
    """
    try:
        if not plain_password:
            return False
        if not hashed_password:
            return False
        return pwd_context.verify(plain_password, hashed_password)
    except PasswordHashError:
        raise
    except Exception as e:
        raise PasswordHashError(f"Failed to verify password: {str(e)}") from e


# ============================================================================
# JWT TOKEN MANAGEMENT
# ============================================================================


ValidRole = Literal["viewer", "operator", "admin"]
TokenType = Literal["access", "refresh"]


def encode_jwt(
    user_id: str,
    role: ValidRole,
    secret: Optional[str] = None,
    exp_seconds: Optional[int] = None,
    token_type: TokenType = "access",
) -> str:
    """Encode a JWT token.

    Args:
        user_id: User UUID as string
        role: One of "viewer", "operator", "admin"
        secret: JWT secret (defaults to settings.jwt_secret)
        exp_seconds: Token expiry in seconds (defaults to 900 for access, 604800 for refresh)
        token_type: "access" or "refresh"

    Returns:
        Signed JWT token string

    Raises:
        ValueError: If inputs are invalid
        JWTError: If encoding fails
    """
    # Validate inputs
    if not user_id:
        raise ValueError("user_id is required")
    if not role:
        raise ValueError("role is required")
    if role not in ("viewer", "operator", "admin"):
        raise ValueError(f"role must be one of: viewer, operator, admin")
    
    secret = secret or settings.jwt_secret
    if not secret or len(secret) < 32:
        raise ValueError("JWT secret must be at least 32 characters")
    
    if exp_seconds is not None and exp_seconds <= 0:
        raise ValueError("exp_seconds must be positive")
    
    # Set default expiry based on token type
    if exp_seconds is None:
        if token_type == "refresh":
            exp_seconds = 604800  # 7 days
        else:
            exp_seconds = 900  # 15 minutes
    
    try:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(seconds=exp_seconds)
        
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": int(expire.timestamp()),
            "iat": int(now.timestamp()),
            "type": token_type,
            "jti": str(uuid.uuid4()),
            "aud": "anpr-api",
            "iss": "anpr-issuer",
        }
        
        token = jose_jwt.encode(
            payload,
            secret,
            algorithm=settings.jwt_algorithm,
        )
        return token
    except Exception as e:
        raise JWTError(f"Failed to encode JWT: {str(e)}") from e


def decode_jwt(
    token: str,
    secret: Optional[str] = None,
    algorithms: Optional[list[str]] = None,
    audience: Optional[str] = None,
) -> dict:
    """Decode and verify JWT token.

    Args:
        token: JWT token string
        secret: JWT secret (defaults to settings.jwt_secret)
        algorithms: List of allowed algorithms (defaults to [settings.jwt_algorithm])
        audience: Expected audience claim (defaults to "anpr-api")

    Returns:
        Decoded payload dictionary

    Raises:
        JWTError: If token is invalid or expired
    """
    if not token:
        raise JWTError("Token is required")
    
    secret = secret or settings.jwt_secret
    algorithms = algorithms or [settings.jwt_algorithm]
    audience = audience or "anpr-api"
    
    try:
        payload = jose_jwt.decode(
            token,
            secret,
            algorithms=algorithms,
            audience=audience,
            issuer="anpr-issuer",
        )
        return payload
    except jose_jwt.ExpiredSignatureError as e:
        raise JWTError("Token expired") from e
    except jose_jwt.JWTError as e:
        raise JWTError(f"Invalid token: {str(e)}") from e
    except Exception as e:
        raise JWTError(f"Failed to decode JWT: {str(e)}") from e


def verify_token_type(
    token_or_payload,
    expected_type: TokenType,
    secret: Optional[str] = None,
) -> dict:
    """Decode JWT and verify it matches expected type.

    Can accept either a token string or a decoded payload dict.

    Args:
        token_or_payload: JWT token string or decoded payload dict
        expected_type: "access" or "refresh"
        secret: JWT secret (defaults to settings.jwt_secret) - only used if token_or_payload is a string

    Returns:
        Decoded payload if type matches

    Raises:
        JWTError: If token type doesn't match or is invalid
    """
    try:
        # Handle both token strings and decoded payloads
        if isinstance(token_or_payload, dict):
            payload = token_or_payload
        else:
            payload = decode_jwt(token_or_payload, secret)
        
        actual_type = payload.get("type", "access")
        if actual_type != expected_type:
            raise JWTError(f"Expected {expected_type} token, got {actual_type}")
        
        return payload
    except JWTError:
        raise
    except Exception as e:
        raise JWTError(f"Failed to verify token type: {str(e)}") from e


def create_access_token(
    user_id: str,
    role: ValidRole,
    secret: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT access token.

    Args:
        user_id: User UUID as string
        role: One of "viewer", "operator", "admin"
        secret: JWT secret (defaults to settings.jwt_secret)
        expires_delta: Token expiry delta (defaults to 15 minutes)

    Returns:
        Signed JWT token

    Raises:
        JWTError: If token creation fails
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=15)  # 15 minutes = 900 seconds
    
    exp_seconds = int(expires_delta.total_seconds())
    
    return encode_jwt(
        user_id=user_id,
        role=role,
        secret=secret,
        exp_seconds=exp_seconds,
        token_type="access",
    )


def create_refresh_token(
    user_id: str,
    role: Optional[ValidRole] = None,
    secret: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT refresh token (longer expiry).

    Args:
        user_id: User UUID as string
        role: One of "viewer", "operator", "admin" (optional, defaults to viewer)
        secret: JWT secret (defaults to settings.jwt_secret)
        expires_delta: Token expiry delta (defaults to 7 days)

    Returns:
        Signed JWT refresh token

    Raises:
        JWTError: If token creation fails
    """
    role = role or "viewer"
    
    if expires_delta is None:
        expires_delta = timedelta(days=7)  # 7 days
    
    exp_seconds = int(expires_delta.total_seconds())
    
    return encode_jwt(
        user_id=user_id,
        role=role,
        secret=secret,
        exp_seconds=exp_seconds,
        token_type="refresh",
    )


def verify_token(token: str) -> dict:
    """Verify and decode JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict

    Raises:
        JWTError: If token is invalid or expired
    """
    return decode_jwt(token)


def extract_user_id_from_token(token: str) -> str:
    """Extract user_id from token.

    Args:
        token: JWT token string

    Returns:
        User ID (UUID string)

    Raises:
        JWTError: If token is invalid
    """
    payload = verify_token(token)
    return payload.get("user_id")


def extract_role_from_token(token: str) -> str:
    """Extract role from token.

    Args:
        token: JWT token string

    Returns:
        Role string

    Raises:
        JWTError: If token is invalid
    """
    payload = verify_token(token)
    return payload.get("role")


# ============================================================================
# TOKEN BLACKLIST (Redis-backed revocation)
# ============================================================================


async def add_token_to_blacklist(token: str, redis_client) -> None:
    """Add token to blacklist (revocation list).

    Stores token JTI in Redis, expires at token's expiration time.
    Used for logout and token revocation.

    Args:
        token: JWT token string
        redis_client: aioredis.Redis client

    Raises:
        JWTError: If token is invalid
    """
    try:
        payload = decode_jwt(token)
        jti = payload.get("jti")
        exp_timestamp = payload.get("exp")

        if not jti or not exp_timestamp:
            raise JWTError("Token missing JTI or expiration")

        # Calculate TTL as (exp_timestamp - now) seconds
        now_timestamp = int(datetime.now(timezone.utc).timestamp())
        ttl = max(1, exp_timestamp - now_timestamp)

        # Store in Redis with expiry equal to token's remaining lifetime
        await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")
    except JWTError:
        raise
    except Exception as e:
        raise JWTError(f"Failed to blacklist token: {str(e)}") from e


async def is_token_blacklisted(token: str, redis_client) -> bool:
    """Check if token has been revoked (blacklisted).

    Args:
        token: JWT token string
        redis_client: aioredis.Redis client

    Returns:
        True if token is blacklisted, False otherwise

    Raises:
        JWTError: If token is invalid
    """
    try:
        payload = decode_jwt(token)
        jti = payload.get("jti")

        if not jti:
            raise JWTError("Token missing JTI")

        result = await redis_client.exists(f"token_blacklist:{jti}")
        return bool(result)
    except JWTError:
        raise
    except Exception as e:
        raise JWTError(f"Failed to check token blacklist: {str(e)}") from e


# ============================================================================
# ENCRYPTION (Fernet - symmetric)
# ============================================================================


def encrypt_data(data: bytes, key: bytes) -> bytes:
    """Encrypt data using Fernet symmetric encryption.

    Args:
        data: Data to encrypt (bytes)
        key: Fernet encryption key

    Returns:
        Encrypted data

    Raises:
        ValueError: If key is invalid or data is empty
    """
    if not data:
        raise ValueError("Data to encrypt cannot be empty")
    
    try:
        cipher = Fernet(key)
        return cipher.encrypt(data)
    except Exception as e:
        raise ValueError(f"Encryption failed: {str(e)}") from e


def decrypt_data(encrypted_data: bytes, key: bytes) -> bytes:
    """Decrypt data using Fernet symmetric decryption.

    Args:
        encrypted_data: Encrypted data (bytes)
        key: Fernet encryption key

    Returns:
        Decrypted data

    Raises:
        ValueError: If key is invalid or decryption fails
    """
    if not encrypted_data:
        raise ValueError("Encrypted data cannot be empty")
    
    try:
        cipher = Fernet(key)
        return cipher.decrypt(encrypted_data)
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}") from e


def generate_encryption_key() -> bytes:
    """Generate a new Fernet encryption key.

    Returns:
        Fernet key suitable for encrypt_data/decrypt_data
    """
    return Fernet.generate_key()


# ============================================================================
# RESOURCE AUTHORIZATION
# ============================================================================


async def get_user_accessible_regions(
    user_id: str,
    db,
) -> list[str]:
    """Get list of region IDs that user has access to.

    Args:
        user_id: User UUID as string
        db: SQLAlchemy AsyncSession

    Returns:
        List of region IDs (as strings) user can access.
        Empty list if user has no region assignments.

    Raises:
        ValueError: If user_id is invalid
    """
    if not user_id:
        raise ValueError("user_id is required")

    try:
        from db.models import UserRegionAssignment
        from sqlalchemy import select
        from uuid import UUID

        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

        stmt = select(UserRegionAssignment.region_id).where(
            UserRegionAssignment.user_id == user_uuid
        )
        result = await db.execute(stmt)
        region_ids = result.scalars().all()

        # Return as strings for consistency with query filters
        return [str(rid) for rid in region_ids]
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to retrieve user accessible regions: {str(e)}") from e
