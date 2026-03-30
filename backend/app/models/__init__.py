"""TidePool ORM models -- import and re-export all models for convenient access."""

from app.models.base import TimestampMixin

from app.models.user import User
from app.models.api_key import ApiKey
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import (
    AddressBook,
    Contact,
    Group,
    GroupMember,
    ImportStatus,
)
from app.models.email_template import EmailTemplate, TemplateCategory
from app.models.landing_page import LandingPage, PageType
from app.models.smtp_profile import SmtpProfile, BackendType
from app.models.tracking import (
    CampaignRecipient,
    EventType,
    RecipientStatus,
    TrackingEvent,
)
from app.models.audit import AuditLog
from app.models.report import ReportSnapshot, ReportType

__all__ = [
    # Mixins
    "TimestampMixin",
    # Core models
    "User",
    "ApiKey",
    "Campaign",
    "AddressBook",
    "Contact",
    "Group",
    "GroupMember",
    "EmailTemplate",
    "LandingPage",
    "SmtpProfile",
    "CampaignRecipient",
    "TrackingEvent",
    "AuditLog",
    "ReportSnapshot",
    # Enums
    "BackendType",
    "CampaignStatus",
    "EventType",
    "ImportStatus",
    "PageType",
    "RecipientStatus",
    "ReportType",
    "TemplateCategory",
]
