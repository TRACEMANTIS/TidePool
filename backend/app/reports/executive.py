"""Executive report generator for TidePool campaigns."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.email_template import EmailTemplate
from app.reports.aggregator import MetricsAggregator
from app.reports.risk_scoring import calculate_org_risk, risk_level


class ExecutiveReportGenerator:
    """Generate executive-level summary reports."""

    def __init__(self) -> None:
        self._aggregator = MetricsAggregator()

    async def generate(self, campaign_id: int, db: AsyncSession) -> dict[str, Any]:
        """Produce an executive report for a single campaign."""
        metrics = await self._aggregator.get_campaign_metrics(campaign_id, db)
        departments = await self._aggregator.get_department_metrics(campaign_id, db)

        # Campaign metadata
        camp_q = select(Campaign).where(Campaign.id == campaign_id)
        campaign = (await db.execute(camp_q)).scalar_one_or_none()

        template_name = None
        if campaign and campaign.email_template_id:
            tpl_q = select(EmailTemplate).where(
                EmailTemplate.id == campaign.email_template_id
            )
            tpl = (await db.execute(tpl_q)).scalar_one_or_none()
            template_name = tpl.name if tpl else None

        # Risk scoring
        dept_tuples = [(d.name, d.risk_score, d.headcount) for d in departments]
        org_score = calculate_org_risk(dept_tuples)
        level = risk_level(org_score)

        # Top 5 riskiest departments
        top_depts = [
            {
                "name": d.name,
                "headcount": d.headcount,
                "sent": d.sent,
                "clicked": d.clicked,
                "submitted": d.submitted,
                "risk_score": d.risk_score,
            }
            for d in departments[:5]
        ]

        # Auto-generated findings
        findings = self._generate_findings(metrics, departments)

        # Auto-generated recommendations
        recommendations = self._generate_recommendations(level, metrics, departments)

        # Check for previous campaign comparison
        comparison = None
        if campaign:
            comparison = await self._compare_previous(campaign, db)

        return {
            "campaign_summary": {
                "name": campaign.name if campaign else f"Campaign {campaign_id}",
                "start_date": (
                    campaign.send_window_start.isoformat()
                    if campaign and campaign.send_window_start
                    else None
                ),
                "end_date": (
                    campaign.send_window_end.isoformat()
                    if campaign and campaign.send_window_end
                    else None
                ),
                "template_used": template_name,
                "total_recipients": metrics.total_recipients,
            },
            "overall_metrics": {
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
            },
            "department_breakdown": top_depts,
            "risk_assessment": {
                "org_risk_score": round(org_score, 4),
                "risk_level": level,
            },
            "key_findings": findings,
            "recommendations": recommendations,
            "previous_campaign_comparison": comparison,
        }

    async def generate_multi_campaign(
        self,
        campaign_ids: list[int],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Produce a trend report across multiple campaigns."""
        trend = await self._aggregator.get_trend_metrics(campaign_ids, db)
        org_risk = await self._aggregator.get_org_risk_score(campaign_ids, db)

        # Regression analysis
        analysis = []
        campaigns_data = trend.campaigns
        for i in range(1, len(campaigns_data)):
            prev = campaigns_data[i - 1]
            curr = campaigns_data[i]
            click_delta = curr["click_rate"] - prev["click_rate"]
            submit_delta = curr["submit_rate"] - prev["submit_rate"]
            direction = "improved" if click_delta < 0 else ("regressed" if click_delta > 0 else "unchanged")
            analysis.append({
                "from_campaign": prev["name"],
                "to_campaign": curr["name"],
                "click_rate_delta": round(click_delta, 2),
                "submit_rate_delta": round(submit_delta, 2),
                "direction": direction,
            })

        return {
            "trend": {
                "campaigns": campaigns_data,
                "trend_direction": trend.trend_direction,
            },
            "org_risk": {
                "score": org_risk.org_risk_score,
                "level": org_risk.risk_level,
                "department_rankings": org_risk.department_rankings,
                "improvement_delta": org_risk.improvement_delta,
            },
            "regression_analysis": analysis,
        }

    # -- Private helpers ----------------------------------------------------

    def _generate_findings(self, metrics, departments) -> list[str]:
        """Auto-generate key findings based on metric thresholds."""
        findings: list[str] = []

        if metrics.click_rate > 30:
            findings.append(
                f"Click rate of {metrics.click_rate}% exceeds the 30% threshold, "
                f"indicating significant susceptibility to phishing."
            )
        elif metrics.click_rate > 15:
            findings.append(
                f"Click rate of {metrics.click_rate}% is moderate; targeted training "
                f"is recommended for high-risk departments."
            )
        else:
            findings.append(
                f"Click rate of {metrics.click_rate}% is within acceptable bounds."
            )

        if metrics.submit_rate > 10:
            findings.append(
                f"Credential submission rate of {metrics.submit_rate}% indicates "
                f"that users are entering data on phishing pages."
            )

        if metrics.report_rate < 5:
            findings.append(
                "Phish reporting rate is below 5%, suggesting employees lack "
                "awareness of the reporting mechanism."
            )
        elif metrics.report_rate > 20:
            findings.append(
                f"Strong phish reporting rate of {metrics.report_rate}% indicates "
                f"good security awareness culture."
            )

        if departments:
            worst = departments[0]
            if worst.risk_score > 0.5:
                findings.append(
                    f"Department '{worst.name}' has the highest risk score "
                    f"({worst.risk_score:.2f}) and should be prioritised for training."
                )

        if metrics.time_to_first_click_median is not None:
            minutes = metrics.time_to_first_click_median.total_seconds() / 60
            findings.append(
                f"Median time to first click was {minutes:.1f} minutes, "
                f"indicating {'rapid' if minutes < 5 else 'moderate'} response to phishing emails."
            )

        return findings

    def _generate_recommendations(self, level, metrics, departments) -> list[str]:
        """Auto-generate recommendations based on risk level and patterns."""
        recs: list[str] = []

        if level in ("Critical", "Severe"):
            recs.append(
                "Conduct mandatory organisation-wide phishing awareness training."
            )
            recs.append(
                "Implement additional email filtering controls to reduce phishing "
                "delivery rates."
            )
        elif level in ("High", "Moderate"):
            recs.append(
                "Schedule targeted training sessions for departments with elevated risk scores."
            )
        else:
            recs.append(
                "Continue the current security awareness programme and run periodic "
                "simulations to maintain vigilance."
            )

        if metrics.submit_rate > 5:
            recs.append(
                "Deploy browser-based credential entry warnings to alert users "
                "when submitting data to unrecognised domains."
            )

        if metrics.report_rate < 10:
            recs.append(
                "Promote the phishing report button and ensure employees know "
                "how to report suspicious emails."
            )

        high_risk_depts = [d for d in departments if d.risk_score > 0.4]
        if high_risk_depts:
            names = ", ".join(d.name for d in high_risk_depts[:3])
            recs.append(
                f"Prioritise training for: {names}."
            )

        return recs

    async def _compare_previous(
        self,
        campaign: Campaign,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Compare with the most recent previous campaign by the same creator."""
        prev_q = (
            select(Campaign)
            .where(
                Campaign.created_by == campaign.created_by,
                Campaign.id < campaign.id,
            )
            .order_by(Campaign.id.desc())
            .limit(1)
        )
        prev = (await db.execute(prev_q)).scalar_one_or_none()
        if prev is None:
            return None

        prev_metrics = await self._aggregator.get_campaign_metrics(prev.id, db)
        curr_metrics = await self._aggregator.get_campaign_metrics(campaign.id, db)

        return {
            "previous_campaign": {
                "id": prev.id,
                "name": prev.name,
            },
            "click_rate_delta": round(curr_metrics.click_rate - prev_metrics.click_rate, 2),
            "submit_rate_delta": round(curr_metrics.submit_rate - prev_metrics.submit_rate, 2),
            "report_rate_delta": round(curr_metrics.report_rate - prev_metrics.report_rate, 2),
        }
