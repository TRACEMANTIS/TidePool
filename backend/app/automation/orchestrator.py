"""Campaign orchestration logic.

The ``CampaignOrchestrator`` glues together file parsing, database
persistence, template creation, and Celery task dispatch into a
single coherent workflow used by the automation API.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import AddressBook, Contact, ImportStatus
from app.models.email_template import EmailTemplate, TemplateCategory
from app.models.landing_page import LandingPage
from app.models.smtp_profile import SmtpProfile
from app.models.tracking import CampaignRecipient, RecipientStatus

from app.automation.file_parser import (
    ColumnMapping,
    parse_csv,
    parse_excel,
    validate_emails,
    BATCH_SIZE,
)

# Template variable pattern: {{variable_name}}
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


class OrchestratorError(Exception):
    """Raised when the orchestrator encounters a non-recoverable problem."""


class CampaignOrchestrator:
    """Coordinates the quick-launch workflow.

    Each public method is a discrete step that can be composed by the
    API router or invoked independently in tests.

    Parameters
    ----------
    db:
        An active async SQLAlchemy session.  The caller is responsible for
        committing or rolling back.
    user_id:
        The numeric ID of the authenticated user performing the action.
    """

    def __init__(self, db: AsyncSession, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    # ------------------------------------------------------------------
    # File ingestion
    # ------------------------------------------------------------------

    async def ingest_file(
        self,
        file_path: str | Path,
        column_mapping: ColumnMapping,
        book_name: str | None = None,
    ) -> tuple[AddressBook, int, int]:
        """Parse a contact file, persist an AddressBook and Contacts.

        Returns ``(address_book, valid_count, invalid_count)``.

        Contacts are inserted in batches of ``BATCH_SIZE`` to keep memory
        usage bounded.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            parser = parse_excel
        elif suffix == ".csv":
            parser = parse_csv
        else:
            raise OrchestratorError(f"Unsupported file type: {suffix}")

        # Create the address book record.
        address_book = AddressBook(
            name=book_name or path.stem,
            source_filename=path.name,
            import_status=ImportStatus.PROCESSING,
            column_mapping=dict(column_mapping),
        )
        self.db.add(address_book)
        await self.db.flush()  # Assign an id without committing.

        valid_count = 0
        invalid_count = 0
        batch: list[Contact] = []

        for contact_dict in parser(file_path, column_mapping):
            email = contact_dict.get("email", "")
            if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                invalid_count += 1
                continue

            batch.append(
                Contact(
                    email=email,
                    first_name=contact_dict.get("first_name"),
                    last_name=contact_dict.get("last_name"),
                    department=contact_dict.get("department"),
                    address_book_id=address_book.id,
                )
            )
            valid_count += 1

            if len(batch) >= BATCH_SIZE:
                self.db.add_all(batch)
                await self.db.flush()
                batch = []

        # Flush remaining batch.
        if batch:
            self.db.add_all(batch)
            await self.db.flush()

        address_book.import_status = ImportStatus.COMPLETED
        address_book.row_count = valid_count

        return address_book, valid_count, invalid_count

    # ------------------------------------------------------------------
    # Template creation
    # ------------------------------------------------------------------

    async def create_template(
        self,
        subject: str,
        body: str,
        category: str,
        from_name: str | None = None,
    ) -> EmailTemplate:
        """Create an EmailTemplate from the lure parameters."""
        try:
            cat = TemplateCategory(category)
        except ValueError:
            cat = TemplateCategory.CUSTOM

        # Extract variable names from the body.
        variables = sorted(set(_VAR_RE.findall(body)))

        template = EmailTemplate(
            name=f"Auto: {subject[:80]}",
            category=cat,
            difficulty=3,
            subject=subject,
            body_html=body,
            body_text=re.sub(r"<[^>]+>", "", body),
            variables=variables or None,
            created_by=self.user_id,
        )
        self.db.add(template)
        await self.db.flush()
        return template

    # ------------------------------------------------------------------
    # Campaign creation
    # ------------------------------------------------------------------

    async def create_campaign(
        self,
        name: str,
        address_book: AddressBook,
        template: EmailTemplate,
        smtp_profile_id: int,
        landing_page_id: int | None,
        send_window_hours: int,
    ) -> Campaign:
        """Create a Campaign and link all contacts as recipients.

        The throttle rate is computed so that all emails are spread
        evenly across ``send_window_hours``.
        """
        # Validate the SMTP profile exists.
        result = await self.db.execute(
            select(SmtpProfile).where(SmtpProfile.id == smtp_profile_id)
        )
        smtp_profile = result.scalar_one_or_none()
        if smtp_profile is None:
            raise OrchestratorError(
                f"SMTP profile {smtp_profile_id} does not exist."
            )

        # Validate landing page if provided.
        if landing_page_id is not None:
            result = await self.db.execute(
                select(LandingPage).where(LandingPage.id == landing_page_id)
            )
            if result.scalar_one_or_none() is None:
                raise OrchestratorError(
                    f"Landing page {landing_page_id} does not exist."
                )

        # Count contacts for throttle calculation.
        count_result = await self.db.execute(
            select(func.count(Contact.id)).where(
                Contact.address_book_id == address_book.id
            )
        )
        total = count_result.scalar() or 0

        send_window_minutes = send_window_hours * 60
        throttle = max(1, math.ceil(total / send_window_minutes)) if total else 1

        now = datetime.now(timezone.utc)

        campaign = Campaign(
            name=name,
            status=CampaignStatus.DRAFT,
            smtp_profile_id=smtp_profile_id,
            email_template_id=template.id,
            landing_page_id=landing_page_id,
            send_window_start=now,
            send_window_end=now + timedelta(hours=send_window_hours),
            throttle_rate=throttle,
            created_by=self.user_id,
        )
        self.db.add(campaign)
        await self.db.flush()

        # Create CampaignRecipient rows in batches.
        contact_result = await self.db.execute(
            select(Contact.id).where(
                Contact.address_book_id == address_book.id
            )
        )
        contact_ids = [row[0] for row in contact_result.all()]

        batch: list[CampaignRecipient] = []
        for cid in contact_ids:
            batch.append(
                CampaignRecipient(
                    campaign_id=campaign.id,
                    contact_id=cid,
                    status=RecipientStatus.PENDING,
                )
            )
            if len(batch) >= BATCH_SIZE:
                self.db.add_all(batch)
                await self.db.flush()
                batch = []

        if batch:
            self.db.add_all(batch)
            await self.db.flush()

        return campaign

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    async def launch(self, campaign_id: int) -> None:
        """Dispatch a campaign to the Celery send-mail task queue.

        The campaign status is moved to SCHEDULED.  The actual worker
        picks it up and transitions to RUNNING.
        """
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise OrchestratorError(f"Campaign {campaign_id} not found.")

        if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
            raise OrchestratorError(
                f"Campaign {campaign_id} is in status {campaign.status.value} "
                "and cannot be launched."
            )

        campaign.status = CampaignStatus.SCHEDULED
        await self.db.flush()

        # Dispatch to Celery.
        from app.celery_app import celery

        celery.send_task(
            "app.engine.send_campaign",
            kwargs={"campaign_id": campaign_id},
        )

    # ------------------------------------------------------------------
    # Abort
    # ------------------------------------------------------------------

    async def abort(self, campaign_id: int) -> None:
        """Abort a running or scheduled campaign."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise OrchestratorError(f"Campaign {campaign_id} not found.")

        if campaign.status not in (
            CampaignStatus.SCHEDULED,
            CampaignStatus.RUNNING,
        ):
            raise OrchestratorError(
                f"Campaign {campaign_id} is {campaign.status.value}; "
                "only SCHEDULED or RUNNING campaigns can be aborted."
            )

        campaign.status = CampaignStatus.CANCELLED
        await self.db.flush()

        # Revoke pending Celery task if possible.
        from app.celery_app import celery

        celery.control.revoke(
            f"campaign-{campaign_id}", terminate=True, signal="SIGTERM",
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_status(self, campaign_id: int) -> dict[str, Any]:
        """Return detailed send-status for a campaign."""
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise OrchestratorError(f"Campaign {campaign_id} not found.")

        # Count recipients by status.
        counts: dict[str, int] = {}
        for status in RecipientStatus:
            count_result = await self.db.execute(
                select(func.count()).where(
                    CampaignRecipient.campaign_id == campaign_id,
                    CampaignRecipient.status == status,
                )
            )
            counts[status.value] = count_result.scalar() or 0

        total = sum(counts.values())
        sent = counts.get(RecipientStatus.SENT.value, 0) + counts.get(
            RecipientStatus.DELIVERED.value, 0
        )
        pending = counts.get(RecipientStatus.PENDING.value, 0)
        failed = counts.get(RecipientStatus.FAILED.value, 0) + counts.get(
            RecipientStatus.BOUNCED.value, 0
        )

        # Estimate ETA from throttle rate.
        rate = float(campaign.throttle_rate or 1)
        eta = None
        if pending > 0 and campaign.status == CampaignStatus.RUNNING:
            minutes_remaining = pending / rate
            eta = datetime.now(timezone.utc) + timedelta(minutes=minutes_remaining)

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": campaign.status.value,
            "sent": sent,
            "pending": pending,
            "failed": failed,
            "total": total,
            "rate_per_minute": rate,
            "eta": eta,
        }

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def preview(
        self,
        file_path: str | Path,
        column_mapping: ColumnMapping,
        subject: str,
        body: str,
        count: int = 5,
    ) -> tuple[list[dict[str, str]], int]:
        """Render preview emails without touching the database.

        Returns ``(previews, total_rows)`` where ``previews`` is a list
        of up to ``count`` dicts with keys ``to``, ``subject``, and
        ``body_preview``.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            parser = parse_excel
        elif suffix == ".csv":
            parser = parse_csv
        else:
            raise OrchestratorError(f"Unsupported file type: {suffix}")

        previews: list[dict[str, str]] = []
        total = 0

        for contact in parser(file_path, column_mapping):
            total += 1
            if len(previews) < count:
                rendered_subject = self._render(subject, contact)
                rendered_body = self._render(body, contact)
                previews.append({
                    "to": contact.get("email", ""),
                    "subject": rendered_subject,
                    "body_preview": rendered_body[:500],
                })

        return previews, total

    @staticmethod
    def _render(template: str, contact: dict[str, Any]) -> str:
        """Replace ``{{variable}}`` placeholders with contact values."""
        def _replace(match: re.Match) -> str:
            key = match.group(1)
            val = contact.get(key)
            if val is not None:
                return str(val)
            return match.group(0)  # Leave unresolved vars as-is.

        return _VAR_RE.sub(_replace, template)
