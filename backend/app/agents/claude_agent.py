"""Claude Code agent integration for TidePool.

Wraps the orchestrator with a conversational interface that parses
natural language instructions, determines the appropriate action,
and returns a fully auditable session.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import AgentOrchestrator
from app.agents.pretext_engine import PretextEngine
from app.agents.scheduler_agent import SchedulerAgent
from app.agents.schemas import (
    AgentActionType,
    AgentCampaignPlan,
    AgentSession,
    AgentSessionStatus,
    PretextGenerationRequest,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent profiles
# ---------------------------------------------------------------------------

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "campaign_planner": {
        "name": "Campaign Planner",
        "description": "Plans and configures phishing simulation campaigns based on objectives and constraints.",
        "capabilities": [AgentActionType.PLAN, AgentActionType.RECOMMEND],
        "default_constraints": {
            "difficulty": 2,
            "window_hours": 8,
            "preferred_send_times": ["09:00-11:00", "13:00-15:00"],
        },
    },
    "campaign_monitor": {
        "name": "Campaign Monitor",
        "description": "Watches running campaigns in real-time and alerts on anomalies such as high bounce rates or unusual click patterns.",
        "capabilities": [AgentActionType.MONITOR, AgentActionType.ADJUST],
        "default_constraints": {
            "bounce_threshold": 0.10,
            "send_rate_threshold": 100,
        },
    },
    "analyst": {
        "name": "Campaign Analyst",
        "description": "Analyzes completed campaign results, generates findings and recommendations, and compares actual outcomes to planned targets.",
        "capabilities": [AgentActionType.ANALYZE, AgentActionType.RECOMMEND],
        "default_constraints": {},
    },
    "program_manager": {
        "name": "Program Manager",
        "description": "Manages annual phishing simulation programs including planning, scheduling, difficulty progression, and adaptive adjustments.",
        "capabilities": [
            AgentActionType.PLAN,
            AgentActionType.ANALYZE,
            AgentActionType.ADJUST,
            AgentActionType.RECOMMEND,
        ],
        "default_constraints": {
            "campaigns_per_year": 12,
            "base_difficulty": 1,
            "max_difficulty": 4,
        },
    },
}


# ---------------------------------------------------------------------------
# Instruction parsing patterns
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, AgentActionType, str]] = [
    (r"(?i)\b(plan|create|design|build)\b.*\b(campaign|simulation|phish)", AgentActionType.PLAN, "plan_campaign"),
    (r"(?i)\b(execute|launch|start|run|deploy)\b.*\b(campaign|plan)", AgentActionType.EXECUTE, "execute_plan"),
    (r"(?i)\b(monitor|watch|check|track)\b.*\b(campaign|status|progress)", AgentActionType.MONITOR, "monitor_campaign"),
    (r"(?i)\b(analyze|review|assess|evaluate)\b.*\b(campaign|result|metric)", AgentActionType.ANALYZE, "analyze_results"),
    (r"(?i)\b(program|annual|yearly|schedule)\b.*\b(plan|create|build|design)", AgentActionType.PLAN, "plan_program"),
    (r"(?i)\b(adjust|update|modify|adapt)\b.*\b(program|schedule|plan)", AgentActionType.ADJUST, "adjust_program"),
    (r"(?i)\b(generate|create|write)\b.*\b(pretext|email|template)", AgentActionType.PLAN, "generate_pretext"),
    (r"(?i)\b(recommend|suggest|advise)\b", AgentActionType.RECOMMEND, "recommend"),
]


class TidePoolAgent:
    """Conversational agent interface for TidePool campaign management.

    Parses natural language instructions, routes to the appropriate
    orchestrator method, and records all actions in an auditable session.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis_client: aioredis.Redis | None = None,
        api_key: str | None = None,
        profile: str = "campaign_planner",
    ) -> None:
        self.db = db
        self.redis = redis_client
        self.api_key = api_key
        self.profile_name = profile
        self.profile = AGENT_PROFILES.get(profile, AGENT_PROFILES["campaign_planner"])

        self.orchestrator = AgentOrchestrator(db, redis_client, api_key)
        self.pretext_engine = PretextEngine(api_key)
        self.scheduler = SchedulerAgent()

    async def run(
        self,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> AgentSession:
        """Parse a natural language instruction and execute the appropriate action.

        Parameters
        ----------
        instruction:
            Natural language description of what the agent should do.
        context:
            Optional dict with additional parameters:
            - addressbook_id: int
            - campaign_id: int
            - smtp_profile_id: int
            - constraints: dict
            - plan: AgentCampaignPlan (serialized)

        Returns
        -------
        AgentSession
            Complete session with all actions and reasoning for audit.
        """
        context = context or {}
        session = AgentSession(agent_type=self.profile_name)

        # Record the initial instruction.
        session.record_action(
            action_type=AgentActionType.PLAN,
            description=f"Received instruction: {instruction}",
            input_data={"instruction": instruction, "context": context},
            reasoning="Parsing instruction to determine appropriate action.",
        )

        try:
            # Determine action from instruction.
            action_type, method_name = self._parse_instruction(instruction)

            # Validate capability.
            if action_type not in self.profile["capabilities"]:
                session.record_action(
                    action_type=action_type,
                    description=f"Action {action_type.value} not permitted for profile {self.profile_name}.",
                    reasoning=(
                        f"The '{self.profile_name}' profile does not include "
                        f"{action_type.value} in its capabilities: "
                        f"{[c.value for c in self.profile['capabilities']]}."
                    ),
                )
                session.fail()
                return session

            # Route to the appropriate handler.
            result = await self._dispatch(method_name, instruction, context, session)

            session.record_action(
                action_type=action_type,
                description=f"Completed: {method_name}",
                output_data=result if isinstance(result, dict) else {"result": str(result)},
                reasoning=f"Action {method_name} completed successfully.",
            )

            session.complete()

        except Exception as exc:
            session.record_action(
                action_type=AgentActionType.PLAN,
                description=f"Error: {exc}",
                reasoning=f"Action failed with exception: {type(exc).__name__}: {exc}",
            )
            session.fail()
            logger.error("Agent session failed: %s", exc, exc_info=True)

        return session

    def _parse_instruction(self, instruction: str) -> tuple[AgentActionType, str]:
        """Match instruction text against known patterns.

        Returns the action type and method name to dispatch.
        """
        for pattern, action_type, method_name in _PATTERNS:
            if re.search(pattern, instruction):
                return action_type, method_name

        # Default: recommend.
        return AgentActionType.RECOMMEND, "recommend"

    async def _dispatch(
        self,
        method_name: str,
        instruction: str,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        """Route to the appropriate orchestrator/engine method."""
        if method_name == "plan_campaign":
            return await self._handle_plan_campaign(instruction, context, session)
        elif method_name == "execute_plan":
            return await self._handle_execute_plan(context, session)
        elif method_name == "monitor_campaign":
            return await self._handle_monitor(context, session)
        elif method_name == "analyze_results":
            return await self._handle_analyze(context, session)
        elif method_name == "plan_program":
            return await self._handle_plan_program(context, session)
        elif method_name == "adjust_program":
            return await self._handle_adjust_program(context, session)
        elif method_name == "generate_pretext":
            return await self._handle_generate_pretext(instruction, context, session)
        elif method_name == "recommend":
            return await self._handle_recommend(instruction, context, session)
        else:
            return {"message": f"Unknown method: {method_name}"}

    async def _handle_plan_campaign(
        self,
        instruction: str,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        addressbook_id = context.get("addressbook_id")
        if not addressbook_id:
            return {"error": "addressbook_id is required in context for campaign planning."}

        constraints = context.get("constraints", {})
        constraints.update(self.profile.get("default_constraints", {}))

        session.record_action(
            action_type=AgentActionType.PLAN,
            description="Planning campaign from objective.",
            input_data={"objective": instruction, "addressbook_id": addressbook_id, "constraints": constraints},
            reasoning="Using orchestrator to analyze address book and produce structured plan.",
        )

        plan = await self.orchestrator.plan_campaign(
            objective=instruction,
            addressbook_id=addressbook_id,
            constraints=constraints,
        )

        return plan.model_dump()

    async def _handle_execute_plan(
        self,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        plan_data = context.get("plan")
        smtp_profile_id = context.get("smtp_profile_id")

        if not plan_data or not smtp_profile_id:
            return {"error": "Both 'plan' and 'smtp_profile_id' are required in context."}

        plan = AgentCampaignPlan(**plan_data) if isinstance(plan_data, dict) else plan_data

        session.record_action(
            action_type=AgentActionType.EXECUTE,
            description=f"Executing plan: {plan.campaign_name}",
            input_data={"plan_name": plan.campaign_name, "smtp_profile_id": smtp_profile_id},
            reasoning="Creating campaign from plan and configuring send parameters.",
        )

        auto_start = context.get("auto_start", False)
        campaign_id = await self.orchestrator.execute_plan(plan, smtp_profile_id, auto_start)

        return {"campaign_id": campaign_id, "status": "created", "auto_start": auto_start}

    async def _handle_monitor(
        self,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        campaign_id = context.get("campaign_id")
        if not campaign_id:
            return {"error": "campaign_id is required in context for monitoring."}

        session.record_action(
            action_type=AgentActionType.MONITOR,
            description=f"Monitoring campaign {campaign_id}.",
            input_data={"campaign_id": campaign_id},
            reasoning="Checking real-time metrics and evaluating campaign health.",
        )

        return await self.orchestrator.monitor_campaign(campaign_id)

    async def _handle_analyze(
        self,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        campaign_id = context.get("campaign_id")
        if not campaign_id:
            return {"error": "campaign_id is required in context for analysis."}

        session.record_action(
            action_type=AgentActionType.ANALYZE,
            description=f"Analyzing campaign {campaign_id} results.",
            input_data={"campaign_id": campaign_id},
            reasoning="Pulling full metrics, generating findings, and comparing to success criteria.",
        )

        result = await self.orchestrator.analyze_results(campaign_id)
        return result.model_dump()

    async def _handle_plan_program(
        self,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        addressbook_id = context.get("addressbook_id")
        if not addressbook_id:
            return {"error": "addressbook_id is required for program planning."}

        campaigns_per_year = context.get("campaigns_per_year", 12)
        config = context.get("config", {})

        session.record_action(
            action_type=AgentActionType.PLAN,
            description=f"Planning annual program: {campaigns_per_year} campaigns.",
            input_data={"addressbook_id": addressbook_id, "campaigns_per_year": campaigns_per_year},
            reasoning="Building year-long program with progressive difficulty and category rotation.",
        )

        plans = await self.scheduler.plan_annual_program(addressbook_id, campaigns_per_year, config)
        return {"program": [p.model_dump() for p in plans], "total_campaigns": len(plans)}

    async def _handle_adjust_program(
        self,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        program_data = context.get("program", [])
        results_data = context.get("completed_results", [])

        from app.agents.schemas import AgentCampaignResult

        program = [
            AgentCampaignPlan(**p) if isinstance(p, dict) else p
            for p in program_data
        ]
        results = [
            AgentCampaignResult(**r) if isinstance(r, dict) else r
            for r in results_data
        ]

        session.record_action(
            action_type=AgentActionType.ADJUST,
            description="Adjusting program based on completed results.",
            input_data={"remaining_campaigns": len(program), "completed_campaigns": len(results)},
            reasoning="Analyzing results to adjust difficulty, department focus, and category mix.",
        )

        adjusted = await self.scheduler.adjust_program(program, results)
        return {"adjusted_program": [p.model_dump() for p in adjusted], "total_campaigns": len(adjusted)}

    async def _handle_generate_pretext(
        self,
        instruction: str,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        request = PretextGenerationRequest(
            target_audience=context.get("target_audience", "general employees"),
            company_context=context.get("company_context", ""),
            difficulty=context.get("difficulty", 2),
            category=context.get("category", "IT"),
            tone=context.get("tone", "professional"),
            urgency_level=context.get("urgency_level", "medium"),
        )

        session.record_action(
            action_type=AgentActionType.PLAN,
            description="Generating pretext email.",
            input_data=request.model_dump(),
            reasoning="Creating phishing simulation email content for authorized testing.",
        )

        result = await self.pretext_engine.generate_pretext(request)
        return result.model_dump()

    async def _handle_recommend(
        self,
        instruction: str,
        context: dict[str, Any],
        session: AgentSession,
    ) -> dict[str, Any]:
        """Provide recommendations based on available data."""
        campaign_ids = context.get("campaign_ids", [])

        if campaign_ids:
            session.record_action(
                action_type=AgentActionType.RECOMMEND,
                description="Generating adaptive difficulty recommendation.",
                input_data={"campaign_ids": campaign_ids},
                reasoning="Analyzing trend across campaigns to recommend difficulty progression.",
            )
            return await self.orchestrator.adaptive_difficulty(campaign_ids)

        return {
            "recommendation": (
                "Provide campaign_ids in context to get data-driven recommendations. "
                "Without historical data, the default recommendation is to start with "
                "difficulty level 2 using IT-category pretexts targeting all departments."
            ),
        }
