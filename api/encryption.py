"""
Fernet symmetric encryption for sensitive plate strings.

Implements cryptography.fernet for deterministic, authenticated encryption.
Plate strings encrypted at rest in database; decrypted on read for audit purposes.

Key rotation strategy:
- DEV: Single key from FERNET_KEY env var
- PROD: Envelope encryption (master key in KMS, derive DEK per region)

FERNET_KEY format: 44-character URL-safe base64 string (32 bytes key)
Generate with: from cryptography.fernet import Fernet; Fernet.generate_key()
"""

import base64
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""
    pass


def _validate_fernet_key(key: Optional[str]) -> str:
    """
    Validate and return a Fernet key.

    Args:
        key: URL-safe base64 Fernet key (44 characters, 32 bytes).

    Returns:
        Valid Fernet key (str).

    Raises:
        EncryptionError: If key is invalid or missing.
    """
    if not key:
        raise EncryptionError("FERNET_KEY environment variable is not set")
    if len(key) != 44:
        raise EncryptionError(f"FERNET_KEY must be 44 characters, got {len(key)}")

    try:
        # Validate it's a valid Fernet key by decoding
        base64.urlsafe_b64decode(key)
        return key
    except Exception as e:
        raise EncryptionError(f"Invalid FERNET_KEY format: {e}") from e


def encrypt_plate_string(plate_str: str, key: str) -> str:
    """
    Encrypt a plate string using Fernet.

    Args:
        plate_str: Plain-text plate string (e.g., "CA-12345").
        key: Fernet key (44 chars, from FERNET_KEY env var).

    Returns:
        Encrypted ciphertext as hex string.

    Raises:
        EncryptionError: If encryption fails.
    """
    if not plate_str:
        raise EncryptionError("plate_str cannot be empty")

    try:
        validated_key = _validate_fernet_key(key)
        cipher = Fernet(validated_key)
        ciphertext = cipher.encrypt(plate_str.encode("utf-8"))
        # Return as hex for database storage (easier to index/debug than base64)
        return ciphertext.hex()
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt plate string: {e}") from e


def decrypt_plate_string(ciphertext_hex: str, key: str) -> str:
    """
    Decrypt a plate string from ciphertext.

    Args:
        ciphertext_hex: Encrypted ciphertext as hex string.
        key: Fernet key (44 chars, from FERNET_KEY env var).

    Returns:
        Plain-text plate string.

    Raises:
        EncryptionError: If decryption fails.
    """
    if not ciphertext_hex:
        raise EncryptionError("ciphertext_hex cannot be empty")

    try:
        validated_key = _validate_fernet_key(key)
        cipher = Fernet(validated_key)
        # Convert hex back to bytes
        ciphertext = bytes.fromhex(ciphertext_hex)
        plaintext = cipher.decrypt(ciphertext)
        return plaintext.decode("utf-8")
    except InvalidToken:
        raise EncryptionError("Invalid or tampered ciphertext (authentication failed)") from None
    except EncryptionError:
        raise
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt plate string: {e}") from e


def encrypt_batch(plate_strs: list[str], key: str) -> list[str]:
    """
    Encrypt multiple plate strings (vectorized).

    Args:
        plate_strs: List of plain-text plate strings.
        key: Fernet key.

    Returns:
        List of encrypted ciphertexts (hex).

    Raises:
        EncryptionError: If any encryption fails.
    """
    return [encrypt_plate_string(p, key) for p in plate_strs]


def decrypt_batch(ciphertexts_hex: list[str], key: str) -> list[str]:
    """
    Decrypt multiple plate strings (vectorized).

    Args:
        ciphertexts_hex: List of encrypted ciphertexts (hex).
        key: Fernet key.

    Returns:
        List of plain-text plate strings.

    Raises:
        EncryptionError: If any decryption fails.
    """
    return [decrypt_plate_string(c, key) for c in ciphertexts_hex]
