"""Email template model for phishing simulation pretexts."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TemplateCategory(str, enum.Enum):
    IT = "IT"
    HR = "HR"
    FINANCE = "FINANCE"
    EXECUTIVE = "EXECUTIVE"
    VENDOR = "VENDOR"
    CUSTOM = "CUSTOM"


class EmailTemplate(TimestampMixin, Base):
    __tablename__ = "email_templates"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[TemplateCategory] = mapped_column(
        Enum(TemplateCategory, name="template_category", native_enum=False),
        nullable=False,
    )
    difficulty: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Difficulty rating from 1 (easy) to 5 (hard)",
    )
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="List of variable names used in the template",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False,
    )

    # -- Relationships --
    creator: Mapped[User] = relationship(
        "User", back_populates="email_templates", lazy="joined",
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        "Campaign", back_populates="email_template", lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<EmailTemplate id={self.id} name={self.name!r} "
            f"category={self.category.value}>"
        )


# Resolve forward references.
from app.models.user import User  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
