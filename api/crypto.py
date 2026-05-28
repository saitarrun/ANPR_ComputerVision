"""Encryption utilities for Celery task payloads."""

import logging
from cryptography.fernet import Fernet

from api.config import settings

logger = logging.getLogger(__name__)

# Initialize Fernet cipher with Celery encryption key
_cipher = Fernet(settings.celery_encryption_key.encode())


def encrypt_frame(frame_bytes: bytes) -> bytes:
    """Encrypt frame bytes for Redis transmission.
    
    Args:
        frame_bytes: Raw frame data
        
    Returns:
        Encrypted bytes
    """
    try:
        encrypted = _cipher.encrypt(frame_bytes)
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
        decrypted = _cipher.decrypt(encrypted_bytes)
        return decrypted
    except Exception as e:
        logger.error(f"Failed to decrypt frame: {e}")
        raise
