"""Encryption utilities for storing sensitive data like Gmail app passwords."""

import base64
import os

from cryptography.fernet import Fernet
from django.conf import settings


def _get_fernet():
    """Get or generate a Fernet encryption key."""
    key = settings.ENCRYPTION_KEY
    if not key:
        # Auto-generate and warn in development
        key = Fernet.generate_key().decode()
        import warnings

        warnings.warn(
            "ENCRYPTION_KEY not set in environment. Using auto-generated key. "
            "Set ENCRYPTION_KEY in .env for production use.",
            stacklevel=2,
        )
    else:
        # Ensure key is properly formatted
        if isinstance(key, str):
            try:
                # Try to use as-is (base64-encoded Fernet key)
                Fernet(key.encode())
                key = key.encode()
            except Exception:
                # Derive a Fernet-compatible key from the provided string
                key = base64.urlsafe_b64encode(key.ljust(32)[:32].encode())
        else:
            key = key
    return Fernet(key if isinstance(key, bytes) else key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return the ciphertext as a string."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string and return the plaintext."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()