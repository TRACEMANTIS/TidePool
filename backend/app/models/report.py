"""Report snapshot model for persisted campaign analytics."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportType(str, enum.Enum):
    EXECUTIVE = "EXECUTIVE"
    DEPARTMENT = "DEPARTMENT"
    COMPLIANCE = "COMPLIANCE"
    CUSTOM = "CUSTOM"


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False,
    )
    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="report_type", native_enum=False),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False,
    )
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    generated_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )

    # -- Relationships --
    campaign: Mapped[Campaign] = relationship(
        "Campaign", back_populates="report_snapshots", lazy="joined",
    )
    generator: Mapped[User] = relationship(
        "User", back_populates="report_snapshots", lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<ReportSnapshot id={self.id} campaign={self.campaign_id} "
            f"type={self.report_type.value}>"
        )


# Resolve forward references.
from app.models.campaign import Campaign  # noqa: E402
from app.models.user import User  # noqa: E402
