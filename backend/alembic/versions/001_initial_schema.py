"""Initial schema -- create all TidePool tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("full_name", sa.String(length=256), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    # ------------------------------------------------------------------
    # api_keys
    # ------------------------------------------------------------------
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("key_prefix", sa.String(length=12), nullable=False, comment="First 8 chars of the raw key for display/identification."),
        sa.Column("key_hash", sa.String(length=256), nullable=False, comment="Bcrypt hash of the full API key."),
        sa.Column("name", sa.String(length=128), nullable=False, comment="Human-readable label for this key."),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Allowed scopes, e.g. ["campaigns:read", "automation:*"].'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # ------------------------------------------------------------------
    # smtp_profiles
    # ------------------------------------------------------------------
    op.create_table(
        "smtp_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "backend_type",
            sa.Enum("SMTP", "SES", "MAILGUN", "SENDGRID", name="backend_type", native_enum=False),
            nullable=False,
            server_default="SMTP",
        ),
        sa.Column("host", sa.String(length=256), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=256), nullable=True),
        sa.Column("password", sa.Text(), nullable=True, comment="Fernet-encrypted at rest"),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("from_address", sa.String(length=320), nullable=False),
        sa.Column("from_name", sa.String(length=256), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Non-sensitive backend settings (region, endpoint, etc.)"),
        sa.Column(
            "encrypted_credentials", sa.Text(), nullable=True,
            comment="Fernet-encrypted JSON blob of sensitive credentials (api_key, api_secret, etc.)",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    # ------------------------------------------------------------------
    # address_books
    # ------------------------------------------------------------------
    op.create_table(
        "address_books",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column(
            "import_status",
            sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="import_status", native_enum=False),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # contacts
    # ------------------------------------------------------------------
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("custom_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("address_book_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["address_book_id"], ["address_books.id"]),
        sa.UniqueConstraint("email", "address_book_id", name="uq_contact_email_book"),
    )
    op.create_index("ix_contacts_email", "contacts", ["email"])

    # ------------------------------------------------------------------
    # groups
    # ------------------------------------------------------------------
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # group_members (composite PK, no TimestampMixin)
    # ------------------------------------------------------------------
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("group_id", "contact_id"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
    )

    # ------------------------------------------------------------------
    # email_templates
    # ------------------------------------------------------------------
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "category",
            sa.Enum("IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR", "CUSTOM", name="template_category", native_enum=False),
            nullable=False,
        ),
        sa.Column("difficulty", sa.Integer(), nullable=False, comment="Difficulty rating from 1 (easy) to 5 (hard)"),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="List of variable names used in the template"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    # ------------------------------------------------------------------
    # landing_pages
    # ------------------------------------------------------------------
    op.create_table(
        "landing_pages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "page_type",
            sa.Enum("TEMPLATE", "CLONED", "CUSTOM", name="page_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("redirect_url", sa.String(length=2048), nullable=True, comment="URL to redirect to after form submission"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    # ------------------------------------------------------------------
    # campaigns
    # ------------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "SCHEDULED", "RUNNING", "PAUSED", "COMPLETED", "CANCELLED", name="campaign_status", native_enum=False),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("smtp_profile_id", sa.Integer(), nullable=False),
        sa.Column("email_template_id", sa.Integer(), nullable=False),
        sa.Column("landing_page_id", sa.Integer(), nullable=True),
        sa.Column("send_window_start", sa.DateTime(), nullable=True),
        sa.Column("send_window_end", sa.DateTime(), nullable=True),
        sa.Column("throttle_rate", sa.Integer(), nullable=True, comment="Maximum emails per minute"),
        sa.Column(
            "training_redirect_url", sa.String(length=2048), nullable=True,
            comment="External URL users are redirected to after falling for the phish",
        ),
        sa.Column(
            "training_redirect_delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("0"),
            comment="Seconds to show interstitial before redirecting to training URL",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["smtp_profile_id"], ["smtp_profiles.id"]),
        sa.ForeignKeyConstraint(["email_template_id"], ["email_templates.id"]),
        sa.ForeignKeyConstraint(["landing_page_id"], ["landing_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )

    # ------------------------------------------------------------------
    # campaign_recipients (composite PK, no TimestampMixin)
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_recipients",
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "DELIVERED", "BOUNCED", "FAILED", name="recipient_status", native_enum=False),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("campaign_id", "contact_id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_campaign_recipients_token", "campaign_recipients", ["token"])

    # ------------------------------------------------------------------
    # tracking_events
    # ------------------------------------------------------------------
    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("recipient_token", sa.String(length=36), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("SENT", "DELIVERED", "OPENED", "CLICKED", "SUBMITTED", "REPORTED", name="event_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="user_agent, ip, field_names for submissions, etc."),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )
    op.create_index("ix_tracking_events_recipient_token", "tracking_events", ["recipient_token"])
    op.create_index("ix_tracking_events_campaign_event", "tracking_events", ["campaign_id", "event_type"])

    # ------------------------------------------------------------------
    # audit_logs (note: model uses "audit_logs" not "audit_log")
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False, comment="Username or 'system' for automated actions"),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # report_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column(
            "report_type",
            sa.Enum("EXECUTIVE", "DEPARTMENT", "COMPLIANCE", "CUSTOM", name="report_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("generated_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"]),
    )

    # ------------------------------------------------------------------
    # training_redirects
    # ------------------------------------------------------------------
    op.create_table(
        "training_redirects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("recipient_token", sa.String(length=128), nullable=False),
        sa.Column("redirected_at", sa.DateTime(), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )
    op.create_index("ix_training_redirects_campaign_id", "training_redirects", ["campaign_id"])
    op.create_index("ix_training_redirects_recipient_token", "training_redirects", ["recipient_token"])


def downgrade() -> None:
    # Drop tables in reverse dependency order.
    op.drop_table("training_redirects")
    op.drop_table("report_snapshots")
    op.drop_table("audit_logs")
    op.drop_table("tracking_events")
    op.drop_table("campaign_recipients")
    op.drop_table("campaigns")
    op.drop_table("landing_pages")
    op.drop_table("email_templates")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("contacts")
    op.drop_table("address_books")
    op.drop_table("smtp_profiles")
    op.drop_table("api_keys")
    op.drop_table("users")
