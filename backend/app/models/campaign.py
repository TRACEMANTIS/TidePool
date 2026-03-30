"""Campaign model -- the central orchestration entity for a phishing simulation."""

from __future__ import annotations

import enum
from datetime import datetime

from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class CampaignStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status", native_enum=False),
        default=CampaignStatus.DRAFT,
        nullable=False,
    )

    smtp_profile_id: Mapped[int] = mapped_column(
        ForeignKey("smtp_profiles.id"), nullable=False,
    )
    email_template_id: Mapped[int] = mapped_column(
        ForeignKey("email_templates.id"), nullable=False,
    )
    landing_page_id: Mapped[int | None] = mapped_column(
        ForeignKey("landing_pages.id"), nullable=True,
    )

    send_window_start: Mapped[datetime | None] = mapped_column(nullable=True)
    send_window_end: Mapped[datetime | None] = mapped_column(nullable=True)
    throttle_rate: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Maximum emails per minute",
    )

    training_redirect_url: Mapped[Optional[str]] = mapped_column(
        String(2048), nullable=True,
        comment="External URL users are redirected to after falling for the phish",
    )
    training_redirect_delay_seconds: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Seconds to show interstitial before redirecting to training URL",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )

    # -- Relationships --
    creator: Mapped[User] = relationship(
        "User", back_populates="campaigns", lazy="joined",
    )
    smtp_profile: Mapped[SmtpProfile] = relationship(
        "SmtpProfile", back_populates="campaigns", lazy="joined",
    )
    email_template: Mapped[EmailTemplate] = relationship(
        "EmailTemplate", back_populates="campaigns", lazy="joined",
    )
    landing_page: Mapped[LandingPage | None] = relationship(
        "LandingPage", back_populates="campaigns", lazy="joined",
    )
    recipients: Mapped[list[CampaignRecipient]] = relationship(
        "CampaignRecipient", back_populates="campaign", lazy="selectin",
    )
    tracking_events: Mapped[list[TrackingEvent]] = relationship(
        "TrackingEvent", back_populates="campaign", lazy="selectin",
    )
    report_snapshots: Mapped[list[ReportSnapshot]] = relationship(
        "ReportSnapshot", back_populates="campaign", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} name={self.name!r} status={self.status.value}>"


# Resolve forward references.
from app.models.user import User  # noqa: E402
from app.models.smtp_profile import SmtpProfile  # noqa: E402
from app.models.email_template import EmailTemplate  # noqa: E402
from app.models.landing_page import LandingPage  # noqa: E402
from app.models.tracking import CampaignRecipient, TrackingEvent  # noqa: E402
from app.models.report import ReportSnapshot  # noqa: E402
