"""Campaign recipient and tracking event models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RecipientStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    FAILED = "FAILED"


class EventType(str, enum.Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    OPENED = "OPENED"
    CLICKED = "CLICKED"
    SUBMITTED = "SUBMITTED"
    REPORTED = "REPORTED"


# ---------------------------------------------------------------------------
# CampaignRecipient
# ---------------------------------------------------------------------------

class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), primary_key=True,
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"), primary_key=True,
    )
    token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True,
        nullable=False,
    )
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status", native_enum=False),
        default=RecipientStatus.PENDING,
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # -- Relationships --
    campaign: Mapped[Campaign] = relationship(
        "Campaign", back_populates="recipients", lazy="joined",
    )
    contact: Mapped[Contact] = relationship(
        "Contact", back_populates="campaign_assignments", lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignRecipient campaign={self.campaign_id} "
            f"contact={self.contact_id} status={self.status.value}>"
        )


# ---------------------------------------------------------------------------
# TrackingEvent
# ---------------------------------------------------------------------------

class TrackingEvent(Base):
    __tablename__ = "tracking_events"
    __table_args__ = (
        Index("ix_tracking_events_campaign_event", "campaign_id", "event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False,
    )
    recipient_token: Mapped[str] = mapped_column(
        String(36), index=True, nullable=False,
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type", native_enum=False),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True,
        comment="user_agent, ip, field_names for submissions, etc.",
    )

    # -- Relationships --
    campaign: Mapped[Campaign] = relationship(
        "Campaign", back_populates="tracking_events", lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<TrackingEvent id={self.id} type={self.event_type.value} "
            f"token={self.recipient_token}>"
        )


# Resolve forward references.
from app.models.campaign import Campaign  # noqa: E402
from app.models.contact import Contact  # noqa: E402
