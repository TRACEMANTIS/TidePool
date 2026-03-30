"""Compliance package generator for TidePool campaigns.

Produces an evidence bundle suitable for auditors: PDF summary, CSV data files,
event timeline, and integrity hashes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.tracking import CampaignRecipient, TrackingEvent
from app.reports.aggregator import MetricsAggregator
from app.reports.executive import ExecutiveReportGenerator
from app.reports.export import export_pdf


class CompliancePackageGenerator:
    """Generate compliance-grade evidence packages."""

    def __init__(self) -> None:
        self._aggregator = MetricsAggregator()
        self._exec_gen = ExecutiveReportGenerator()

    async def generate(self, campaign_id: int, db: AsyncSession) -> dict[str, Any]:
        """Produce the compliance data structure for a campaign."""
        metrics = await self._aggregator.get_campaign_metrics(campaign_id, db)
        departments = await self._aggregator.get_department_metrics(campaign_id, db)

        # Campaign snapshot
        camp_q = select(Campaign).where(Campaign.id == campaign_id)
        campaign = (await db.execute(camp_q)).scalar_one_or_none()

        evidence_of_test: dict[str, Any] = {}
        if campaign:
            evidence_of_test = {
                "campaign_id": campaign.id,
                "name": campaign.name,
                "status": campaign.status.value if hasattr(campaign.status, "value") else str(campaign.status),
                "smtp_profile_id": campaign.smtp_profile_id,
                "email_template_id": campaign.email_template_id,
                "landing_page_id": campaign.landing_page_id,
                "send_window_start": (
                    campaign.send_window_start.isoformat()
                    if campaign.send_window_start else None
                ),
                "send_window_end": (
                    campaign.send_window_end.isoformat()
                    if campaign.send_window_end else None
                ),
                "training_redirect_url": campaign.training_redirect_url,
                "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            }

        # Participation rate
        total_org = metrics.total_recipients  # best approximation from recipients
        participation_rate = (
            round(metrics.sent / total_org * 100, 2) if total_org > 0 else 0.0
        )

        # Training redirect stats (CLICKED events approximate training redirect reach)
        training_redirect_count = metrics.clicked

        # Department completion
        dept_completion = [
            {
                "department": d.name,
                "headcount": d.headcount,
                "sent": d.sent,
                "opened": d.opened,
                "clicked": d.clicked,
                "submitted": d.submitted,
                "reported": d.reported,
                "risk_score": d.risk_score,
            }
            for d in departments
        ]

        # Full event timeline
        events_q = (
            select(TrackingEvent)
            .where(TrackingEvent.campaign_id == campaign_id)
            .order_by(TrackingEvent.timestamp)
        )
        events = (await db.execute(events_q)).scalars().all()
        timeline = [
            {
                "id": ev.id,
                "recipient_token": ev.recipient_token,
                "event_type": ev.event_type.value if hasattr(ev.event_type, "value") else ev.event_type,
                "timestamp": ev.timestamp.isoformat(),
                "metadata": ev.metadata_,
            }
            for ev in events
        ]

        package = {
            "evidence_of_test": evidence_of_test,
            "participation_rate": participation_rate,
            "completion_summary": {
                "sent": metrics.sent,
                "delivered": metrics.delivered,
                "opened": metrics.opened,
                "clicked": metrics.clicked,
                "submitted": metrics.submitted,
                "reported": metrics.reported,
            },
            "training_redirect_stats": {
                "reached_training_url": training_redirect_count,
            },
            "department_completion": dept_completion,
            "timeline": timeline,
        }

        # Integrity hash of the entire package
        package_json = json.dumps(package, sort_keys=True, default=str)
        package["integrity_hash"] = hashlib.sha256(package_json.encode()).hexdigest()

        return package

    async def export_package(self, campaign_id: int, db: AsyncSession) -> bytes:
        """Produce a ZIP archive containing all compliance artefacts."""
        package = await self.generate(campaign_id, db)

        # Generate executive PDF
        exec_report = await self._exec_gen.generate(campaign_id, db)
        pdf_bytes = await export_pdf(exec_report, "executive")

        # Build CSV data
        metrics = await self._aggregator.get_campaign_metrics(campaign_id, db)
        departments = await self._aggregator.get_department_metrics(campaign_id, db)

        # Detailed metrics CSV
        metrics_csv = self._dict_to_csv([{
            "campaign_id": metrics.campaign_id,
            "total_recipients": metrics.total_recipients,
            "sent": metrics.sent,
            "delivered": metrics.delivered,
            "opened": metrics.opened,
            "clicked": metrics.clicked,
            "submitted": metrics.submitted,
            "reported": metrics.reported,
            "open_rate": metrics.open_rate,
            "click_rate": metrics.click_rate,
            "submit_rate": metrics.submit_rate,
            "report_rate": metrics.report_rate,
        }])

        # Event timeline CSV
        timeline_csv = self._dict_to_csv(package.get("timeline", []))

        # Department breakdown CSV
        dept_csv = self._dict_to_csv(package.get("department_completion", []))

        # Training completions CSV
        training_csv = self._dict_to_csv([
            package.get("training_redirect_stats", {}),
        ])

        # Evidence metadata JSON with per-file hashes
        file_map = {
            "executive_summary.pdf": pdf_bytes,
            "detailed_metrics.csv": metrics_csv,
            "event_timeline.csv": timeline_csv,
            "department_breakdown.csv": dept_csv,
            "training_completions.csv": training_csv,
        }

        file_hashes = {}
        for name, content in file_map.items():
            data = content if isinstance(content, bytes) else content.encode("utf-8")
            file_hashes[name] = hashlib.sha256(data).hexdigest()

        evidence_metadata = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "campaign_id": campaign_id,
            "file_hashes": file_hashes,
            "integrity_hash": package.get("integrity_hash"),
        }
        evidence_json = json.dumps(evidence_metadata, indent=2, default=str)

        # Package integrity hash (hash of all file hashes)
        all_hashes = "\n".join(f"{h}  {n}" for n, h in sorted(file_hashes.items()))
        package_integrity = hashlib.sha256(all_hashes.encode()).hexdigest()

        # Build ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("executive_summary.pdf", pdf_bytes)
            zf.writestr("detailed_metrics.csv", metrics_csv)
            zf.writestr("event_timeline.csv", timeline_csv)
            zf.writestr("department_breakdown.csv", dept_csv)
            zf.writestr("training_completions.csv", training_csv)
            zf.writestr("evidence_metadata.json", evidence_json)
            zf.writestr("package_integrity.sha256", package_integrity + "\n")

        zip_buf.seek(0)
        return zip_buf.getvalue()

    @staticmethod
    def _dict_to_csv(data: list[dict]) -> str:
        """Convert a list of dicts to CSV string."""
        if not data:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
        writer.writeheader()
        for row in data:
            writer.writerow(row)
        return buf.getvalue()
