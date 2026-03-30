"""Landing page model for credential-capture and awareness pages."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class PageType(str, enum.Enum):
    TEMPLATE = "TEMPLATE"
    CLONED = "CLONED"
    CUSTOM = "CUSTOM"


class LandingPage(TimestampMixin, Base):
    __tablename__ = "landing_pages"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    page_type: Mapped[PageType] = mapped_column(
        Enum(PageType, name="page_type", native_enum=False),
        nullable=False,
    )
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="URL to redirect to after form submission",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )

    # -- Relationships --
    creator: Mapped[User] = relationship(
        "User", back_populates="landing_pages", lazy="joined",
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        "Campaign", back_populates="landing_page", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<LandingPage id={self.id} name={self.name!r} type={self.page_type.value}>"


# Resolve forward references.
from app.models.user import User  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
