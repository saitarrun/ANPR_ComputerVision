"""Plate string encryption service using Fernet."""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from api.settings import settings

logger = logging.getLogger(__name__)


class PlateEncryption:
    """Service for encrypting/decrypting plate strings."""

    def __init__(self, key: str | bytes) -> None:
        """Initialize encryption service.

        Args:
            key: Fernet key (base64-encoded).
        """
        if isinstance(key, str):
            key = key.encode()
        try:
            self.cipher = Fernet(key)
        except Exception as e:
            logger.error(f"Invalid Fernet key: {e}")
            raise ValueError("Invalid Fernet key") from e

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plate string.

        Args:
            plaintext: Plain text plate string.

        Returns:
            Encrypted (base64-encoded) plate string.
        """
        try:
            ciphertext = self.cipher.encrypt(plaintext.encode())
            return ciphertext.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError("Encryption failed") from e

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt plate string.

        Args:
            ciphertext: Encrypted (base64-encoded) plate string.

        Returns:
            Plain text plate string.
        """
        try:
            plaintext = self.cipher.decrypt(ciphertext.encode())
            return plaintext.decode()
        except InvalidToken:
            logger.warning("Invalid token during decryption")
            raise ValueError("Invalid encrypted plate") from None
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Decryption failed") from e


# Initialize encryption service
if settings.fernet_key:
    plate_encryption = PlateEncryption(settings.fernet_key)
else:
    # Fallback: generate a key for development
    logger.warning("FERNET_KEY not set; generating ephemeral key (DEV ONLY)")
    plate_encryption = PlateEncryption(Fernet.generate_key())
