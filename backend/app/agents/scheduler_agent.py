"""Autonomous scheduling agent for annual phishing simulation programs.

Plans a full year of campaigns with progressive difficulty, category
rotation, blackout avoidance, and adaptive adjustment based on results.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.pretext.library import PretextLibrary

from app.agents.schemas import (
    AgentCampaignPlan,
    AgentCampaignResult,
    LandingPageStrategy,
    PretextSelection,
    SendSchedule,
    SuccessCriteria,
)

logger = logging.getLogger(__name__)

_pretext_library = PretextLibrary()

# Category rotation order -- ensures every vector is covered.
_CATEGORY_ROTATION = ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"]

# Default blackout periods (month, day) -- US federal holidays as baseline.
_DEFAULT_BLACKOUTS = [
    (1, 1),    # New Year's Day
    (7, 4),    # Independence Day
    (12, 25),  # Christmas Day
    (12, 31),  # New Year's Eve
]


class SchedulerAgent:
    """Plans and adjusts annual phishing simulation programs.

    Produces a list of AgentCampaignPlan objects spread across the year
    with progressive difficulty, category rotation, and department
    coverage guarantees.
    """

    async def plan_annual_program(
        self,
        addressbook_id: int,
        campaigns_per_year: int = 12,
        config: dict[str, Any] | None = None,
    ) -> list[AgentCampaignPlan]:
        """Plan a full year of phishing simulation campaigns.

        Parameters
        ----------
        addressbook_id:
            Target address book for all campaigns.
        campaigns_per_year:
            Number of campaigns to schedule (1-52).
        config:
            Optional overrides:
            - blackout_dates: list of ISO date strings to avoid.
            - start_date: ISO date string for program start.
            - departments: list of department names to ensure coverage.
            - min_department_tests: minimum times each dept is tested.
            - base_difficulty: starting difficulty (default 1).
            - max_difficulty: ceiling (default 4).

        Returns
        -------
        list[AgentCampaignPlan]
            Ordered list of plans with scheduled_date set.
        """
        config = config or {}

        # Parse configuration.
        start_date = self._parse_date(config.get("start_date")) or date.today()
        blackout_dates = self._parse_blackout_dates(config.get("blackout_dates", []))
        departments = config.get("departments", [])
        min_dept_tests = config.get("min_department_tests", 2)
        base_difficulty = config.get("base_difficulty", 1)
        max_difficulty = config.get("max_difficulty", 4)

        # Calculate campaign dates spread across the year.
        campaign_dates = self._compute_campaign_dates(
            start_date, campaigns_per_year, blackout_dates,
        )

        # Build difficulty progression.
        difficulties = self._difficulty_progression(
            campaigns_per_year, base_difficulty, max_difficulty,
        )

        # Build category rotation.
        categories = self._category_rotation(campaigns_per_year)

        # Build department focus schedule.
        dept_focus_schedule = self._department_focus_schedule(
            departments, campaigns_per_year, min_dept_tests,
        )

        # Assemble plans.
        plans: list[AgentCampaignPlan] = []
        for i in range(campaigns_per_year):
            campaign_date = campaign_dates[i] if i < len(campaign_dates) else None
            difficulty = difficulties[i]
            category = categories[i]
            dept_focus = dept_focus_schedule.get(i)

            # Select pretexts for this campaign.
            pretexts = self._select_campaign_pretexts(category, difficulty)

            # Build objective description.
            objective = self._build_objective(i + 1, campaigns_per_year, category, difficulty, dept_focus)

            # Difficulty-adjusted success criteria.
            expected_click = max(0.03, 0.30 - (difficulty * 0.06))
            expected_report = min(0.45, 0.10 + (difficulty * 0.06))

            plan = AgentCampaignPlan(
                campaign_name=f"Program Campaign {i + 1}/{campaigns_per_year} - {category}",
                objective=objective,
                target_audience=f"All employees" + (f" (focus: {', '.join(dept_focus)})" if dept_focus else ""),
                pretext_strategy=pretexts,
                landing_page_strategy=LandingPageStrategy(
                    customization_notes=f"Standard credential capture for {category} scenario.",
                ),
                send_schedule=SendSchedule(
                    start_delay_hours=0.0,
                    window_hours=8,
                    preferred_send_times=["09:00-11:30", "13:00-15:30"],
                ),
                difficulty_target=difficulty,
                department_focus=dept_focus,
                estimated_recipients=0,  # Will be populated during execution.
                success_criteria=SuccessCriteria(
                    target_click_rate=round(expected_click, 3),
                    target_report_rate=round(expected_report, 3),
                ),
                risk_assessment=self._risk_for_campaign(i, campaigns_per_year, difficulty),
                scheduled_date=(
                    datetime(campaign_date.year, campaign_date.month, campaign_date.day, 9, 0, tzinfo=timezone.utc)
                    if campaign_date else None
                ),
            )
            plans.append(plan)

        return plans

    async def adjust_program(
        self,
        program: list[AgentCampaignPlan],
        completed_results: list[AgentCampaignResult],
    ) -> list[AgentCampaignPlan]:
        """Adjust remaining program based on completed campaign results.

        Logic:
        - If org is performing well (low click rate): increase difficulty.
        - If specific departments are struggling: add targeted campaigns.
        - If a category had high click rates: add more of that category.
        """
        if not completed_results:
            return program

        # Analyze completed results.
        avg_click_rate = sum(
            r.metrics_summary.get("click_rate", 0) for r in completed_results
        ) / len(completed_results)

        # Identify struggling departments.
        dept_risk: dict[str, list[float]] = {}
        for result in completed_results:
            for dept in result.department_analysis:
                name = dept.get("name", "Unknown")
                risk = dept.get("risk_score", 0)
                dept_risk.setdefault(name, []).append(risk)

        struggling_depts = [
            name for name, scores in dept_risk.items()
            if sum(scores) / len(scores) > 60
        ]

        # Identify high-click categories.
        # (We infer category from the plan name if available.)
        category_clicks: dict[str, list[float]] = {}
        for result in completed_results:
            # Try to extract category from campaign name.
            for cat in _CATEGORY_ROTATION:
                # Simple heuristic: look for category in the summary or name.
                if cat.lower() in str(result.metrics_summary).lower():
                    cr = result.metrics_summary.get("click_rate", 0)
                    category_clicks.setdefault(cat, []).append(cr)

        high_click_categories = [
            cat for cat, rates in category_clicks.items()
            if sum(rates) / len(rates) > 0.20
        ]

        # Filter to only unexecuted campaigns (those without results).
        completed_ids = {r.campaign_id for r in completed_results}
        # Since plans don't have IDs, we adjust all remaining plans.
        # The caller should only pass plans that haven't been executed yet.
        adjusted: list[AgentCampaignPlan] = []

        for plan in program:
            adjusted_plan = plan.model_copy()

            # Difficulty adjustment.
            if avg_click_rate < 0.08:
                adjusted_plan.difficulty_target = min(5, plan.difficulty_target + 1)
            elif avg_click_rate > 0.25:
                adjusted_plan.difficulty_target = max(1, plan.difficulty_target - 1)

            # Department focus injection.
            if struggling_depts and plan.department_focus is None:
                # Every third remaining campaign gets department focus.
                idx = program.index(plan)
                if idx % 3 == 0:
                    adjusted_plan.department_focus = struggling_depts[:3]
                    adjusted_plan.objective = (
                        f"{plan.objective} [ADJUSTED: targeting high-risk departments: "
                        f"{', '.join(struggling_depts[:3])}]"
                    )

            # Category reinforcement.
            if high_click_categories:
                # Check if plan's category should be swapped.
                for cat in _CATEGORY_ROTATION:
                    if cat in plan.campaign_name and cat not in high_click_categories:
                        # Swap to a high-click category for reinforcement.
                        if high_click_categories:
                            replacement = high_click_categories[0]
                            adjusted_plan.campaign_name = plan.campaign_name.replace(cat, replacement)
                            adjusted_plan.pretext_strategy = self._select_campaign_pretexts(
                                replacement, adjusted_plan.difficulty_target,
                            )
                            adjusted_plan.risk_assessment = (
                                f"{plan.risk_assessment} | ADJUSTED: Swapped from {cat} to "
                                f"{replacement} due to high click rates in that category."
                            )
                            break

            # Update success criteria based on trend.
            adjusted_plan.success_criteria = SuccessCriteria(
                target_click_rate=max(0.03, avg_click_rate - 0.03),
                target_report_rate=min(0.50, adjusted_plan.success_criteria.target_report_rate + 0.02),
            )

            adjusted.append(adjusted_plan)

        return adjusted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_campaign_dates(
        self,
        start: date,
        count: int,
        blackouts: set[date],
    ) -> list[date]:
        """Spread campaigns evenly across 365 days, avoiding blackouts and weekends."""
        interval_days = max(1, 365 // count)
        dates: list[date] = []
        current = start

        for _ in range(count):
            # Find the next valid date.
            candidate = current
            attempts = 0
            while attempts < 14:
                if candidate not in blackouts and candidate.weekday() < 5:
                    break
                candidate += timedelta(days=1)
                attempts += 1

            dates.append(candidate)
            current = candidate + timedelta(days=interval_days)

        return dates

    def _difficulty_progression(
        self,
        count: int,
        base: int,
        ceiling: int,
    ) -> list[int]:
        """Build a progressive difficulty curve."""
        if count <= 1:
            return [base]

        difficulties: list[int] = []
        for i in range(count):
            # Linear progression from base to ceiling.
            progress = i / (count - 1)
            difficulty = base + round(progress * (ceiling - base))
            difficulties.append(max(1, min(5, difficulty)))

        return difficulties

    def _category_rotation(self, count: int) -> list[str]:
        """Rotate through categories to ensure coverage."""
        categories: list[str] = []
        for i in range(count):
            categories.append(_CATEGORY_ROTATION[i % len(_CATEGORY_ROTATION)])
        return categories

    def _department_focus_schedule(
        self,
        departments: list[str],
        campaign_count: int,
        min_tests: int,
    ) -> dict[int, list[str] | None]:
        """Assign department focus to specific campaign indices.

        Returns a mapping of campaign_index -> department focus list.
        None means target all departments.
        """
        schedule: dict[int, list[str] | None] = {}

        if not departments:
            return schedule

        # Ensure each department is tested at least min_tests times.
        total_dept_campaigns = len(departments) * min_tests
        dept_campaign_indices: list[int] = []

        if total_dept_campaigns <= campaign_count:
            # Spread department-focused campaigns evenly.
            interval = max(1, campaign_count // total_dept_campaigns)
            idx = 0
            for _ in range(min_tests):
                for dept in departments:
                    if idx < campaign_count:
                        schedule[idx] = [dept]
                        dept_campaign_indices.append(idx)
                    idx += interval
        else:
            # More dept campaigns needed than total -- group departments.
            group_size = math.ceil(len(departments) / max(1, campaign_count // min_tests))
            idx = 0
            for i in range(0, len(departments), group_size):
                group = departments[i:i + group_size]
                for _ in range(min_tests):
                    if idx < campaign_count:
                        schedule[idx] = group
                        idx += 1

        return schedule

    def _select_campaign_pretexts(
        self,
        category: str,
        difficulty: int,
    ) -> list[PretextSelection]:
        """Select pretexts for a campaign from the library."""
        pretexts = _pretext_library.list_pretexts(category=category, difficulty=difficulty)
        if not pretexts:
            pretexts = _pretext_library.list_pretexts(category=category)
        if not pretexts:
            pretexts = _pretext_library.list_pretexts(difficulty=difficulty)
        if not pretexts:
            return []

        # Take up to 2 pretexts for variety.
        selected = pretexts[:2]
        weight = round(1.0 / len(selected), 3)

        return [
            PretextSelection(
                pretext_id=p["id"],
                weight=weight,
                rationale=(
                    f"Selected for {category} category at difficulty {difficulty}. "
                    f"Template: '{p['name']}' with {len(p.get('red_flags', []))} red flags."
                ),
            )
            for p in selected
        ]

    def _build_objective(
        self,
        index: int,
        total: int,
        category: str,
        difficulty: int,
        dept_focus: list[str] | None,
    ) -> str:
        """Build a descriptive objective for a program campaign."""
        phase = "early" if index <= total // 3 else ("mid" if index <= 2 * total // 3 else "late")
        parts = [
            f"Campaign {index}/{total} ({phase}-program).",
            f"Category: {category}, Difficulty: {difficulty}/5.",
        ]
        if dept_focus:
            parts.append(f"Department focus: {', '.join(dept_focus)}.")
        else:
            parts.append("Targeting all departments.")

        return " ".join(parts)

    def _risk_for_campaign(self, index: int, total: int, difficulty: int) -> str:
        """Generate risk assessment based on position in program."""
        risks: list[str] = []

        if index == 0:
            risks.append("First campaign in program -- establishes baseline. Keep difficulty low.")
        if difficulty >= 4:
            risks.append("High difficulty may generate support tickets. Brief the help desk.")
        if index >= total - 2:
            risks.append("Late-program campaign -- compare against baseline to measure improvement.")

        return " | ".join(risks) if risks else "Standard risk profile for this program phase."

    def _parse_date(self, value: Any) -> date | None:
        """Parse a date from string or return None."""
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _parse_blackout_dates(self, dates: list[str]) -> set[date]:
        """Parse blackout date strings and add defaults."""
        blackouts: set[date] = set()

        # Add user-specified dates.
        for d in dates:
            parsed = self._parse_date(d)
            if parsed:
                blackouts.add(parsed)

        # Add default holidays for the next year.
        current_year = date.today().year
        for month, day in _DEFAULT_BLACKOUTS:
            try:
                blackouts.add(date(current_year, month, day))
                blackouts.add(date(current_year + 1, month, day))
            except ValueError:
                continue

        return blackouts
