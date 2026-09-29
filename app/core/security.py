"""Fernet-based encryption helpers for at-rest token protection."""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import settings


_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    """Return a singleton Fernet instance, creating it on first call."""
    global _fernet
    if _fernet is None:
        key = settings.token_encryption_key
        if not key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is not set. "
                "Run 'python scripts/gen_key.py' to generate one."
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_token(plain: str) -> str:
    """Encrypt a plain-text token string → Fernet ciphertext (str)."""
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_token(cipher: str) -> str:
    """Decrypt a Fernet ciphertext → plain-text token string."""
    return get_fernet().decrypt(cipher.encode()).decode()


def reset_fernet() -> None:
    """Reset the cached Fernet instance.

    Useful in tests when TOKEN_ENCRYPTION_KEY changes between test cases.
    """
    global _fernet
    _fernet = None
