"""Metrics aggregation engine for TidePool campaign analytics.

All queries use SQLAlchemy async select with func.count, func.avg, etc.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, extract, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.tracking import CampaignRecipient, EventType, TrackingEvent
from app.reports.risk_scoring import (
    calculate_department_risk,
    calculate_org_risk,
    calculate_recipient_risk,
    risk_level,
)


# ---------------------------------------------------------------------------
# Dataclasses for structured return types
# ---------------------------------------------------------------------------

@dataclass
class CampaignMetrics:
    campaign_id: int
    total_recipients: int = 0
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    submitted: int = 0
    reported: int = 0

    open_rate: float = 0.0
    click_rate: float = 0.0
    submit_rate: float = 0.0
    report_rate: float = 0.0

    time_to_first_click_median: timedelta | None = None
    time_to_first_click_p90: timedelta | None = None

    sends_by_hour: dict[int, int] = field(default_factory=dict)
    events_timeline: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DepartmentMetrics:
    name: str
    headcount: int = 0
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    submitted: int = 0
    reported: int = 0
    risk_score: float = 0.0


@dataclass
class TrendMetrics:
    campaigns: list[dict[str, Any]] = field(default_factory=list)
    trend_direction: str = "stable"


@dataclass
class OrgRiskScore:
    org_risk_score: float = 0.0
    risk_level: str = "Low"
    department_rankings: list[dict[str, Any]] = field(default_factory=list)
    improvement_delta: float | None = None


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class MetricsAggregator:
    """Compute campaign, department, trend, and org-level metrics."""

    # -- Campaign-level -----------------------------------------------------

    async def get_campaign_metrics(
        self,
        campaign_id: int,
        db: AsyncSession,
    ) -> CampaignMetrics:
        """Aggregate all metrics for a single campaign."""
        metrics = CampaignMetrics(campaign_id=campaign_id)

        # Total recipients
        total_q = select(func.count()).select_from(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id,
        )
        metrics.total_recipients = (await db.execute(total_q)).scalar() or 0

        # Event counts by type
        counts_q = (
            select(TrackingEvent.event_type, func.count(TrackingEvent.id))
            .where(TrackingEvent.campaign_id == campaign_id)
            .group_by(TrackingEvent.event_type)
        )
        rows = (await db.execute(counts_q)).all()
        count_map: dict[str, int] = {}
        for event_type, cnt in rows:
            count_map[event_type.value if hasattr(event_type, "value") else event_type] = cnt

        metrics.sent = count_map.get("SENT", 0)
        metrics.delivered = count_map.get("DELIVERED", 0)
        metrics.opened = count_map.get("OPENED", 0)
        metrics.clicked = count_map.get("CLICKED", 0)
        metrics.submitted = count_map.get("SUBMITTED", 0)
        metrics.reported = count_map.get("REPORTED", 0)

        # Rates (as percentages, denominator = delivered or sent)
        denominator = metrics.delivered if metrics.delivered > 0 else metrics.sent
        if denominator > 0:
            metrics.open_rate = round(metrics.opened / denominator * 100, 2)
            metrics.click_rate = round(metrics.clicked / denominator * 100, 2)
            metrics.submit_rate = round(metrics.submitted / denominator * 100, 2)
            metrics.report_rate = round(metrics.reported / denominator * 100, 2)

        # Time-to-first-click analysis
        await self._compute_click_times(campaign_id, db, metrics)

        # Sends by hour
        sends_q = (
            select(
                extract("hour", TrackingEvent.timestamp).label("hr"),
                func.count(TrackingEvent.id),
            )
            .where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.event_type == EventType.SENT,
            )
            .group_by("hr")
        )
        for hr, cnt in (await db.execute(sends_q)).all():
            metrics.sends_by_hour[int(hr)] = cnt

        # Events timeline (bucketed by hour)
        timeline_q = (
            select(
                func.date_trunc("hour", TrackingEvent.timestamp).label("bucket"),
                TrackingEvent.event_type,
                func.count(TrackingEvent.id),
            )
            .where(TrackingEvent.campaign_id == campaign_id)
            .group_by("bucket", TrackingEvent.event_type)
            .order_by("bucket")
        )
        for bucket, etype, cnt in (await db.execute(timeline_q)).all():
            metrics.events_timeline.append({
                "timestamp": bucket.isoformat() if bucket else None,
                "event_type": etype.value if hasattr(etype, "value") else etype,
                "count": cnt,
            })

        return metrics

    async def _compute_click_times(
        self,
        campaign_id: int,
        db: AsyncSession,
        metrics: CampaignMetrics,
    ) -> None:
        """Calculate median and p90 time-to-first-click."""
        # Get earliest SENT per recipient
        sent_sub = (
            select(
                TrackingEvent.recipient_token,
                func.min(TrackingEvent.timestamp).label("sent_at"),
            )
            .where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.event_type == EventType.SENT,
            )
            .group_by(TrackingEvent.recipient_token)
            .subquery()
        )

        # Get earliest CLICKED per recipient
        click_sub = (
            select(
                TrackingEvent.recipient_token,
                func.min(TrackingEvent.timestamp).label("clicked_at"),
            )
            .where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.event_type == EventType.CLICKED,
            )
            .group_by(TrackingEvent.recipient_token)
            .subquery()
        )

        # Join to get deltas
        delta_q = select(
            click_sub.c.clicked_at - sent_sub.c.sent_at,
        ).select_from(
            click_sub.join(
                sent_sub,
                click_sub.c.recipient_token == sent_sub.c.recipient_token,
            )
        )

        deltas_raw = (await db.execute(delta_q)).scalars().all()
        deltas: list[float] = []
        for d in deltas_raw:
            if d is not None:
                if isinstance(d, timedelta):
                    deltas.append(d.total_seconds())
                else:
                    deltas.append(float(d))

        if deltas:
            deltas.sort()
            metrics.time_to_first_click_median = timedelta(
                seconds=statistics.median(deltas)
            )
            p90_idx = int(math.ceil(0.9 * len(deltas))) - 1
            metrics.time_to_first_click_p90 = timedelta(
                seconds=deltas[max(0, p90_idx)]
            )

    # -- Department-level ---------------------------------------------------

    async def get_department_metrics(
        self,
        campaign_id: int,
        db: AsyncSession,
    ) -> list[DepartmentMetrics]:
        """Per-department breakdown, sorted by risk_score descending."""
        # Subquery: recipients with their department
        recip_q = (
            select(
                Contact.department,
                CampaignRecipient.contact_id,
                CampaignRecipient.campaign_id,
                func.cast(CampaignRecipient.token, type_=func.text()).label("token_str"),
            )
            .join(Contact, Contact.id == CampaignRecipient.contact_id)
            .where(CampaignRecipient.campaign_id == campaign_id)
        )
        recip_rows = (await db.execute(recip_q)).all()

        # Build mapping: department -> list of tokens
        dept_tokens: dict[str, list[str]] = {}
        dept_headcount: dict[str, int] = {}
        for dept, contact_id, cid, token_str in recip_rows:
            dept_name = dept or "Unknown"
            dept_tokens.setdefault(dept_name, []).append(str(token_str))
            dept_headcount[dept_name] = dept_headcount.get(dept_name, 0) + 1

        # All events for this campaign
        events_q = (
            select(TrackingEvent.recipient_token, TrackingEvent.event_type)
            .where(TrackingEvent.campaign_id == campaign_id)
        )
        event_rows = (await db.execute(events_q)).all()

        # Build mapping: token -> set of event types
        token_events: dict[str, set[str]] = {}
        for token, etype in event_rows:
            t = str(token)
            token_events.setdefault(t, set()).add(
                etype.value if hasattr(etype, "value") else etype
            )

        results: list[DepartmentMetrics] = []
        for dept_name, tokens in dept_tokens.items():
            dm = DepartmentMetrics(
                name=dept_name,
                headcount=dept_headcount.get(dept_name, 0),
            )
            recipient_scores: list[float] = []
            for tok in tokens:
                evts = token_events.get(tok, set())
                if "SENT" in evts:
                    dm.sent += 1
                if "OPENED" in evts:
                    dm.opened += 1
                if "CLICKED" in evts:
                    dm.clicked += 1
                if "SUBMITTED" in evts:
                    dm.submitted += 1
                if "REPORTED" in evts:
                    dm.reported += 1
                recipient_scores.append(calculate_recipient_risk(list(evts)))

            participation = dm.sent / dm.headcount if dm.headcount > 0 else 0.0
            dm.risk_score = round(
                calculate_department_risk(recipient_scores, participation), 4
            )
            results.append(dm)

        results.sort(key=lambda d: d.risk_score, reverse=True)
        return results

    # -- Recipient timeline -------------------------------------------------

    async def get_recipient_timeline(
        self,
        campaign_id: int,
        recipient_token: str,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Return ordered event list for a specific recipient."""
        q = (
            select(TrackingEvent)
            .where(
                TrackingEvent.campaign_id == campaign_id,
                TrackingEvent.recipient_token == recipient_token,
            )
            .order_by(TrackingEvent.timestamp)
        )
        rows = (await db.execute(q)).scalars().all()
        return [
            {
                "id": ev.id,
                "event_type": ev.event_type.value if hasattr(ev.event_type, "value") else ev.event_type,
                "timestamp": ev.timestamp.isoformat(),
                "metadata": ev.metadata_,
            }
            for ev in rows
        ]

    # -- Trend analysis -----------------------------------------------------

    async def get_trend_metrics(
        self,
        campaign_ids: list[int],
        db: AsyncSession,
    ) -> TrendMetrics:
        """Trend analysis across multiple campaigns."""
        trend = TrendMetrics()

        for cid in campaign_ids:
            m = await self.get_campaign_metrics(cid, db)
            # Get campaign name and date
            camp_q = select(Campaign).where(Campaign.id == cid)
            camp = (await db.execute(camp_q)).scalar_one_or_none()

            trend.campaigns.append({
                "campaign_id": cid,
                "name": camp.name if camp else f"Campaign {cid}",
                "date": (camp.created_at.isoformat() if camp and camp.created_at else None),
                "open_rate": m.open_rate,
                "click_rate": m.click_rate,
                "submit_rate": m.submit_rate,
            })

        # Determine trend direction based on click rates
        if len(trend.campaigns) >= 2:
            rates = [c["click_rate"] for c in trend.campaigns]
            first_half = rates[: len(rates) // 2]
            second_half = rates[len(rates) // 2 :]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0

            delta = avg_second - avg_first
            if delta < -2.0:
                trend.trend_direction = "improving"
            elif delta > 2.0:
                trend.trend_direction = "declining"
            else:
                trend.trend_direction = "stable"

        return trend

    # -- Organisation risk score --------------------------------------------

    async def get_org_risk_score(
        self,
        campaign_ids: list[int],
        db: AsyncSession,
    ) -> OrgRiskScore:
        """Weighted organisation-wide risk score."""
        # Aggregate department metrics across all specified campaigns
        dept_aggregates: dict[str, dict[str, Any]] = {}

        for cid in campaign_ids:
            dept_list = await self.get_department_metrics(cid, db)
            for dm in dept_list:
                if dm.name not in dept_aggregates:
                    dept_aggregates[dm.name] = {
                        "scores": [],
                        "headcount": dm.headcount,
                    }
                dept_aggregates[dm.name]["scores"].append(dm.risk_score)
                # Use the max headcount seen
                if dm.headcount > dept_aggregates[dm.name]["headcount"]:
                    dept_aggregates[dm.name]["headcount"] = dm.headcount

        dept_tuples: list[tuple[str, float, int]] = []
        rankings: list[dict[str, Any]] = []
        for name, data in dept_aggregates.items():
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0.0
            hc = data["headcount"]
            dept_tuples.append((name, avg_score, hc))
            rankings.append({
                "name": name,
                "risk_score": round(avg_score, 4),
                "headcount": hc,
            })

        rankings.sort(key=lambda d: d["risk_score"], reverse=True)

        org_score = calculate_org_risk(dept_tuples)

        # Improvement delta: compare first campaign vs last campaign avg click rate
        improvement_delta = None
        if len(campaign_ids) >= 2:
            first_m = await self.get_campaign_metrics(campaign_ids[0], db)
            last_m = await self.get_campaign_metrics(campaign_ids[-1], db)
            improvement_delta = round(last_m.click_rate - first_m.click_rate, 2)

        return OrgRiskScore(
            org_risk_score=round(org_score, 4),
            risk_level=risk_level(org_score),
            department_rankings=rankings,
            improvement_delta=improvement_delta,
        )
