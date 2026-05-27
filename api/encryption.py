"""Fernet symmetric encryption for sensitive plate strings."""

import base64
from typing import Optional
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


def _validate_fernet_key(key: Optional[str]) -> str:
    """Validate Fernet key (44 chars, base64)."""
    if not key:
        raise EncryptionError("FERNET_KEY not set")
    if len(key) != 44:
        raise EncryptionError(f"FERNET_KEY must be 44 chars, got {len(key)}")
    try:
        base64.urlsafe_b64decode(key)
        return key
    except Exception as e:
        raise EncryptionError(f"Invalid FERNET_KEY: {e}") from e


def encrypt_plate_string(plate_str: str, key: str) -> str:
    """Encrypt plate string using Fernet (hex format)."""
    if not plate_str:
        raise EncryptionError("plate_str cannot be empty")
    try:
        validated_key = _validate_fernet_key(key)
        cipher = Fernet(validated_key)
        ciphertext = cipher.encrypt(plate_str.encode("utf-8"))
        return ciphertext.hex()
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt: {e}") from e


def decrypt_plate_string(ciphertext_hex: str, key: str) -> str:
    """Decrypt plate string from hex ciphertext."""
    if not ciphertext_hex:
        raise EncryptionError("ciphertext_hex cannot be empty")
    try:
        validated_key = _validate_fernet_key(key)
        cipher = Fernet(validated_key)
        ciphertext = bytes.fromhex(ciphertext_hex)
        plaintext = cipher.decrypt(ciphertext)
        return plaintext.decode("utf-8")
    except InvalidToken:
        raise EncryptionError("Invalid or tampered ciphertext") from None
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt: {e}") from e


def encrypt_batch(plate_strs: list[str], key: str) -> list[str]:
    """Encrypt multiple plates."""
    return [encrypt_plate_string(p, key) for p in plate_strs]


def decrypt_batch(ciphertexts_hex: list[str], key: str) -> list[str]:
    """Decrypt multiple plates."""
    return [decrypt_plate_string(c, key) for c in ciphertexts_hex]

