"""Agent API router -- AI-driven campaign management endpoints.

Exposes endpoints for planning, executing, monitoring, and analyzing
phishing simulation campaigns via AI agents. Every response includes
reasoning fields for full auditability.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db

from app.agents.orchestrator import AgentOrchestrator
from app.agents.pretext_engine import PretextEngine
from app.agents.scheduler_agent import SchedulerAgent
from app.agents.schemas import (
    AgentCampaignPlan,
    AgentCampaignResult,
    AgentSession,
    ExecuteRequest,
    PlanRequest,
    PretextEvaluateRequest,
    PretextGenerationRequest,
    PretextGenerationResponse,
    ProgramAdjustRequest,
    ProgramRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents")

# In-memory session store. Production deployments should use Redis or a DB.
_sessions: dict[str, AgentSession] = {}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def _get_redis() -> aioredis.Redis | None:
    """Return an async Redis client, or None if unavailable."""
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        logger.warning("Redis unavailable for agent operations.")
        return None


def _check_agent_enabled() -> None:
    """Raise 403 if agent features are disabled."""
    if not settings.AGENT_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Agent features are disabled. Set AGENT_ENABLED=true to enable.",
        )


# ---------------------------------------------------------------------------
# POST /agents/plan
# ---------------------------------------------------------------------------

@router.post("/plan", response_model=AgentCampaignPlan)
async def plan_campaign(
    body: PlanRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> AgentCampaignPlan:
    """Generate a structured campaign plan from an objective.

    The agent analyzes the address book, selects pretexts, determines
    send windows, and calculates difficulty -- all with reasoning.
    """
    _check_agent_enabled()

    redis_client = await _get_redis()
    api_key = settings.ANTHROPIC_API_KEY if body.use_ai else None

    try:
        orchestrator = AgentOrchestrator(db, redis_client, api_key)
        plan = await orchestrator.plan_campaign(
            objective=body.objective,
            addressbook_id=body.addressbook_id,
            constraints=body.constraints,
        )
        return plan
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if redis_client:
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# POST /agents/execute
# ---------------------------------------------------------------------------

@router.post("/execute")
async def execute_plan(
    body: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Execute a previously generated campaign plan.

    Creates the campaign, configures the email template and landing page,
    sets up the send schedule, and optionally starts sending.
    """
    _check_agent_enabled()

    # Safety: refuse auto-start unless explicitly enabled.
    if body.auto_start and not settings.AGENT_AUTO_EXECUTE:
        raise HTTPException(
            status_code=403,
            detail=(
                "Auto-execute is disabled (AGENT_AUTO_EXECUTE=false). "
                "Set auto_start=false to create the campaign in DRAFT status."
            ),
        )

    redis_client = await _get_redis()
    try:
        orchestrator = AgentOrchestrator(db, redis_client)
        campaign_id = await orchestrator.execute_plan(
            plan=body.plan,
            smtp_profile_id=body.smtp_profile_id,
            auto_start=body.auto_start,
        )
        await db.commit()
        return {
            "campaign_id": campaign_id,
            "status": "SCHEDULED" if body.auto_start else "DRAFT",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if redis_client:
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# POST /agents/analyze/{campaign_id}
# ---------------------------------------------------------------------------

@router.post("/analyze/{campaign_id}", response_model=AgentCampaignResult)
async def analyze_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> AgentCampaignResult:
    """Analyze a completed campaign and generate findings.

    Returns metrics summary, department analysis, findings with
    severity and recommendations, plan comparison, and a recommended
    next campaign.
    """
    _check_agent_enabled()

    redis_client = await _get_redis()
    try:
        orchestrator = AgentOrchestrator(db, redis_client)
        result = await orchestrator.analyze_results(campaign_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Campaign analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis failed. Check server logs.")
    finally:
        if redis_client:
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# POST /agents/program
# ---------------------------------------------------------------------------

@router.post("/program")
async def plan_annual_program(
    body: ProgramRequest,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Plan an annual phishing simulation program.

    Returns a list of campaign plans spread across the year with
    progressive difficulty, category rotation, and department coverage.
    """
    _check_agent_enabled()

    scheduler = SchedulerAgent()
    config = body.config.copy()
    config["blackout_dates"] = body.blackout_dates

    try:
        plans = await scheduler.plan_annual_program(
            addressbook_id=body.addressbook_id,
            campaigns_per_year=body.campaigns_per_year,
            config=config,
        )
        return {
            "program": [p.model_dump() for p in plans],
            "total_campaigns": len(plans),
            "addressbook_id": body.addressbook_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /agents/program/adjust
# ---------------------------------------------------------------------------

@router.post("/program/adjust")
async def adjust_program(
    body: ProgramAdjustRequest,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Adjust an annual program based on completed campaign results.

    Re-evaluates remaining campaigns and adjusts difficulty, department
    focus, and category mix based on observed performance.
    """
    _check_agent_enabled()

    scheduler = SchedulerAgent()

    try:
        adjusted = await scheduler.adjust_program(body.program, body.completed_results)
        return {
            "adjusted_program": [p.model_dump() for p in adjusted],
            "total_campaigns": len(adjusted),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# POST /agents/pretext/generate
# ---------------------------------------------------------------------------

@router.post("/pretext/generate", response_model=PretextGenerationResponse)
async def generate_pretext(
    body: PretextGenerationRequest,
    _user: dict = Depends(get_current_user),
) -> PretextGenerationResponse:
    """Generate a phishing simulation pretext.

    Uses Claude API if ANTHROPIC_API_KEY is configured, otherwise falls
    back to selecting and customizing a template from the built-in library.
    """
    _check_agent_enabled()

    engine = PretextEngine(settings.ANTHROPIC_API_KEY or None)
    return await engine.generate_pretext(body)


# ---------------------------------------------------------------------------
# POST /agents/pretext/evaluate
# ---------------------------------------------------------------------------

@router.post("/pretext/evaluate")
async def evaluate_pretext(
    body: PretextEvaluateRequest,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Evaluate an existing pretext email.

    Returns difficulty score, red flag analysis, strengths, weaknesses,
    and improvement suggestions.
    """
    _check_agent_enabled()

    engine = PretextEngine(settings.ANTHROPIC_API_KEY or None)
    return await engine.evaluate_pretext(body.subject, body.body)


# ---------------------------------------------------------------------------
# GET /agents/sessions
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(
    _user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all agent sessions (summary view)."""
    _check_agent_enabled()

    return [
        {
            "session_id": s.session_id,
            "agent_type": s.agent_type,
            "started_at": s.started_at.isoformat(),
            "status": s.status.value,
            "action_count": len(s.actions),
        }
        for s in _sessions.values()
    ]


# ---------------------------------------------------------------------------
# GET /agents/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get full session detail including all actions and reasoning."""
    _check_agent_enabled()

    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    return session.model_dump()
