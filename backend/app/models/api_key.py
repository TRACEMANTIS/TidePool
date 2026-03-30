"""API key model for programmatic authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    key_prefix: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True,
        comment="First 8 chars of the raw key for display/identification.",
    )
    key_hash: Mapped[str] = mapped_column(
        String(256), nullable=False, unique=True,
        comment="Bcrypt hash of the full API key.",
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Human-readable label for this key.",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    scopes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        comment='Allowed scopes, e.g. ["campaigns:read", "automation:*"].',
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # -- Relationships --
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return (
            f"<ApiKey id={self.id} name={self.name!r} "
            f"prefix={self.key_prefix!r} user_id={self.user_id}>"
        )


# Resolve forward reference.
from app.models.user import User  # noqa: E402
