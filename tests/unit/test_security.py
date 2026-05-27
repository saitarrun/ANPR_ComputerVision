"""
Unit tests for security module: JWT, password hashing, encryption.

Test Coverage:
- JWT encode/decode round-trip
- JWT expiry validation
- JWT signature verification
- Password hashing + verification
- Fernet encryption/decryption
- RBAC enforcement
- Token type validation
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import InvalidToken

from api.security import (
    JWTError,
    PasswordHashError,
    create_access_token,
    create_refresh_token,
    decode_jwt,
    encode_jwt,
    hash_password,
    verify_password,
    verify_token_type,
)


class TestJWTEncoding:
    """JWT encoding tests."""

    def test_encode_jwt_valid(self, jwt_secret: str):
        """Test encoding a valid JWT token."""
        token = encode_jwt(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
            exp_seconds=900,
            token_type="access",
        )
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT has 3 parts

    def test_encode_jwt_requires_user_id(self, jwt_secret: str):
        """Test that user_id is required."""
        with pytest.raises(ValueError, match="user_id.*required"):
            encode_jwt(
                user_id="",
                role="viewer",
                secret=jwt_secret,
            )

    def test_encode_jwt_requires_role(self, jwt_secret: str):
        """Test that role is required."""
        with pytest.raises(ValueError, match="role.*required"):
            encode_jwt(
                user_id="user-123",
                role="",
                secret=jwt_secret,
            )

    def test_encode_jwt_invalid_role(self, jwt_secret: str):
        """Test that invalid roles are rejected."""
        with pytest.raises(ValueError, match="viewer.*operator.*admin"):
            encode_jwt(
                user_id="user-123",
                role="superuser",  # Invalid role
                secret=jwt_secret,
            )

    def test_encode_jwt_short_secret(self):
        """Test that secret must be at least 32 chars."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            encode_jwt(
                user_id="user-123",
                role="viewer",
                secret="short",
            )

    def test_encode_jwt_negative_expiry(self, jwt_secret: str):
        """Test that expiry must be positive."""
        with pytest.raises(ValueError, match="positive"):
            encode_jwt(
                user_id="user-123",
                role="viewer",
                secret=jwt_secret,
                exp_seconds=-100,
            )

    def test_encode_jwt_all_roles(self, jwt_secret: str):
        """Test encoding for all valid roles."""
        for role in ["viewer", "operator", "admin"]:
            token = encode_jwt(
                user_id="user-123",
                role=role,
                secret=jwt_secret,
            )
            assert token


class TestJWTDecoding:
    """JWT decoding tests."""

    def test_decode_jwt_valid(self, jwt_secret: str):
        """Test decoding a valid JWT token."""
        original_user_id = "user-456"
        token = encode_jwt(
            user_id=original_user_id,
            role="operator",
            secret=jwt_secret,
            exp_seconds=900,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["user_id"] == original_user_id
        assert payload["role"] == "operator"

    def test_decode_jwt_expired(self, jwt_secret: str):
        """Test that expired tokens are rejected."""
        token = encode_jwt(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
            exp_seconds=1,  # Expires in 1 second
        )
        time.sleep(2)
        with pytest.raises(JWTError, match="expired"):
            decode_jwt(token, secret=jwt_secret)

    def test_decode_jwt_invalid_signature(self, jwt_secret: str):
        """Test that tampering with token is detected."""
        token = encode_jwt(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        # Modify token
        parts = token.split(".")
        tampered_token = parts[0] + ".modified." + parts[2]
        with pytest.raises(JWTError, match="Invalid token"):
            decode_jwt(tampered_token, secret=jwt_secret)

    def test_decode_jwt_wrong_secret(self, jwt_secret: str):
        """Test that token signed with different secret fails."""
        token = encode_jwt(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        wrong_secret = "wrong-secret-key-min-32-chars-long-value-here-ok!"
        with pytest.raises(JWTError, match="Invalid token"):
            decode_jwt(token, secret=wrong_secret)

    def test_decode_jwt_missing_token(self, jwt_secret: str):
        """Test that empty token is rejected."""
        with pytest.raises(JWTError, match="required"):
            decode_jwt("", secret=jwt_secret)

    def test_decode_jwt_invalid_audience(self, jwt_secret: str):
        """Test that audience mismatch is detected."""
        token = encode_jwt(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        with pytest.raises(JWTError):
            decode_jwt(token, secret=jwt_secret, audience="wrong-audience")

    def test_decode_jwt_payload_structure(self, jwt_secret: str):
        """Test that decoded payload contains all required fields."""
        token = encode_jwt(
            user_id="user-789",
            role="admin",
            secret=jwt_secret,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        assert "user_id" in payload
        assert "role" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "aud" in payload
        assert "iss" in payload
        assert "jti" in payload
        assert "type" in payload


class TestAccessTokens:
    """Access token creation tests."""

    def test_create_access_token(self, jwt_secret: str):
        """Test access token creation."""
        token = create_access_token(
            user_id="user-123",
            role="operator",
            secret=jwt_secret,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["type"] == "access"
        assert payload["user_id"] == "user-123"
        assert payload["role"] == "operator"

    def test_access_token_expires_in_15_minutes(self, jwt_secret: str):
        """Test that access token expires in 15 minutes."""
        token = create_access_token(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat_time = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        diff = (exp_time - iat_time).total_seconds()
        assert 899 <= diff <= 901  # ~900 seconds = 15 minutes


class TestRefreshTokens:
    """Refresh token creation tests."""

    def test_create_refresh_token(self, jwt_secret: str):
        """Test refresh token creation."""
        token = create_refresh_token(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["type"] == "refresh"
        assert payload["user_id"] == "user-123"

    def test_refresh_token_expires_in_7_days(self, jwt_secret: str):
        """Test that refresh token expires in 7 days."""
        token = create_refresh_token(
            user_id="user-123",
            role="viewer",
            secret=jwt_secret,
        )
        payload = decode_jwt(token, secret=jwt_secret)
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat_time = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        diff = (exp_time - iat_time).total_seconds()
        expected = 604800  # 7 days in seconds
        assert diff >= expected and diff < expected + 2


class TestVerifyTokenType:
    """Token type verification tests."""

    def test_verify_token_type_access(self, jwt_secret: str):
        """Test verifying access token type."""
        token = create_access_token("user-123", "viewer", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        # Should not raise
        verify_token_type(payload, "access")

    def test_verify_token_type_refresh(self, jwt_secret: str):
        """Test verifying refresh token type."""
        token = create_refresh_token("user-123", "viewer", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        # Should not raise
        verify_token_type(payload, "refresh")

    def test_verify_token_type_mismatch(self, jwt_secret: str):
        """Test that token type mismatch is detected."""
        token = create_access_token("user-123", "viewer", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        with pytest.raises(JWTError, match="refresh"):
            verify_token_type(payload, "refresh")


class TestPasswordHashing:
    """Password hashing and verification tests."""

    def test_hash_password_valid(self):
        """Test hashing a valid password."""
        password = "secure-password-123!"
        hashed = hash_password(password)
        assert isinstance(hashed, str)
        assert len(hashed) > len(password)  # Hashed is longer
        assert hashed != password  # Not plaintext

    def test_hash_password_empty(self):
        """Test that empty password is rejected."""
        with pytest.raises(PasswordHashError, match="empty"):
            hash_password("")

    def test_hash_password_too_short(self):
        """Test that short password is rejected."""
        with pytest.raises(PasswordHashError, match="8 characters"):
            hash_password("short")

    def test_verify_password_valid(self):
        """Test password verification with correct password."""
        password = "correct-password-123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_verify_password_invalid(self):
        """Test password verification with wrong password."""
        password = "correct-password-123"
        hashed = hash_password(password)
        assert not verify_password("wrong-password", hashed)

    def test_verify_password_against_empty_hash(self):
        """Test verification against empty hash."""
        result = verify_password("password", "")
        assert not result

    def test_hash_password_different_hashes(self):
        """Test that same password produces different hashes (bcrypt salt)."""
        password = "same-password-123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestEncryption:
    """Encryption/decryption tests."""

    def test_encrypt_decrypt_plate_string(self):
        """Test Fernet encryption and decryption."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        cipher = Fernet(key)
        plaintext = b"KA01AB1234"
        encrypted = cipher.encrypt(plaintext)
        decrypted = cipher.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_wrong_key(self):
        """Test decryption with wrong key fails."""
        from cryptography.fernet import Fernet

        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        cipher1 = Fernet(key1)
        cipher2 = Fernet(key2)
        encrypted = cipher1.encrypt(b"KA01AB1234")
        with pytest.raises(InvalidToken):
            cipher2.decrypt(encrypted)


class TestRBAC:
    """Role-Based Access Control tests."""

    def test_role_viewer_in_token(self, jwt_secret: str):
        """Test that viewer role is correctly encoded."""
        token = encode_jwt("user-1", "viewer", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["role"] == "viewer"

    def test_role_operator_in_token(self, jwt_secret: str):
        """Test that operator role is correctly encoded."""
        token = encode_jwt("user-2", "operator", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["role"] == "operator"

    def test_role_admin_in_token(self, jwt_secret: str):
        """Test that admin role is correctly encoded."""
        token = encode_jwt("user-3", "admin", jwt_secret)
        payload = decode_jwt(token, secret=jwt_secret)
        assert payload["role"] == "admin"
