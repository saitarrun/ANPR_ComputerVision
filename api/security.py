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
        if not password:
            raise PasswordHashError("Password cannot be empty")
        if len(password) < 8:
            raise PasswordHashError("Password must be at least 8 characters")
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
