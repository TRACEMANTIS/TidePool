"""Address book, contact, group, and group membership models."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ImportStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# AddressBook
# ---------------------------------------------------------------------------

class AddressBook(TimestampMixin, Base):
    __tablename__ = "address_books"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    import_status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status", native_enum=False),
        default=ImportStatus.PENDING,
        nullable=False,
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # -- Relationships --
    contacts: Mapped[list[Contact]] = relationship(
        "Contact", back_populates="address_book", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AddressBook id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("email", "address_book_id", name="uq_contact_email_book"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    is_valid_email: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true",
        comment="Set to False on hard bounce",
    )
    do_not_email: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
        comment="Set to True on spam complaint",
    )
    bounce_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0",
        comment="Incremented on each bounce event",
    )

    address_book_id: Mapped[int] = mapped_column(
        ForeignKey("address_books.id"), nullable=False,
    )

    # -- Relationships --
    address_book: Mapped[AddressBook] = relationship(
        "AddressBook", back_populates="contacts", lazy="joined",
    )
    group_memberships: Mapped[list[GroupMember]] = relationship(
        "GroupMember", back_populates="contact", lazy="selectin",
        cascade="all, delete-orphan",
    )
    campaign_assignments: Mapped[list[CampaignRecipient]] = relationship(
        "CampaignRecipient", back_populates="contact", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Contact id={self.id} email={self.email!r}>"


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------

class Group(TimestampMixin, Base):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Relationships --
    members: Mapped[list[GroupMember]] = relationship(
        "GroupMember", back_populates="group", lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# GroupMember (association table with composite PK)
# ---------------------------------------------------------------------------

class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id"), primary_key=True,
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"), primary_key=True,
    )

    # -- Relationships --
    group: Mapped[Group] = relationship(
        "Group", back_populates="members", lazy="joined",
    )
    contact: Mapped[Contact] = relationship(
        "Contact", back_populates="group_memberships", lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<GroupMember group_id={self.group_id} contact_id={self.contact_id}>"


# Resolve forward references.
from app.models.tracking import CampaignRecipient  # noqa: E402
