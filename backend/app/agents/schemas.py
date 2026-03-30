"""Agent-specific Pydantic models for AI-driven campaign management.

Defines structured schemas for campaign planning, execution tracking,
result analysis, pretext generation, and session auditing. Every agent
decision carries a reasoning field so that all actions are auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentActionType(str, Enum):
    """Discrete action types an agent can perform."""

    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    MONITOR = "MONITOR"
    ANALYZE = "ANALYZE"
    RECOMMEND = "RECOMMEND"
    ADJUST = "ADJUST"


class AgentSessionStatus(str, Enum):
    """Lifecycle status for an agent session."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Campaign planning
# ---------------------------------------------------------------------------

class PretextSelection(BaseModel):
    """Agent's selection of a pretext template with justification."""

    pretext_id: str
    weight: float = Field(ge=0.0, le=1.0, description="Relative weight for A/B distribution")
    rationale: str = Field(description="Agent's reasoning for selecting this pretext")


class LandingPageStrategy(BaseModel):
    """Landing page configuration for the campaign."""

    template_id: int | None = None
    customization_notes: str = ""


class SendSchedule(BaseModel):
    """When and how emails should be dispatched."""

    start_delay_hours: float = Field(default=0.0, ge=0.0, description="Hours to wait before first send")
    window_hours: int = Field(default=24, ge=1, le=720, description="Total send window duration")
    preferred_send_times: list[str] = Field(
        default_factory=lambda: ["09:00-11:00", "13:00-15:00"],
        description="Hour ranges in HH:MM-HH:MM format when sends are preferred",
    )


class SuccessCriteria(BaseModel):
    """Quantitative targets the campaign aims to measure against."""

    target_click_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    target_report_rate: float = Field(default=0.20, ge=0.0, le=1.0)


class AgentCampaignPlan(BaseModel):
    """A structured plan an agent produces before executing a campaign.

    Every field that represents a decision includes context so a human
    reviewer can understand and approve the plan.
    """

    campaign_name: str
    objective: str
    target_audience: str = Field(description="Description of who to target")
    pretext_strategy: list[PretextSelection] = Field(default_factory=list)
    landing_page_strategy: LandingPageStrategy = Field(default_factory=LandingPageStrategy)
    send_schedule: SendSchedule = Field(default_factory=SendSchedule)
    difficulty_target: int = Field(default=2, ge=1, le=5, description="Difficulty level to aim for")
    department_focus: list[str] | None = Field(
        default=None,
        description="Specific departments to target, or None for all",
    )
    estimated_recipients: int = 0
    success_criteria: SuccessCriteria = Field(default_factory=SuccessCriteria)
    risk_assessment: str = Field(default="", description="Agent's assessment of potential issues")
    scheduled_date: datetime | None = Field(
        default=None,
        description="When this campaign is scheduled (used by annual programs)",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Campaign results and analysis
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    """An individual finding from post-campaign analysis."""

    finding: str
    severity: str = Field(description="HIGH / MEDIUM / LOW / INFO")
    recommendation: str


class PlanComparison(BaseModel):
    """How actual results compared to the plan's success criteria."""

    expected_click_rate: float
    actual_click_rate: float
    delta: float
    assessment: str


class AgentCampaignResult(BaseModel):
    """Post-campaign analysis produced by the agent."""

    campaign_id: int
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    department_analysis: list[dict[str, Any]] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    comparison_to_plan: PlanComparison | None = None
    recommended_next_campaign: AgentCampaignPlan | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Action and session tracking
# ---------------------------------------------------------------------------

class AgentAction(BaseModel):
    """Individual action record within an agent session.

    Captures inputs, outputs, and -- critically -- reasoning for auditing.
    """

    action_type: AgentActionType
    description: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = Field(default="", description="Agent's reasoning for this action")


class AgentSession(BaseModel):
    """Full session tracking for an agent's interaction with TidePool.

    Contains the ordered list of all actions taken, enabling full
    replay and audit of agent decisions.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_type: str = Field(default="general", description="Agent profile identifier")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actions: list[AgentAction] = Field(default_factory=list)
    status: AgentSessionStatus = AgentSessionStatus.ACTIVE

    def record_action(
        self,
        action_type: AgentActionType,
        description: str,
        input_data: dict | None = None,
        output_data: dict | None = None,
        reasoning: str = "",
    ) -> AgentAction:
        """Append a new action to the session and return it."""
        action = AgentAction(
            action_type=action_type,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {},
            reasoning=reasoning,
        )
        self.actions.append(action)
        return action

    def complete(self) -> None:
        self.status = AgentSessionStatus.COMPLETED

    def fail(self) -> None:
        self.status = AgentSessionStatus.FAILED


# ---------------------------------------------------------------------------
# Pretext generation
# ---------------------------------------------------------------------------

class PretextGenerationRequest(BaseModel):
    """Request for AI-generated pretext content."""

    target_audience: str = Field(description="Who the phishing simulation targets")
    company_context: str = Field(default="", description="Company name, industry, and relevant context")
    difficulty: int = Field(default=2, ge=1, le=5)
    category: str = Field(default="IT", description="IT, HR, FINANCE, EXECUTIVE, or VENDOR")
    tone: str = Field(default="professional", description="Tone of the email: professional, urgent, casual, formal")
    urgency_level: str = Field(default="medium", description="low, medium, high")


class PretextGenerationResponse(BaseModel):
    """Generated pretext with metadata and self-evaluation."""

    subject: str
    body_html: str
    body_text: str
    variables_used: list[str] = Field(default_factory=list)
    estimated_difficulty: int = Field(ge=1, le=5)
    red_flags: list[str] = Field(default_factory=list)
    reasoning: str = Field(
        default="",
        description="Why this pretext was generated with these characteristics",
    )


# ---------------------------------------------------------------------------
# API request/response wrappers
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    """Request body for POST /agents/plan."""

    objective: str
    addressbook_id: int
    constraints: dict[str, Any] | None = None
    use_ai: bool = False


class ExecuteRequest(BaseModel):
    """Request body for POST /agents/execute."""

    plan: AgentCampaignPlan
    smtp_profile_id: int
    auto_start: bool = False


class ProgramRequest(BaseModel):
    """Request body for POST /agents/program."""

    addressbook_id: int
    campaigns_per_year: int = Field(default=12, ge=1, le=52)
    blackout_dates: list[str] = Field(
        default_factory=list,
        description="ISO date strings (YYYY-MM-DD) to avoid",
    )
    config: dict[str, Any] = Field(default_factory=dict)


class ProgramAdjustRequest(BaseModel):
    """Request body for POST /agents/program/adjust."""

    program: list[AgentCampaignPlan]
    completed_results: list[AgentCampaignResult]


class PretextEvaluateRequest(BaseModel):
    """Request body for POST /agents/pretext/evaluate."""

    subject: str
    body: str
