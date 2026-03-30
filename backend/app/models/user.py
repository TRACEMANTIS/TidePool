"""User model for authentication and ownership tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # -- Account lockout fields --
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # -- Relationships --
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="user", lazy="selectin",
        cascade="all, delete-orphan",
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        "Campaign", back_populates="creator", lazy="selectin",
    )
    email_templates: Mapped[list[EmailTemplate]] = relationship(
        "EmailTemplate", back_populates="creator", lazy="selectin",
    )
    landing_pages: Mapped[list[LandingPage]] = relationship(
        "LandingPage", back_populates="creator", lazy="selectin",
    )
    smtp_profiles: Mapped[list[SmtpProfile]] = relationship(
        "SmtpProfile", back_populates="creator", lazy="selectin",
    )
    report_snapshots: Mapped[list[ReportSnapshot]] = relationship(
        "ReportSnapshot", back_populates="generator", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


# Resolve forward references at import time.
from app.models.api_key import ApiKey  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.models.email_template import EmailTemplate  # noqa: E402
from app.models.landing_page import LandingPage  # noqa: E402
from app.models.smtp_profile import SmtpProfile  # noqa: E402
from app.models.report import ReportSnapshot  # noqa: E402
