"""Audit log model for tracking all state-changing actions."""

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    actor: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Username or 'system' for automated actions",
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)

    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)

    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    timestamp: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} actor={self.actor!r} "
            f"action={self.action!r} resource={self.resource_type}/{self.resource_id}>"
        )
