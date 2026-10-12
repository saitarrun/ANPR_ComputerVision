"""Encryption utilities for Celery task payloads."""

import logging
from cryptography.fernet import Fernet

from api.config import settings

logger = logging.getLogger(__name__)

_cipher: Fernet | None = None


def _get_cipher() -> Fernet:
    """Build (and cache) the Fernet cipher on first use.

    Initialization is deferred so importing this module never fails when the
    configured key is a non-secret placeholder (e.g. CI dummy values). The
    key is still validated before any actual encryption/decryption.
    """
    global _cipher
    if _cipher is None:
        try:
            _cipher = Fernet(settings.celery_encryption_key.encode())
        except Exception as e:
            raise ValueError("CELERY_ENCRYPTION_KEY is not a valid Fernet key") from e
    return _cipher


def encrypt_frame(frame_bytes: bytes) -> bytes:
    """Encrypt frame bytes for Redis transmission.

    Args:
        frame_bytes: Raw frame data

    Returns:
        Encrypted bytes
    """
    try:
        encrypted = _get_cipher().encrypt(frame_bytes)
        return encrypted
    except Exception as e:
        logger.error(f"Failed to encrypt frame: {e}")
        raise


def decrypt_frame(encrypted_bytes: bytes) -> bytes:
    """Decrypt frame bytes from Redis.

    Args:
        encrypted_bytes: Encrypted frame data

    Returns:
        Raw frame bytes
    """
    try:
        decrypted = _get_cipher().decrypt(encrypted_bytes)
        return decrypted
    except Exception as e:
        logger.error(f"Failed to decrypt frame: {e}")
        raise
