"""Field-level encryption utilities for sensitive database columns.

Uses Fernet symmetric encryption (via the ``cryptography`` library) keyed
from ``config.ENCRYPTION_KEY``.  Supports key rotation through MultiFernet
when multiple comma-separated keys are provided in the environment variable.

Usage in SQLAlchemy models::

    from app.utils.encryption import EncryptedField

    class SmtpProfile(Base):
        password: Mapped[str | None] = mapped_column(
            EncryptedField(), nullable=True,
        )
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import String, TypeDecorator

from app.config import settings


def _build_fernet() -> MultiFernet:
    """Build a MultiFernet instance from the configured encryption key(s).

    The ``ENCRYPTION_KEY`` setting may contain multiple comma-separated
    Fernet keys to support key rotation.  The *first* key is used for
    encryption; all keys are tried during decryption.
    """
    raw_keys = [k.strip() for k in settings.ENCRYPTION_KEY.split(",") if k.strip()]
    if not raw_keys:
        raise ValueError("ENCRYPTION_KEY must contain at least one valid Fernet key.")
    fernets = [Fernet(k.encode() if isinstance(k, str) else k) for k in raw_keys]
    return MultiFernet(fernets)


def encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* and return a base64-encoded ciphertext string."""
    f = _build_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded *ciphertext* string back to plaintext."""
    f = _build_fernet()
    raw_token = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    return f.decrypt(raw_token).decode("utf-8")


class EncryptedField(TypeDecorator):
    """SQLAlchemy ``TypeDecorator`` that transparently encrypts on write
    and decrypts on read.

    The underlying column type is ``String`` (TEXT).  Values stored in the
    database are Fernet-encrypted and base64-encoded, making them opaque
    to anyone with database access but without the application key.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt before writing to the database."""
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        """Decrypt after reading from the database."""
        if value is None:
            return None
        return decrypt_value(value)
