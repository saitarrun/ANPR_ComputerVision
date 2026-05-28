"""Encrypted field types using SQLAlchemy TypeDecorator."""

import base64
import os
from typing import Any, Optional
from cryptography.fernet import Fernet
from sqlalchemy import TypeDecorator, String
from sqlalchemy.orm import Mapped, mapped_column


class EncryptedString(TypeDecorator):
    """SQLAlchemy column type for encrypted strings.
    
    Encrypts on INSERT, decrypts on SELECT automatically.
    Uses Fernet (symmetric, AES-128).
    
    In dev: inline key from FERNET_KEY env var.
    In prod: would use envelope encryption (key encrypted by KMS).
    """
    
    impl = String
    cache_ok = True
    
    def __init__(self, key: Optional[str] = None):
        super().__init__()
        if key:
            self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            # Fallback: read from env (should always be set in config)
            from api.settings import settings
            if settings.fernet_key:
                self.cipher = Fernet(settings.fernet_key.encode())
            else:
                # Generate a throwaway key for testing (not secure)
                self.cipher = Fernet(Fernet.generate_key())
    
    def process_bind_param(self, value: Optional[str], dialect: Any) -> Optional[str]:
        """Encrypt plaintext before insert/update."""
        if value is None:
            return None
        plaintext_bytes = value.encode('utf-8') if isinstance(value, str) else value
        ciphertext = self.cipher.encrypt(plaintext_bytes)
        # Store as base64 string for DB compatibility
        return base64.b64encode(ciphertext).decode('utf-8')
    
    def process_result_value(self, value: Optional[str], dialect: Any) -> Optional[str]:
        """Decrypt ciphertext after SELECT."""
        if value is None:
            return None
        try:
            ciphertext = base64.b64decode(value.encode('utf-8'))
            plaintext = self.cipher.decrypt(ciphertext)
            return plaintext.decode('utf-8')
        except Exception as e:
            # Log decryption failure (corrupted or wrong key)
            import logging
            logging.error(f"Decryption failed: {e}")
            return None
