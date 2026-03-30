"""Add BENCHMARK backend type.

Revision ID: 002
Revises: 001
Create Date: 2026-03-27

BackendType is stored as VARCHAR (native_enum=False) in the smtp_profiles
table, so adding a new enum member does not require any DDL changes.  The
SQLAlchemy Enum with native_enum=False simply validates in Python; the
database column already accepts any string value.

This migration exists for documentation and revision-chain continuity.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No DDL changes required.  BackendType is stored as VARCHAR
    # (native_enum=False), so the new BENCHMARK value is handled
    # entirely in application code.
    pass


def downgrade() -> None:
    # No DDL changes to reverse.  Rows with backend_type='BENCHMARK'
    # would need to be manually cleaned up or migrated if rolling back
    # past this point.
    pass
