"""MCP (Model Context Protocol) tool definitions for TidePool.

Defines TidePool as an MCP tool server so that AI agents (including
Claude Code) can connect and drive campaign management end-to-end.

Each tool definition follows the MCP tool schema with name, description,
and input_schema. The TidePoolMCPServer class dispatches tool calls to
the orchestrator, pretext engine, and scheduler.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "tidepool_plan_campaign",
        "description": (
            "Plan a phishing simulation campaign. Analyzes the target address book, "
            "selects pretexts based on the objective, determines optimal send windows, "
            "and produces a structured plan with reasoning for each decision."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Campaign objective (e.g., 'Test credential phishing awareness')",
                },
                "addressbook_id": {
                    "type": "integer",
                    "description": "ID of the target address book",
                },
                "constraints": {
                    "type": "object",
                    "description": "Optional constraints: difficulty, categories, window_hours, etc.",
                    "default": {},
                },
            },
            "required": ["objective", "addressbook_id"],
        },
    },
    {
        "name": "tidepool_execute_campaign",
        "description": (
            "Execute a previously planned campaign. Creates the campaign record, "
            "configures templates and landing pages, and optionally starts sending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "description": "AgentCampaignPlan object from tidepool_plan_campaign",
                },
                "smtp_profile_id": {
                    "type": "integer",
                    "description": "SMTP profile to use for sending",
                },
                "auto_start": {
                    "type": "boolean",
                    "description": "Whether to start sending immediately (requires AGENT_AUTO_EXECUTE=true)",
                    "default": False,
                },
            },
            "required": ["plan", "smtp_profile_id"],
        },
    },
    {
        "name": "tidepool_campaign_status",
        "description": (
            "Check real-time status and live metrics for a running campaign. "
            "Returns sent/opened/clicked counts, send rate, bounce rate, and health assessment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "integer",
                    "description": "Campaign ID to check",
                },
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "tidepool_analyze_campaign",
        "description": (
            "Analyze a completed campaign. Generates findings with severity ratings, "
            "department analysis, plan comparison, and recommends the next campaign."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "integer",
                    "description": "Campaign ID to analyze",
                },
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "tidepool_list_addressbooks",
        "description": "List available address books with recipient counts and department breakdowns.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "tidepool_list_pretexts",
        "description": (
            "List available pretext templates. Filter by category "
            "(IT, HR, FINANCE, EXECUTIVE, VENDOR) and/or difficulty level (1-5)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                    "enum": ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
                },
                "difficulty": {
                    "type": "integer",
                    "description": "Filter by difficulty level (1-5)",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
        },
    },
    {
        "name": "tidepool_generate_pretext",
        "description": (
            "Generate a custom phishing simulation pretext email. "
            "Uses AI if configured, otherwise selects from the built-in library."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_audience": {
                    "type": "string",
                    "description": "Who the simulation targets",
                },
                "company_context": {
                    "type": "string",
                    "description": "Company name, industry, and relevant context",
                },
                "difficulty": {
                    "type": "integer",
                    "description": "Difficulty level 1-5",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
                },
                "category": {
                    "type": "string",
                    "description": "Pretext category",
                    "enum": ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
                    "default": "IT",
                },
                "tone": {
                    "type": "string",
                    "description": "Email tone",
                    "enum": ["professional", "urgent", "casual", "formal"],
                    "default": "professional",
                },
                "urgency_level": {
                    "type": "string",
                    "description": "Urgency level",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
            },
            "required": ["target_audience"],
        },
    },
    {
        "name": "tidepool_upload_addressbook",
        "description": "Upload and process an address book file (CSV or XLSX) for use in campaigns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the CSV or XLSX file",
                },
                "name": {
                    "type": "string",
                    "description": "Name for the address book",
                },
                "email_column": {
                    "type": "string",
                    "description": "Column name containing email addresses",
                },
                "first_name_column": {"type": "string"},
                "last_name_column": {"type": "string"},
                "department_column": {"type": "string"},
            },
            "required": ["file_path", "name", "email_column"],
        },
    },
    {
        "name": "tidepool_plan_program",
        "description": (
            "Plan an annual phishing simulation program. Produces a list of campaigns "
            "with progressive difficulty, category rotation, and department coverage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "addressbook_id": {
                    "type": "integer",
                    "description": "Target address book ID",
                },
                "campaigns_per_year": {
                    "type": "integer",
                    "description": "Number of campaigns to schedule",
                    "default": 12,
                    "minimum": 1,
                    "maximum": 52,
                },
                "blackout_dates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO date strings to avoid",
                    "default": [],
                },
                "config": {
                    "type": "object",
                    "description": "Additional configuration: departments, base_difficulty, max_difficulty, etc.",
                    "default": {},
                },
            },
            "required": ["addressbook_id"],
        },
    },
    {
        "name": "tidepool_org_risk",
        "description": "Get the organization-wide risk score across specified campaigns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Campaign IDs to include in risk calculation",
                },
            },
            "required": ["campaign_ids"],
        },
    },
    {
        "name": "tidepool_department_metrics",
        "description": "Get per-department metrics for a specific campaign, sorted by risk score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "integer",
                    "description": "Campaign ID",
                },
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "tidepool_export_report",
        "description": "Export a campaign report in the specified format (pdf, csv, or json).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "integer",
                    "description": "Campaign ID to export",
                },
                "format": {
                    "type": "string",
                    "description": "Export format",
                    "enum": ["pdf", "csv", "json"],
                    "default": "json",
                },
            },
            "required": ["campaign_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

class TidePoolMCPServer:
    """MCP tool server for TidePool.

    Dispatches tool calls to the appropriate orchestrator, engine, or
    scheduler method. Handles authentication via API key and returns
    structured results that AI agents can parse.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._db = None
        self._redis = None

    async def _get_db(self) -> Any:
        """Lazy-initialize database session."""
        if self._db is None:
            from app.database import async_session_factory
            self._db = async_session_factory()
        return self._db

    async def _get_redis(self) -> Any:
        """Lazy-initialize Redis client."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                from app.config import settings
                self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception:
                self._redis = None
        return self._redis

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the list of available MCP tools."""
        return TOOLS

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with the given arguments.

        Returns a structured result dict.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}", "available_tools": [t["name"] for t in TOOLS]}

        try:
            return await handler(self, arguments)
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", name, exc, exc_info=True)
            return {"error": str(exc), "tool": name}

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _handle_plan_campaign(self, args: dict) -> dict:
        from app.agents.orchestrator import AgentOrchestrator
        db = await self._get_db()
        redis_client = await self._get_redis()
        orch = AgentOrchestrator(db, redis_client, self.api_key)
        plan = await orch.plan_campaign(
            objective=args["objective"],
            addressbook_id=args["addressbook_id"],
            constraints=args.get("constraints", {}),
        )
        return plan.model_dump()

    async def _handle_execute_campaign(self, args: dict) -> dict:
        from app.agents.orchestrator import AgentOrchestrator
        from app.agents.schemas import AgentCampaignPlan
        db = await self._get_db()
        redis_client = await self._get_redis()
        orch = AgentOrchestrator(db, redis_client, self.api_key)
        plan = AgentCampaignPlan(**args["plan"])
        campaign_id = await orch.execute_plan(
            plan=plan,
            smtp_profile_id=args["smtp_profile_id"],
            auto_start=args.get("auto_start", False),
        )
        await db.commit()
        return {"campaign_id": campaign_id, "status": "created"}

    async def _handle_campaign_status(self, args: dict) -> dict:
        from app.agents.orchestrator import AgentOrchestrator
        db = await self._get_db()
        redis_client = await self._get_redis()
        orch = AgentOrchestrator(db, redis_client)
        return await orch.monitor_campaign(args["campaign_id"])

    async def _handle_analyze_campaign(self, args: dict) -> dict:
        from app.agents.orchestrator import AgentOrchestrator
        db = await self._get_db()
        redis_client = await self._get_redis()
        orch = AgentOrchestrator(db, redis_client)
        result = await orch.analyze_results(args["campaign_id"])
        return result.model_dump()

    async def _handle_list_addressbooks(self, args: dict) -> dict:
        from app.models.addressbook import AddressBook
        from sqlalchemy import select
        db = await self._get_db()
        result = await db.execute(select(AddressBook))
        books = result.scalars().all()
        return {
            "addressbooks": [
                {"id": b.id, "name": b.name}
                for b in books
            ],
        }

    async def _handle_list_pretexts(self, args: dict) -> dict:
        from app.pretext.library import PretextLibrary
        lib = PretextLibrary()
        pretexts = lib.list_pretexts(
            category=args.get("category"),
            difficulty=args.get("difficulty"),
        )
        return {"pretexts": pretexts, "count": len(pretexts)}

    async def _handle_generate_pretext(self, args: dict) -> dict:
        from app.agents.pretext_engine import PretextEngine
        from app.agents.schemas import PretextGenerationRequest
        engine = PretextEngine(self.api_key)
        request = PretextGenerationRequest(
            target_audience=args["target_audience"],
            company_context=args.get("company_context", ""),
            difficulty=args.get("difficulty", 2),
            category=args.get("category", "IT"),
            tone=args.get("tone", "professional"),
            urgency_level=args.get("urgency_level", "medium"),
        )
        result = await engine.generate_pretext(request)
        return result.model_dump()

    async def _handle_upload_addressbook(self, args: dict) -> dict:
        # Address book upload requires file I/O -- return instructions.
        return {
            "message": (
                "Address book upload via MCP is not directly supported. "
                "Use the /api/v1/automation/quick-launch endpoint or the TidePool UI "
                "to upload address book files."
            ),
            "alternative_endpoint": "POST /api/v1/automation/quick-launch",
        }

    async def _handle_plan_program(self, args: dict) -> dict:
        from app.agents.scheduler_agent import SchedulerAgent
        scheduler = SchedulerAgent()
        config = args.get("config", {})
        config["blackout_dates"] = args.get("blackout_dates", [])
        plans = await scheduler.plan_annual_program(
            addressbook_id=args["addressbook_id"],
            campaigns_per_year=args.get("campaigns_per_year", 12),
            config=config,
        )
        return {
            "program": [p.model_dump() for p in plans],
            "total_campaigns": len(plans),
        }

    async def _handle_org_risk(self, args: dict) -> dict:
        from app.reports.aggregator import MetricsAggregator
        db = await self._get_db()
        agg = MetricsAggregator()
        risk = await agg.get_org_risk_score(args["campaign_ids"], db)
        return {
            "org_risk_score": risk.org_risk_score,
            "risk_level": risk.risk_level,
            "department_rankings": [
                {"name": d["name"], "risk_score": d["risk_score"], "headcount": d["headcount"]}
                for d in risk.department_rankings
            ],
            "improvement_delta": risk.improvement_delta,
        }

    async def _handle_department_metrics(self, args: dict) -> dict:
        from app.reports.aggregator import MetricsAggregator
        db = await self._get_db()
        agg = MetricsAggregator()
        depts = await agg.get_department_metrics(args["campaign_id"], db)
        return {
            "departments": [
                {
                    "name": d.name,
                    "headcount": d.headcount,
                    "sent": d.sent,
                    "opened": d.opened,
                    "clicked": d.clicked,
                    "reported": d.reported,
                    "risk_score": d.risk_score,
                }
                for d in depts
            ],
        }

    async def _handle_export_report(self, args: dict) -> dict:
        from app.reports.aggregator import MetricsAggregator
        from app.reports.executive import ExecutiveReportGenerator
        db = await self._get_db()
        agg = MetricsAggregator()
        fmt = args.get("format", "json")
        campaign_id = args["campaign_id"]

        if fmt == "json":
            gen = ExecutiveReportGenerator()
            report = await gen.generate(campaign_id, db)
            return {"format": "json", "report": report}
        else:
            return {
                "message": f"Export format '{fmt}' requires the HTTP API for binary download.",
                "endpoint": f"GET /api/v1/reports/campaigns/{campaign_id}/export/{fmt}",
            }

    # Handler dispatch table.
    _handlers: dict[str, Any] = {
        "tidepool_plan_campaign": _handle_plan_campaign,
        "tidepool_execute_campaign": _handle_execute_campaign,
        "tidepool_campaign_status": _handle_campaign_status,
        "tidepool_analyze_campaign": _handle_analyze_campaign,
        "tidepool_list_addressbooks": _handle_list_addressbooks,
        "tidepool_list_pretexts": _handle_list_pretexts,
        "tidepool_generate_pretext": _handle_generate_pretext,
        "tidepool_upload_addressbook": _handle_upload_addressbook,
        "tidepool_plan_program": _handle_plan_program,
        "tidepool_org_risk": _handle_org_risk,
        "tidepool_department_metrics": _handle_department_metrics,
        "tidepool_export_report": _handle_export_report,
    }


# ---------------------------------------------------------------------------
# MCP stdio transport
# ---------------------------------------------------------------------------

async def _run_stdio_server() -> None:
    """Run the MCP server over stdio (JSON-RPC over stdin/stdout).

    Implements the minimal MCP protocol:
    - tools/list: returns tool definitions
    - tools/call: dispatches to tool handler
    """
    server = TidePoolMCPServer()

    async def read_message() -> dict | None:
        """Read a JSON-RPC message from stdin."""
        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return None
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            return None

    def write_message(msg: dict) -> None:
        """Write a JSON-RPC response to stdout."""
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    logger.info("TidePool MCP server started on stdio.")

    while True:
        message = await read_message()
        if message is None:
            break

        msg_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "initialize":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "tidepool",
                        "version": "1.0.0",
                    },
                },
            })

        elif method == "tools/list":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": server.list_tools()},
            })

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = await server.call_tool(tool_name, tool_args)
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str)},
                    ],
                },
            })

        elif method == "notifications/initialized":
            # Client acknowledgment -- no response needed.
            pass

        else:
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    asyncio.run(_run_stdio_server())
