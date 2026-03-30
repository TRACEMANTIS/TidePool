"""Training redirect tracking model.

Records which recipients were redirected to the external training URL
configured on their campaign. The actual training content is hosted
externally (KnowBe4, internal LMS, SharePoint, etc.) -- TidePool only
tracks that the redirect occurred.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TrainingRedirect(TimestampMixin, Base):
    """Records that a phished recipient was redirected to training."""

    __tablename__ = "training_redirects"

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, index=True,
    )
    recipient_token: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
    )
    redirected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True,
    )

    # -- Relationships --
    campaign: Mapped[Campaign] = relationship(
        "Campaign", foreign_keys=[campaign_id], lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<TrainingRedirect id={self.id} "
            f"campaign={self.campaign_id} token={self.recipient_token!r}>"
        )


# Resolve forward references.
from app.models.campaign import Campaign  # noqa: E402
