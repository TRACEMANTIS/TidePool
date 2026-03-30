"""SMTP / mail-provider profile model.

Sensitive credentials (password, API keys) are encrypted at rest using
Fernet field-level encryption via ``EncryptedField``.  The encryption key
is sourced from ``config.ENCRYPTION_KEY`` and supports key rotation.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.utils.encryption import EncryptedField


class BackendType(str, enum.Enum):
    SMTP = "SMTP"
    SES = "SES"
    MAILGUN = "MAILGUN"
    SENDGRID = "SENDGRID"
    BENCHMARK = "BENCHMARK"


class SmtpProfile(TimestampMixin, Base):
    __tablename__ = "smtp_profiles"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    backend_type: Mapped[BackendType] = mapped_column(
        Enum(BackendType, name="backend_type", native_enum=False),
        default=BackendType.SMTP,
        nullable=False,
    )

    # Connection details
    host: Mapped[str | None] = mapped_column(String(256), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Password -- encrypted at rest via Fernet EncryptedField.
    password: Mapped[str | None] = mapped_column(
        EncryptedField(), nullable=True,
        comment="Fernet-encrypted at rest",
    )
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    from_address: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Backend-specific settings (non-sensitive portions: region, endpoint, etc.)
    # NOTE: API keys and other secrets should NOT be stored here. Use
    # encrypted_credentials below for sensitive values.
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Non-sensitive backend settings (region, endpoint, etc.)",
    )

    # Encrypted blob for sensitive backend credentials (password, api_key,
    # api_secret, etc.) stored as a Fernet-encrypted JSON string.  Keeps
    # secrets separate from the plaintext config JSONB column.
    encrypted_credentials: Mapped[str | None] = mapped_column(
        EncryptedField(), nullable=True,
        comment="Fernet-encrypted JSON blob of sensitive credentials (api_key, api_secret, etc.)",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )

    # -- Relationships --
    creator: Mapped[User] = relationship(
        "User", back_populates="smtp_profiles", lazy="joined",
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        "Campaign", back_populates="smtp_profile", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<SmtpProfile id={self.id} name={self.name!r} "
            f"backend={self.backend_type.value}>"
        )


# Resolve forward references.
from app.models.user import User  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
