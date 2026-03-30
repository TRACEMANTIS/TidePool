"""Agent campaign orchestrator -- plans, executes, monitors, and analyzes campaigns.

The orchestrator is the central coordination layer between AI agents and
TidePool's campaign infrastructure. Every decision is recorded with reasoning
so the full chain of logic is auditable.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign, CampaignStatus as ModelStatus
from app.models.tracking import CampaignRecipient
from app.pretext.library import PretextLibrary
from app.reports.aggregator import MetricsAggregator

from app.agents.schemas import (
    AgentCampaignPlan,
    AgentCampaignResult,
    Finding,
    LandingPageStrategy,
    PlanComparison,
    PretextSelection,
    SendSchedule,
    SuccessCriteria,
)

logger = logging.getLogger(__name__)

_pretext_library = PretextLibrary()
_aggregator = MetricsAggregator()

# Mapping from objective keywords to pretext categories.
_OBJECTIVE_CATEGORY_MAP: dict[str, list[str]] = {
    "credential": ["IT"],
    "password": ["IT"],
    "phishing": ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
    "social engineering": ["EXECUTIVE", "HR"],
    "financial": ["FINANCE", "EXECUTIVE"],
    "wire": ["FINANCE", "EXECUTIVE"],
    "vendor": ["VENDOR"],
    "supply chain": ["VENDOR"],
    "hr": ["HR"],
    "benefits": ["HR"],
    "executive": ["EXECUTIVE"],
    "ceo": ["EXECUTIVE"],
    "general": ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
}


class AgentOrchestrator:
    """Plans, executes, monitors, and analyzes phishing simulation campaigns.

    Every public method returns structured data with reasoning fields,
    enabling full audit trails for agent-driven operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: aioredis.Redis | None = None,
        api_key: str | None = None,
    ) -> None:
        self.db = db
        self.redis = redis_client
        self.api_key = api_key

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    async def plan_campaign(
        self,
        objective: str,
        addressbook_id: int,
        constraints: dict[str, Any] | None = None,
    ) -> AgentCampaignPlan:
        """Analyze the address book and objective, then produce a structured plan.

        Steps:
        1. Query address book size and department distribution.
        2. Select pretexts matching the objective and audience.
        3. Determine optimal send window (business hours, avoids weekends).
        4. Calculate difficulty from org history if prior campaigns exist.
        5. Build plan with reasoning for each decision.
        """
        constraints = constraints or {}

        # -- 1. Analyze address book -------------------------------------------
        recipients = await self._get_addressbook_stats(addressbook_id)
        total_recipients = recipients["total"]
        departments = recipients["departments"]

        if total_recipients == 0:
            raise ValueError(f"Address book {addressbook_id} has no recipients.")

        # -- 2. Determine target categories from objective ---------------------
        target_categories = self._categories_from_objective(objective)

        # Allow constraint overrides.
        if "categories" in constraints:
            target_categories = constraints["categories"]

        # -- 3. Select pretexts ------------------------------------------------
        difficulty_target = constraints.get("difficulty", 2)
        pretext_selections = self._select_pretexts(target_categories, difficulty_target, objective)

        # -- 4. Determine send schedule ----------------------------------------
        send_schedule = self._compute_send_schedule(total_recipients, constraints)

        # -- 5. Difficulty from org history ------------------------------------
        org_difficulty = await self._org_difficulty_from_history()
        if org_difficulty is not None:
            difficulty_target = org_difficulty

        # Override with explicit constraint.
        difficulty_target = constraints.get("difficulty", difficulty_target)

        # -- 6. Department focus -----------------------------------------------
        department_focus = constraints.get("department_focus", None)

        # -- 7. Success criteria -----------------------------------------------
        # Higher difficulty => expect lower click rate (more sophisticated users).
        expected_click = max(0.05, 0.30 - (difficulty_target * 0.05))
        expected_report = min(0.40, 0.10 + (difficulty_target * 0.05))

        # -- 8. Risk assessment ------------------------------------------------
        risks: list[str] = []
        if total_recipients > settings.AGENT_MAX_RECIPIENTS_AUTO:
            risks.append(
                f"Recipient count ({total_recipients}) exceeds auto-execute threshold "
                f"({settings.AGENT_MAX_RECIPIENTS_AUTO}). Manual approval required."
            )
        if difficulty_target >= 4:
            risks.append(
                "High difficulty pretexts may generate support-desk tickets. "
                "Ensure the security team is briefed before launch."
            )
        if len(departments) <= 1:
            risks.append(
                "Single department detected. Results will not provide cross-department comparison."
            )

        campaign_name = f"Agent: {objective[:60]} - {datetime.now(timezone.utc):%Y-%m-%d}"

        return AgentCampaignPlan(
            campaign_name=campaign_name,
            objective=objective,
            target_audience=self._describe_audience(departments, total_recipients),
            pretext_strategy=pretext_selections,
            landing_page_strategy=LandingPageStrategy(
                template_id=constraints.get("landing_page_id"),
                customization_notes="Default credential-capture page unless overridden.",
            ),
            send_schedule=send_schedule,
            difficulty_target=difficulty_target,
            department_focus=department_focus,
            estimated_recipients=total_recipients,
            success_criteria=SuccessCriteria(
                target_click_rate=round(expected_click, 3),
                target_report_rate=round(expected_report, 3),
            ),
            risk_assessment=" | ".join(risks) if risks else "No significant risks identified.",
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute_plan(
        self,
        plan: AgentCampaignPlan,
        smtp_profile_id: int,
        auto_start: bool = False,
    ) -> int:
        """Create a campaign from an agent plan and optionally start it.

        Returns the campaign ID.
        """
        # Safety gate: refuse auto-start if recipients exceed threshold.
        if auto_start and plan.estimated_recipients > settings.AGENT_MAX_RECIPIENTS_AUTO:
            if not settings.AGENT_AUTO_EXECUTE:
                raise ValueError(
                    f"Auto-execute disabled or recipient count ({plan.estimated_recipients}) "
                    f"exceeds threshold ({settings.AGENT_MAX_RECIPIENTS_AUTO}). "
                    "Set auto_start=False and launch manually."
                )

        # Select the primary pretext for the email template.
        pretext = None
        if plan.pretext_strategy:
            primary = max(plan.pretext_strategy, key=lambda p: p.weight)
            pretext = _pretext_library.get_pretext(primary.pretext_id)

        # Create campaign record.
        campaign = Campaign(
            name=plan.campaign_name,
            description=f"Agent-planned campaign. Objective: {plan.objective}",
            status=ModelStatus.DRAFT,
            smtp_profile_id=smtp_profile_id,
            landing_page_id=plan.landing_page_strategy.template_id,
        )

        if pretext:
            campaign.email_template_id = None  # Will be created by orchestrator

        self.db.add(campaign)
        await self.db.flush()
        await self.db.refresh(campaign)

        # Configure send window.
        now = datetime.now(timezone.utc)
        start = now + timedelta(hours=plan.send_schedule.start_delay_hours)
        campaign.send_window_start = start
        campaign.send_window_end = start + timedelta(hours=plan.send_schedule.window_hours)

        if auto_start and settings.AGENT_AUTO_EXECUTE:
            campaign.status = ModelStatus.SCHEDULED

        await self.db.flush()
        return campaign.id

    # ------------------------------------------------------------------
    # Monitor
    # ------------------------------------------------------------------

    async def monitor_campaign(self, campaign_id: int) -> dict[str, Any]:
        """Check real-time stats and evaluate against success criteria.

        Returns a dict with current metrics, health assessment, and
        any recommended adjustments.
        """
        campaign = await self.db.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f"Campaign {campaign_id} not found.")

        stats: dict[str, Any] = {
            "campaign_id": campaign_id,
            "status": campaign.status.value,
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "reported": 0,
            "bounce_rate": 0.0,
            "send_rate_per_minute": 0.0,
        }

        # Pull live counts from Redis if available.
        if self.redis is not None:
            try:
                from app.tracking.realtime import RealtimeTracker
                tracker = RealtimeTracker(self.redis)
                counts = await tracker.get_live_counts(campaign_id)
                send_rate = await tracker.get_send_rate(campaign_id)

                stats["sent"] = counts.get("SENT", 0)
                stats["delivered"] = counts.get("DELIVERED", 0)
                stats["opened"] = counts.get("OPENED", 0)
                stats["clicked"] = counts.get("CLICKED", 0)
                stats["submitted"] = counts.get("SUBMITTED", 0)
                stats["reported"] = counts.get("REPORTED", 0)
                stats["send_rate_per_minute"] = send_rate

                # Bounce detection.
                failed = counts.get("FAILED", 0)
                total_sent = stats["sent"] + failed
                if total_sent > 0:
                    stats["bounce_rate"] = round(failed / total_sent, 4)
            except Exception:
                logger.warning("Redis unavailable during campaign monitoring for %s", campaign_id)

        # Health assessment.
        recommendations: list[str] = []
        if stats["bounce_rate"] > 0.10:
            recommendations.append(
                f"Bounce rate is {stats['bounce_rate']:.1%} (threshold: 10%). "
                "Consider pausing the campaign to investigate email list quality."
            )
        if stats["send_rate_per_minute"] > 100:
            recommendations.append(
                f"Send rate is {stats['send_rate_per_minute']:.0f}/min. "
                "High send rates may trigger spam filters. Consider throttling."
            )

        stats["recommendations"] = recommendations
        stats["health"] = "WARNING" if recommendations else "HEALTHY"

        return stats

    # ------------------------------------------------------------------
    # Analyze
    # ------------------------------------------------------------------

    async def analyze_results(self, campaign_id: int) -> AgentCampaignResult:
        """Pull full metrics after a campaign and generate analysis.

        Produces findings, recommendations, department analysis, and a
        recommended next campaign based on the results.
        """
        metrics = await _aggregator.get_campaign_metrics(campaign_id, self.db)
        dept_metrics = await _aggregator.get_department_metrics(campaign_id, self.db)

        metrics_summary = {
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
        }

        # Department analysis.
        department_analysis = [
            {
                "name": d.name,
                "headcount": d.headcount,
                "clicked": d.clicked,
                "reported": d.reported,
                "risk_score": d.risk_score,
            }
            for d in dept_metrics
        ]

        # Generate findings.
        findings = self._generate_findings(metrics_summary, department_analysis)

        # Plan comparison (uses default targets if no stored plan).
        comparison = PlanComparison(
            expected_click_rate=0.15,
            actual_click_rate=metrics.click_rate,
            delta=round(metrics.click_rate - 0.15, 4),
            assessment=self._assess_delta(metrics.click_rate, 0.15),
        )

        # Recommend next campaign.
        next_plan = self._recommend_next_campaign(metrics_summary, department_analysis)

        return AgentCampaignResult(
            campaign_id=campaign_id,
            metrics_summary=metrics_summary,
            department_analysis=department_analysis,
            findings=findings,
            comparison_to_plan=comparison,
            recommended_next_campaign=next_plan,
        )

    # ------------------------------------------------------------------
    # Adaptive difficulty
    # ------------------------------------------------------------------

    async def adaptive_difficulty(self, campaign_ids: list[int]) -> dict[str, Any]:
        """Analyze trends across campaigns and recommend difficulty progression."""
        click_rates: list[float] = []
        report_rates: list[float] = []

        for cid in campaign_ids:
            try:
                m = await _aggregator.get_campaign_metrics(cid, self.db)
                click_rates.append(m.click_rate)
                report_rates.append(m.report_rate)
            except Exception:
                continue

        if not click_rates:
            return {
                "recommendation": "Insufficient data. Run at least one campaign before adjusting difficulty.",
                "current_avg_click_rate": 0.0,
                "suggested_difficulty": 2,
            }

        avg_click = sum(click_rates) / len(click_rates)
        avg_report = sum(report_rates) / len(report_rates)

        # Trend: compare first half to second half.
        mid = len(click_rates) // 2
        if mid > 0:
            early_avg = sum(click_rates[:mid]) / mid
            late_avg = sum(click_rates[mid:]) / (len(click_rates) - mid)
            trend = "improving" if late_avg < early_avg else "declining"
        else:
            trend = "insufficient_data"

        # Suggest difficulty.
        if avg_click < 0.05:
            suggested = min(5, 4)
            reasoning = "Very low click rate indicates users are well-trained. Increase difficulty."
        elif avg_click < 0.10:
            suggested = 3
            reasoning = "Click rate is moderate-low. Increase difficulty to continue challenging users."
        elif avg_click < 0.20:
            suggested = 2
            reasoning = "Click rate is typical. Maintain current difficulty or increase slightly."
        else:
            suggested = max(1, 1)
            reasoning = "High click rate indicates users need more training at lower difficulty."

        return {
            "campaign_count": len(click_rates),
            "current_avg_click_rate": round(avg_click, 4),
            "current_avg_report_rate": round(avg_report, 4),
            "trend": trend,
            "suggested_difficulty": suggested,
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_addressbook_stats(self, addressbook_id: int) -> dict[str, Any]:
        """Query the address book for recipient count and department distribution."""
        from app.models.addressbook import AddressBook, Contact

        ab = await self.db.get(AddressBook, addressbook_id)
        if ab is None:
            raise ValueError(f"Address book {addressbook_id} not found.")

        # Count contacts.
        count_stmt = (
            select(func.count())
            .select_from(Contact)
            .where(Contact.address_book_id == addressbook_id)
        )
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Department distribution.
        dept_stmt = (
            select(Contact.department, func.count())
            .where(Contact.address_book_id == addressbook_id)
            .group_by(Contact.department)
        )
        dept_rows = (await self.db.execute(dept_stmt)).all()
        departments = {
            (row[0] or "Unknown"): row[1]
            for row in dept_rows
        }

        return {"total": total, "departments": departments}

    def _categories_from_objective(self, objective: str) -> list[str]:
        """Map an objective string to relevant pretext categories."""
        objective_lower = objective.lower()
        matched: set[str] = set()

        for keyword, categories in _OBJECTIVE_CATEGORY_MAP.items():
            if keyword in objective_lower:
                matched.update(categories)

        if not matched:
            # Default: cover all categories.
            matched = {"IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"}

        return sorted(matched)

    def _select_pretexts(
        self,
        categories: list[str],
        difficulty: int,
        objective: str,
    ) -> list[PretextSelection]:
        """Select and weight pretexts from the library."""
        selections: list[PretextSelection] = []

        for category in categories:
            # Try exact difficulty match first, then +/- 1.
            pretexts = _pretext_library.list_pretexts(category=category, difficulty=difficulty)
            if not pretexts:
                pretexts = _pretext_library.list_pretexts(category=category)
                # Filter to within +/- 1 difficulty.
                pretexts = [
                    p for p in pretexts
                    if abs(p["difficulty"] - difficulty) <= 1
                ]

            if not pretexts:
                continue

            # Pick the best match (first available for now).
            best = pretexts[0]
            weight = 1.0 / max(len(categories), 1)

            selections.append(PretextSelection(
                pretext_id=best["id"],
                weight=round(weight, 3),
                rationale=(
                    f"Selected '{best['name']}' (category={best['category']}, "
                    f"difficulty={best['difficulty']}) to address objective: {objective[:80]}. "
                    f"Template has {len(best.get('red_flags', []))} red flags for training."
                ),
            ))

        # Normalize weights.
        total_weight = sum(s.weight for s in selections)
        if total_weight > 0:
            for s in selections:
                s.weight = round(s.weight / total_weight, 3)

        return selections

    def _compute_send_schedule(
        self,
        recipient_count: int,
        constraints: dict[str, Any],
    ) -> SendSchedule:
        """Determine the optimal send schedule."""
        # Base window: ~10 emails per minute target.
        minutes_needed = math.ceil(recipient_count / 10)
        hours_needed = max(1, math.ceil(minutes_needed / 60))

        # Constrain to business hours by default.
        window_hours = constraints.get("window_hours", max(hours_needed, 4))
        start_delay = constraints.get("start_delay_hours", 0.0)

        return SendSchedule(
            start_delay_hours=start_delay,
            window_hours=min(window_hours, 720),
            preferred_send_times=constraints.get(
                "preferred_send_times",
                ["09:00-11:00", "13:00-15:00"],
            ),
        )

    async def _org_difficulty_from_history(self) -> int | None:
        """Determine difficulty from prior campaign results.

        If average click rate across recent campaigns is low, increase
        difficulty. Returns None if no history is available.
        """
        result = await self.db.execute(
            select(Campaign.id)
            .where(Campaign.status == ModelStatus.COMPLETED)
            .order_by(Campaign.id.desc())
            .limit(5)
        )
        recent_ids = [row[0] for row in result.all()]

        if not recent_ids:
            return None

        click_rates: list[float] = []
        for cid in recent_ids:
            try:
                m = await _aggregator.get_campaign_metrics(cid, self.db)
                click_rates.append(m.click_rate)
            except Exception:
                continue

        if not click_rates:
            return None

        avg = sum(click_rates) / len(click_rates)
        if avg < 0.05:
            return 4
        elif avg < 0.10:
            return 3
        elif avg < 0.20:
            return 2
        else:
            return 1

    def _describe_audience(self, departments: dict[str, int], total: int) -> str:
        """Build a human-readable audience description."""
        if not departments:
            return f"{total} recipients (no department data)"

        dept_list = sorted(departments.items(), key=lambda x: x[1], reverse=True)
        top = dept_list[:5]
        desc_parts = [f"{name}: {count}" for name, count in top]

        if len(dept_list) > 5:
            desc_parts.append(f"and {len(dept_list) - 5} more departments")

        return f"{total} recipients across {len(departments)} departments ({', '.join(desc_parts)})"

    def _generate_findings(
        self,
        metrics: dict[str, Any],
        departments: list[dict[str, Any]],
    ) -> list[Finding]:
        """Generate findings from campaign metrics."""
        findings: list[Finding] = []

        click_rate = metrics.get("click_rate", 0)
        report_rate = metrics.get("report_rate", 0)
        submit_rate = metrics.get("submit_rate", 0)

        # Click rate analysis.
        if click_rate > 0.25:
            findings.append(Finding(
                finding=f"Click rate of {click_rate:.1%} significantly exceeds industry average (15-20%).",
                severity="HIGH",
                recommendation="Implement mandatory security awareness training with focus on link inspection.",
            ))
        elif click_rate > 0.15:
            findings.append(Finding(
                finding=f"Click rate of {click_rate:.1%} is at or slightly above industry average.",
                severity="MEDIUM",
                recommendation="Continue regular phishing simulations with gradually increasing difficulty.",
            ))
        else:
            findings.append(Finding(
                finding=f"Click rate of {click_rate:.1%} is below industry average.",
                severity="INFO",
                recommendation="Organization shows good phishing resistance. Increase difficulty in next campaign.",
            ))

        # Report rate analysis.
        if report_rate < 0.10:
            findings.append(Finding(
                finding=f"Report rate of {report_rate:.1%} is very low.",
                severity="MEDIUM",
                recommendation="Reinforce reporting procedures. Users may not know how to report suspicious emails.",
            ))
        elif report_rate > 0.30:
            findings.append(Finding(
                finding=f"Report rate of {report_rate:.1%} indicates strong security culture.",
                severity="INFO",
                recommendation="Recognize and reward reporting behavior to sustain this trend.",
            ))

        # Submission rate analysis.
        if submit_rate > 0.10:
            findings.append(Finding(
                finding=f"Credential submission rate of {submit_rate:.1%} indicates users are entering data on phishing pages.",
                severity="HIGH",
                recommendation="Targeted training on credential entry awareness. Consider MFA enforcement.",
            ))

        # Department-level findings.
        high_risk_depts = [d for d in departments if d.get("risk_score", 0) > 70]
        if high_risk_depts:
            dept_names = ", ".join(d["name"] for d in high_risk_depts[:3])
            findings.append(Finding(
                finding=f"High-risk departments identified: {dept_names}.",
                severity="HIGH",
                recommendation="Schedule targeted phishing simulations and additional training for these departments.",
            ))

        return findings

    def _assess_delta(self, actual: float, expected: float) -> str:
        """Generate a human-readable assessment of plan vs. actual."""
        delta = actual - expected
        if abs(delta) < 0.02:
            return "Results closely match predictions. The campaign performed as expected."
        elif delta > 0:
            return (
                f"Click rate exceeded prediction by {delta:.1%}. "
                "Users were more susceptible than anticipated. Consider lowering "
                "difficulty or adding training before the next campaign."
            )
        else:
            return (
                f"Click rate was {abs(delta):.1%} below prediction. "
                "Users performed better than expected. Consider increasing "
                "difficulty in the next campaign."
            )

    def _recommend_next_campaign(
        self,
        metrics: dict[str, Any],
        departments: list[dict[str, Any]],
    ) -> AgentCampaignPlan:
        """Recommend a follow-up campaign based on results."""
        click_rate = metrics.get("click_rate", 0)

        # Determine difficulty adjustment.
        if click_rate < 0.05:
            next_difficulty = 4
            objective = "Advanced phishing simulation targeting well-trained users"
        elif click_rate < 0.10:
            next_difficulty = 3
            objective = "Intermediate phishing simulation to continue building resilience"
        elif click_rate < 0.20:
            next_difficulty = 2
            objective = "Standard phishing simulation to maintain awareness"
        else:
            next_difficulty = 1
            objective = "Foundational phishing simulation with clear red flags for training"

        # Focus on high-risk departments if identified.
        high_risk = [d["name"] for d in departments if d.get("risk_score", 0) > 70]
        department_focus = high_risk[:5] if high_risk else None

        if department_focus:
            objective += f" (focused on: {', '.join(department_focus)})"

        # Pick a different category than what was likely used.
        categories = ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"]
        pretexts = []
        for cat in categories:
            available = _pretext_library.list_pretexts(category=cat, difficulty=next_difficulty)
            if available:
                pretexts.append(PretextSelection(
                    pretext_id=available[0]["id"],
                    weight=round(1.0 / len(categories), 3),
                    rationale=f"Rotating to {cat} category for coverage diversity.",
                ))

        return AgentCampaignPlan(
            campaign_name=f"Follow-up: {objective[:50]}",
            objective=objective,
            target_audience="Based on previous campaign results",
            pretext_strategy=pretexts,
            landing_page_strategy=LandingPageStrategy(),
            send_schedule=SendSchedule(),
            difficulty_target=next_difficulty,
            department_focus=department_focus,
            estimated_recipients=metrics.get("total_recipients", 0),
            success_criteria=SuccessCriteria(
                target_click_rate=max(0.03, click_rate - 0.05),
                target_report_rate=min(0.50, metrics.get("report_rate", 0.10) + 0.05),
            ),
            risk_assessment="Follow-up campaign. Review previous findings before launch.",
        )
