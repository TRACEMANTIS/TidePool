#!/usr/bin/env python3
"""Standalone MCP server launcher for TidePool.

Starts a Model Context Protocol server on stdio transport, exposing
TidePool campaign management tools to AI agents (e.g. Claude Code).

Configuration is via environment variables:
    TIDEPOOL_URL     -- Base URL of the TidePool API (default: http://localhost:8000)
    TIDEPOOL_API_KEY -- API key for authentication

Usage:
    python mcp_server.py                  # Start MCP server on stdio
    python mcp_server.py --list-tools     # Print available tools and schemas
    python mcp_server.py --test           # Run self-test against each tool
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure backend imports work when running from the scripts directory.
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# The MCP tool registry.  Each tool maps to a TidePool API endpoint.
# When app.agents.mcp_tools exists and exports TidePoolMCPServer, we
# delegate to it.  Otherwise we define a minimal built-in registry so
# the --list-tools and --test flags work without the full backend.

TOOLS: list[dict] = [
    {
        "name": "plan_campaign",
        "description": (
            "Plan a phishing campaign.  Accepts an objective string and "
            "addressbook_id, returns a structured campaign plan."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "Goal of the campaign."},
                "addressbook_id": {"type": "integer", "description": "Target address book ID."},
                "constraints": {"type": "string", "description": "Optional constraints."},
            },
            "required": ["objective", "addressbook_id"],
        },
    },
    {
        "name": "execute_plan",
        "description": (
            "Execute a previously generated campaign plan.  Requires the plan "
            "object and an SMTP profile ID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "Plan object from plan_campaign."},
                "smtp_profile_id": {"type": "integer", "description": "SMTP profile to use."},
                "auto_start": {"type": "boolean", "description": "Start sending immediately.", "default": False},
            },
            "required": ["plan", "smtp_profile_id"],
        },
    },
    {
        "name": "get_campaign_stats",
        "description": "Get real-time stats for a running campaign.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "Campaign ID."},
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "analyze_campaign",
        "description": (
            "Analyze completed campaign results.  Returns findings, risk score, "
            "and recommendations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "integer", "description": "Campaign ID to analyze."},
            },
            "required": ["campaign_id"],
        },
    },
    {
        "name": "create_program",
        "description": (
            "Create an annual phishing program with scheduled campaigns."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "addressbook_id": {"type": "integer", "description": "Target address book ID."},
                "campaigns_per_year": {"type": "integer", "description": "Number of campaigns per year."},
                "objective": {"type": "string", "description": "Program objective."},
            },
            "required": ["addressbook_id", "campaigns_per_year"],
        },
    },
    {
        "name": "generate_pretext",
        "description": "Generate a pretext/lure email for a phishing campaign.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
                    "description": "Lure category.",
                },
                "difficulty": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Difficulty (1=easy to spot, 5=very convincing).",
                },
                "audience": {"type": "string", "description": "Target audience description."},
            },
            "required": ["category", "difficulty"],
        },
    },
    {
        "name": "list_addressbooks",
        "description": "List available address books with contact counts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_smtp_profiles",
        "description": "List configured SMTP profiles.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_campaigns",
        "description": "List campaigns with optional status filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["DRAFT", "RUNNING", "COMPLETED", "CANCELLED", "FAILED"],
                    "description": "Filter by campaign status.",
                },
                "limit": {"type": "integer", "description": "Max results.", "default": 20},
            },
        },
    },
]


# ---------------------------------------------------------------------------
# --list-tools
# ---------------------------------------------------------------------------

def list_tools() -> None:
    """Print all registered tools with their schemas."""
    print(f"TidePool MCP Server -- {len(TOOLS)} tools available")
    print()
    for tool in TOOLS:
        print(f"  {tool['name']}")
        print(f"    {tool['description']}")
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        if props:
            for pname, pschema in props.items():
                req_marker = " (required)" if pname in required else ""
                ptype = pschema.get("type", "any")
                pdesc = pschema.get("description", "")
                print(f"      --{pname}: {ptype}{req_marker}  {pdesc}")
        print()


# ---------------------------------------------------------------------------
# --test
# ---------------------------------------------------------------------------

def run_self_test() -> int:
    """Run a basic self-test by calling each tool with sample data."""
    import httpx

    base_url = os.environ.get("TIDEPOOL_URL", "http://localhost:8000")
    api_key = os.environ.get("TIDEPOOL_API_KEY", "")

    print(f"Self-test against {base_url}")
    print()

    # Check health first
    try:
        resp = httpx.get(f"{base_url}/api/v1/health", timeout=10)
        if resp.status_code == 200:
            print(f"  [PASS] Health check: {resp.json()}")
        else:
            print(f"  [FAIL] Health check: HTTP {resp.status_code}")
            return 1
    except httpx.ConnectError:
        print(f"  [FAIL] Cannot connect to {base_url}")
        print(f"         Ensure the TidePool server is running.")
        return 1
    except Exception as exc:
        print(f"  [FAIL] Health check error: {exc}")
        return 1

    headers = {"X-API-Key": api_key} if api_key else {}

    # Test each tool endpoint with safe read-only calls where possible
    test_cases = [
        ("list_addressbooks", "GET", "/api/v1/addressbooks", None),
        ("list_smtp_profiles", "GET", "/api/v1/smtp-profiles", None),
        ("list_campaigns", "GET", "/api/v1/campaigns?limit=1", None),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for tool_name, method, path, body in test_cases:
        try:
            if method == "GET":
                resp = httpx.get(f"{base_url}{path}", headers=headers, timeout=15)
            else:
                resp = httpx.post(f"{base_url}{path}", headers=headers, json=body, timeout=15)

            if resp.status_code < 400:
                print(f"  [PASS] {tool_name}: HTTP {resp.status_code}")
                passed += 1
            elif resp.status_code == 401:
                print(f"  [SKIP] {tool_name}: Authentication required (set TIDEPOOL_API_KEY)")
                skipped += 1
            else:
                print(f"  [FAIL] {tool_name}: HTTP {resp.status_code}")
                failed += 1
        except Exception as exc:
            print(f"  [FAIL] {tool_name}: {exc}")
            failed += 1

    # Report tools that require write operations (skip in self-test)
    write_tools = [
        "plan_campaign", "execute_plan", "analyze_campaign",
        "create_program", "generate_pretext",
    ]
    for name in write_tools:
        print(f"  [SKIP] {name}: write operation (skipped in self-test)")
        skipped += 1

    print()
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed > 0 else 0


# ---------------------------------------------------------------------------
# MCP stdio server
# ---------------------------------------------------------------------------

def _read_message() -> dict | None:
    """Read a single JSON-RPC message from stdin."""
    # MCP uses Content-Length framed JSON-RPC over stdio.
    # Read headers until blank line.
    content_length = 0
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if not line:
            break  # End of headers
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())

    if content_length <= 0:
        return None

    body = sys.stdin.read(content_length)
    if not body:
        return None
    return json.loads(body)


def _send_message(msg: dict) -> None:
    """Write a JSON-RPC message to stdout with Content-Length framing."""
    body = json.dumps(msg)
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.write(header)
    sys.stdout.write(body)
    sys.stdout.flush()


def _handle_initialize(msg: dict) -> dict:
    """Handle the MCP initialize request."""
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "tidepool",
                "version": "1.0.0",
            },
        },
    }


def _handle_tools_list(msg: dict) -> dict:
    """Handle tools/list request."""
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "tools": TOOLS,
        },
    }


def _dispatch_tool(name: str, arguments: dict) -> dict:
    """Dispatch a tool call to the TidePool API."""
    import httpx

    base_url = os.environ.get("TIDEPOOL_URL", "http://localhost:8000")
    api_key = os.environ.get("TIDEPOOL_API_KEY", "")
    headers = {"X-API-Key": api_key, "Accept": "application/json"} if api_key else {"Accept": "application/json"}
    api = f"{base_url}/api/v1"

    try:
        if name == "plan_campaign":
            resp = httpx.post(f"{api}/agents/plan", json=arguments, headers=headers, timeout=60)
        elif name == "execute_plan":
            resp = httpx.post(f"{api}/agents/execute", json=arguments, headers=headers, timeout=60)
        elif name == "get_campaign_stats":
            cid = arguments["campaign_id"]
            resp = httpx.get(f"{api}/monitor/campaigns/{cid}/live", headers=headers, timeout=30)
        elif name == "analyze_campaign":
            cid = arguments["campaign_id"]
            resp = httpx.post(f"{api}/agents/analyze/{cid}", json={}, headers=headers, timeout=60)
        elif name == "create_program":
            resp = httpx.post(f"{api}/agents/program", json=arguments, headers=headers, timeout=60)
        elif name == "generate_pretext":
            resp = httpx.post(f"{api}/agents/pretext/generate", json=arguments, headers=headers, timeout=60)
        elif name == "list_addressbooks":
            resp = httpx.get(f"{api}/addressbooks", headers=headers, timeout=30)
        elif name == "list_smtp_profiles":
            resp = httpx.get(f"{api}/smtp-profiles", headers=headers, timeout=30)
        elif name == "list_campaigns":
            params = {}
            if arguments.get("status"):
                params["status"] = arguments["status"]
            params["limit"] = arguments.get("limit", 20)
            resp = httpx.get(f"{api}/campaigns", headers=headers, params=params, timeout=30)
        else:
            return {"error": f"Unknown tool: {name}"}

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            return {"error": f"API error (HTTP {resp.status_code}): {detail}"}

        return resp.json()

    except httpx.ConnectError:
        return {"error": f"Cannot connect to TidePool API at {base_url}"}
    except httpx.TimeoutException:
        return {"error": f"Request to TidePool API timed out"}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


def _handle_tools_call(msg: dict) -> dict:
    """Handle tools/call request."""
    params = msg.get("params", {})
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    result = _dispatch_tool(name, arguments)

    is_error = "error" in result and isinstance(result.get("error"), str)
    content_text = json.dumps(result, indent=2, default=str)

    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "content": [{"type": "text", "text": content_text}],
            "isError": is_error,
        },
    }


def run_stdio_server() -> int:
    """Run the MCP server loop on stdio transport."""
    sys.stderr.write("TidePool MCP server starting on stdio...\n")
    sys.stderr.flush()

    while True:
        msg = _read_message()
        if msg is None:
            break  # EOF / client disconnected

        method = msg.get("method", "")

        if method == "initialize":
            _send_message(_handle_initialize(msg))
        elif method == "notifications/initialized":
            pass  # Client acknowledgement, no response needed.
        elif method == "tools/list":
            _send_message(_handle_tools_list(msg))
        elif method == "tools/call":
            _send_message(_handle_tools_call(msg))
        elif method == "shutdown":
            _send_message({
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": None,
            })
            break
        else:
            # Unknown method -- return method-not-found error.
            if msg.get("id") is not None:
                _send_message({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                })

    sys.stderr.write("TidePool MCP server shutting down.\n")
    sys.stderr.flush()
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="TidePool MCP server for AI agent integration.",
    )
    parser.add_argument(
        "--list-tools", action="store_true",
        help="Print all available tools and their schemas, then exit.",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run a self-test against the TidePool API, then exit.",
    )
    args = parser.parse_args()

    if args.list_tools:
        list_tools()
        return 0

    if args.test:
        return run_self_test()

    return run_stdio_server()


if __name__ == "__main__":
    sys.exit(main())
