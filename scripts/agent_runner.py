#!/usr/bin/env python3
"""CLI for agent-driven TidePool phishing campaigns.

Provides subcommands for planning, executing, monitoring, and analyzing
campaigns through the TidePool agent API.  Designed for operator use and
CI/CD integration.

Usage examples
--------------
Plan a campaign::

    python agent_runner.py plan --objective "Test Q2 phishing readiness" --addressbook-id 1

Execute a saved plan::

    python agent_runner.py execute --plan-file plan.json --smtp-profile-id 1 --auto-start

Monitor a running campaign::

    python agent_runner.py monitor --campaign-id 42

Analyze results::

    python agent_runner.py analyze --campaign-id 42

Create an annual program::

    python agent_runner.py program --addressbook-id 1 --campaigns-per-year 12

Generate a pretext email::

    python agent_runner.py generate-pretext --category IT --difficulty 3 --audience "Engineering"

Full autonomous cycle::

    python agent_runner.py full-cycle --objective "Monthly test" --addressbook-id 1 --smtp-profile-id 1

Exit codes:
    0  Success
    1  Validation / argument error
    2  API error (server returned an error response)
    3  Connection error (API unreachable)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print(
        "ERROR: the 'httpx' library is required.  Install it with:  pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:8000"
POLL_INTERVAL_SECONDS = 10
API_PREFIX = "/api/v1"

# ANSI colour helpers
_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_DIM = "\033[2m"


def _colour_enabled() -> bool:
    """Return True if stdout is a TTY that supports colour."""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _colour_enabled():
        return f"{code}{text}{_RESET}"
    return text


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class TidePoolClient:
    """Thin wrapper around httpx for TidePool API calls."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{API_PREFIX}{path}"

    def get(self, path: str, **kwargs) -> httpx.Response:
        try:
            return httpx.get(
                self._url(path),
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.ConnectError as exc:
            _die_connection(self.base_url, exc)
        except httpx.TimeoutException as exc:
            _die_timeout(self.base_url, exc)

    def post(self, path: str, **kwargs) -> httpx.Response:
        try:
            return httpx.post(
                self._url(path),
                headers=self._headers(),
                timeout=self.timeout,
                **kwargs,
            )
        except httpx.ConnectError as exc:
            _die_connection(self.base_url, exc)
        except httpx.TimeoutException as exc:
            _die_timeout(self.base_url, exc)


def _die_connection(url: str, exc: Exception) -> None:
    print(
        f"{_c(_RED, 'ERROR')}: Cannot connect to TidePool API at {url}\n"
        f"  Detail: {exc}\n"
        f"  Verify the server is running and the URL is correct.",
        file=sys.stderr,
    )
    sys.exit(3)


def _die_timeout(url: str, exc: Exception) -> None:
    print(
        f"{_c(_RED, 'ERROR')}: Request to {url} timed out.\n"
        f"  Detail: {exc}",
        file=sys.stderr,
    )
    sys.exit(3)


def _check_response(resp: httpx.Response, context: str = "") -> dict:
    """Validate an API response and return the parsed JSON body."""
    if resp.status_code >= 400:
        label = context or "API request"
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        print(
            f"{_c(_RED, 'ERROR')}: {label} failed (HTTP {resp.status_code}):\n  {detail}",
            file=sys.stderr,
        )
        sys.exit(2)
    return resp.json()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _progress_bar(fraction: float, width: int = 40) -> str:
    """Render an ASCII progress bar."""
    filled = int(width * fraction)
    bar = "#" * filled + "-" * (width - filled)
    pct = fraction * 100
    return f"[{bar}] {pct:5.1f}%"


def _table(rows: list[list[str]], headers: list[str] | None = None) -> str:
    """Format a simple text table."""
    all_rows = ([headers] if headers else []) + rows
    if not all_rows:
        return ""
    col_widths = [0] * len(all_rows[0])
    for row in all_rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    lines: list[str] = []
    for idx, row in enumerate(all_rows):
        cells = [str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)]
        lines.append("  ".join(cells))
        if idx == 0 and headers:
            lines.append("  ".join("-" * w for w in col_widths))
    return "\n".join(lines)


def _write_json(data: dict | list, path: str) -> None:
    """Write data as pretty-printed JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"{_c(_DIM, 'Saved to')} {path}")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Subcommand: plan
# ---------------------------------------------------------------------------

def cmd_plan(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Plan a campaign via the agent API."""
    payload = {
        "objective": args.objective,
        "addressbook_id": args.addressbook_id,
    }
    if args.constraints:
        payload["constraints"] = args.constraints

    print(f"{_c(_CYAN, 'Planning')} campaign: {args.objective}")
    resp = client.post("/agents/plan", json=payload)
    data = _check_response(resp, "Campaign planning")

    # Display summary
    plan = data.get("plan", data)
    print()
    print(f"{_c(_BOLD, 'Plan Summary')}")
    print(f"  Objective:    {plan.get('objective', 'N/A')}")
    print(f"  Targets:      {plan.get('target_count', 'N/A')}")
    print(f"  Lure type:    {plan.get('lure_category', 'N/A')}")
    print(f"  Difficulty:   {plan.get('difficulty', 'N/A')}")
    print(f"  Send window:  {plan.get('send_window_hours', 'N/A')} hours")
    if plan.get("schedule"):
        print(f"  Schedule:     {plan.get('schedule')}")

    # Save plan to file
    outfile = args.output or f"plan_{_timestamp()}.json"
    _write_json(data, outfile)

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: execute
# ---------------------------------------------------------------------------

def cmd_execute(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Execute a saved plan."""
    plan_path = Path(args.plan_file)
    if not plan_path.is_file():
        print(f"{_c(_RED, 'ERROR')}: Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    with open(plan_path) as f:
        plan_data = json.load(f)

    payload = {
        "plan": plan_data.get("plan", plan_data),
        "smtp_profile_id": args.smtp_profile_id,
        "auto_start": args.auto_start,
    }
    if args.landing_page_id is not None:
        payload["landing_page_id"] = args.landing_page_id

    print(f"{_c(_CYAN, 'Executing')} plan from {plan_path.name} ...")
    resp = client.post("/agents/execute", json=payload)
    data = _check_response(resp, "Campaign execution")

    campaign_id = data.get("campaign_id")
    print()
    print(f"{_c(_GREEN, 'Campaign created')}")
    print(f"  Campaign ID:  {campaign_id}")
    print(f"  Name:         {data.get('name', 'N/A')}")
    print(f"  Recipients:   {data.get('total_recipients', 'N/A')}")
    print(f"  Status:       {data.get('status', 'N/A')}")

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: monitor
# ---------------------------------------------------------------------------

def cmd_monitor(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Poll campaign status and display a live dashboard."""
    cid = args.campaign_id
    print(f"{_c(_CYAN, 'Monitoring')} campaign {cid}  (Ctrl+C to stop)")
    print()

    try:
        while True:
            resp = client.get(f"/monitor/campaigns/{cid}/live")
            if resp.status_code == 404:
                print(f"{_c(_RED, 'ERROR')}: Campaign {cid} not found.", file=sys.stderr)
                return 2
            data = _check_response(resp, "Live stats")

            sent = data.get("sent", 0)
            delivered = data.get("delivered", 0)
            opened = data.get("opened", 0)
            clicked = data.get("clicked", 0)
            submitted = data.get("submitted", 0)
            reported = data.get("reported", 0)
            rate = data.get("send_rate_per_minute", 0.0)
            status_val = data.get("status", "unknown")
            eta_seconds = data.get("eta_seconds")

            # Compute total from sent + pending (or use sent as denominator)
            total = sent + data.get("pending", 0) if data.get("pending") else sent
            if total <= 0:
                total = max(sent, 1)
            fraction = min(sent / total, 1.0) if total > 0 else 0.0

            eta_str = "N/A"
            if eta_seconds is not None and eta_seconds > 0:
                mins, secs = divmod(int(eta_seconds), 60)
                hrs, mins = divmod(mins, 60)
                if hrs > 0:
                    eta_str = f"{hrs}h {mins}m"
                else:
                    eta_str = f"{mins}m {secs}s"

            status_colour = {
                "RUNNING": _GREEN,
                "COMPLETED": _CYAN,
                "FAILED": _RED,
                "CANCELLED": _YELLOW,
            }.get(status_val.upper(), _DIM)

            # Build dashboard line
            bar = _progress_bar(fraction)
            line = (
                f"\r  {bar}  "
                f"sent={sent} opened={opened} clicked={clicked} submitted={submitted}  "
                f"rate={rate:.1f}/min  ETA={eta_str}  "
                f"status={_c(status_colour, status_val)}   "
            )
            print(line, end="", flush=True)

            if status_val.upper() in ("COMPLETED", "CANCELLED", "FAILED"):
                print()
                print()
                print(f"Campaign {cid} finished: {_c(status_colour, status_val)}")
                print()
                # Print final metrics table
                rows = [
                    ["Sent", str(sent)],
                    ["Delivered", str(delivered)],
                    ["Opened", str(opened)],
                    ["Clicked", str(clicked)],
                    ["Submitted", str(submitted)],
                    ["Reported", str(reported)],
                ]
                print(_table(rows, headers=["Metric", "Count"]))
                return 0

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Monitoring stopped.  Campaign continues in the background.")
        return 0


# ---------------------------------------------------------------------------
# Subcommand: analyze
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Request agent analysis of campaign results."""
    cid = args.campaign_id
    print(f"{_c(_CYAN, 'Analyzing')} campaign {cid} ...")
    resp = client.post(f"/agents/analyze/{cid}", json={})
    data = _check_response(resp, "Campaign analysis")

    analysis = data.get("analysis", data)

    print()
    print(f"{_c(_BOLD, 'Analysis Results')}")
    print()

    if analysis.get("summary"):
        print(f"  {_c(_BOLD, 'Summary')}")
        print(f"  {analysis['summary']}")
        print()

    if analysis.get("risk_score") is not None:
        print(f"  Risk Score:     {analysis['risk_score']}")
    if analysis.get("click_rate") is not None:
        print(f"  Click Rate:     {analysis['click_rate']:.1%}")
    if analysis.get("submit_rate") is not None:
        print(f"  Submit Rate:    {analysis['submit_rate']:.1%}")
    if analysis.get("report_rate") is not None:
        print(f"  Report Rate:    {analysis['report_rate']:.1%}")

    if analysis.get("findings"):
        print()
        print(f"  {_c(_BOLD, 'Findings')}")
        for i, finding in enumerate(analysis["findings"], 1):
            severity = finding.get("severity", "INFO")
            sev_colour = {"HIGH": _RED, "MEDIUM": _YELLOW, "LOW": _GREEN}.get(
                severity.upper(), _DIM
            )
            print(f"    {i}. [{_c(sev_colour, severity)}] {finding.get('title', 'N/A')}")
            if finding.get("detail"):
                print(f"       {finding['detail']}")

    if analysis.get("recommendations"):
        print()
        print(f"  {_c(_BOLD, 'Recommendations')}")
        for i, rec in enumerate(analysis["recommendations"], 1):
            print(f"    {i}. {rec}")

    # Save full report
    outfile = args.output or f"analysis_{cid}_{_timestamp()}.json"
    _write_json(data, outfile)

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: program
# ---------------------------------------------------------------------------

def cmd_program(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Create an annual phishing program."""
    payload = {
        "addressbook_id": args.addressbook_id,
        "campaigns_per_year": args.campaigns_per_year,
    }
    if args.objective:
        payload["objective"] = args.objective

    print(f"{_c(_CYAN, 'Creating')} program ({args.campaigns_per_year} campaigns/year) ...")
    resp = client.post("/agents/program", json=payload)
    data = _check_response(resp, "Program creation")

    program = data.get("program", data)
    print()
    print(f"{_c(_BOLD, 'Program Calendar')}")
    print()

    # Display scheduled campaigns in a table
    campaigns = program.get("campaigns", [])
    if campaigns:
        rows = []
        for c in campaigns:
            rows.append([
                c.get("month", "N/A"),
                c.get("objective", "N/A"),
                c.get("category", "N/A"),
                str(c.get("difficulty", "N/A")),
                c.get("status", "planned"),
            ])
        print(_table(rows, headers=["Month", "Objective", "Category", "Difficulty", "Status"]))
    else:
        print("  No campaigns scheduled.")

    outfile = args.output or f"program_{_timestamp()}.json"
    _write_json(data, outfile)

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: generate-pretext
# ---------------------------------------------------------------------------

def cmd_generate_pretext(args: argparse.Namespace, client: TidePoolClient) -> int:
    """Generate a pretext email via the agent API."""
    payload = {
        "category": args.category,
        "difficulty": args.difficulty,
    }
    if args.audience:
        payload["audience"] = args.audience
    if args.context:
        payload["context"] = args.context

    print(f"{_c(_CYAN, 'Generating')} pretext (category={args.category}, difficulty={args.difficulty}) ...")
    resp = client.post("/agents/pretext/generate", json=payload)
    data = _check_response(resp, "Pretext generation")

    pretext = data.get("pretext", data)
    print()
    print(f"  {_c(_BOLD, 'Subject:')} {pretext.get('subject', 'N/A')}")
    print(f"  {_c(_BOLD, 'From:')}    {pretext.get('from_name', 'N/A')} <{pretext.get('from_address', 'N/A')}>")
    print()
    print(f"  {_c(_BOLD, 'Body:')}")
    body = pretext.get("body", "N/A")
    for line in body.splitlines():
        print(f"    {line}")

    if args.save:
        _write_json(data, args.save)

    if args.json_output:
        print(json.dumps(data, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: full-cycle
# ---------------------------------------------------------------------------

def cmd_full_cycle(args: argparse.Namespace, client: TidePoolClient) -> int:
    """End-to-end autonomous campaign: plan, execute, monitor, analyze."""

    # -- Step 1: Plan --
    print(f"{_c(_BOLD, '=== Step 1/5: Planning ===')}")
    plan_payload = {
        "objective": args.objective,
        "addressbook_id": args.addressbook_id,
    }
    resp = client.post("/agents/plan", json=plan_payload)
    plan_data = _check_response(resp, "Campaign planning")
    plan = plan_data.get("plan", plan_data)

    print(f"  Objective:    {plan.get('objective', 'N/A')}")
    print(f"  Targets:      {plan.get('target_count', 'N/A')}")
    print(f"  Lure type:    {plan.get('lure_category', 'N/A')}")
    print(f"  Difficulty:   {plan.get('difficulty', 'N/A')}")
    print(f"  Send window:  {plan.get('send_window_hours', 'N/A')} hours")
    print()

    # -- Step 2: Approval gate --
    if not args.no_approve:
        print(f"{_c(_BOLD, '=== Step 2/5: Approval ===')}")
        print(f"  Review the plan above.")
        try:
            answer = input(f"  Proceed with execution? [{_c(_GREEN, 'y')}/{_c(_RED, 'n')}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            print("Aborted by operator.")
            return 0
        if answer not in ("y", "yes"):
            print("Execution cancelled by operator.")
            return 0
        print()
    else:
        print(f"{_c(_DIM, '  (--no-approve: skipping approval gate)')}")
        print()

    # -- Step 3: Execute --
    print(f"{_c(_BOLD, '=== Step 3/5: Executing ===')}")
    exec_payload = {
        "plan": plan,
        "smtp_profile_id": args.smtp_profile_id,
        "auto_start": True,
    }
    resp = client.post("/agents/execute", json=exec_payload)
    exec_data = _check_response(resp, "Campaign execution")
    campaign_id = exec_data.get("campaign_id")
    print(f"  Campaign ID:  {campaign_id}")
    print(f"  Status:       {exec_data.get('status', 'N/A')}")
    print()

    # -- Step 4: Monitor --
    print(f"{_c(_BOLD, '=== Step 4/5: Monitoring ===')}")
    print(f"  Tracking campaign {campaign_id} until completion ...")
    print()

    try:
        while True:
            resp = client.get(f"/monitor/campaigns/{campaign_id}/live")
            data = _check_response(resp, "Live stats")

            sent = data.get("sent", 0)
            opened = data.get("opened", 0)
            clicked = data.get("clicked", 0)
            submitted = data.get("submitted", 0)
            rate = data.get("send_rate_per_minute", 0.0)
            status_val = data.get("status", "unknown")
            eta_seconds = data.get("eta_seconds")

            total = sent + data.get("pending", 0) if data.get("pending") else max(sent, 1)
            fraction = min(sent / total, 1.0) if total > 0 else 0.0

            eta_str = "N/A"
            if eta_seconds and eta_seconds > 0:
                mins, secs = divmod(int(eta_seconds), 60)
                eta_str = f"{mins}m {secs}s"

            bar = _progress_bar(fraction)
            print(
                f"\r  {bar}  sent={sent} opened={opened} clicked={clicked} "
                f"rate={rate:.1f}/min  ETA={eta_str}   ",
                end="", flush=True,
            )

            if status_val.upper() in ("COMPLETED", "CANCELLED", "FAILED"):
                print()
                print(f"  Campaign finished: {status_val}")
                break

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print()
        print("  Monitoring interrupted.  Proceeding to analysis.")

    print()

    # -- Step 5: Analyze --
    print(f"{_c(_BOLD, '=== Step 5/5: Analyzing ===')}")
    resp = client.post(f"/agents/analyze/{campaign_id}", json={})
    analysis_data = _check_response(resp, "Campaign analysis")
    analysis = analysis_data.get("analysis", analysis_data)

    print()
    print(f"{_c(_BOLD, '--- Executive Summary ---')}")
    print()
    if analysis.get("summary"):
        print(f"  {analysis['summary']}")
        print()

    metrics = []
    for key, label in [
        ("click_rate", "Click Rate"),
        ("submit_rate", "Submit Rate"),
        ("report_rate", "Report Rate"),
        ("risk_score", "Risk Score"),
    ]:
        if analysis.get(key) is not None:
            val = analysis[key]
            if isinstance(val, float) and val <= 1.0 and key != "risk_score":
                metrics.append([label, f"{val:.1%}"])
            else:
                metrics.append([label, str(val)])
    if metrics:
        print(_table(metrics, headers=["Metric", "Value"]))
        print()

    if analysis.get("recommendations"):
        print(f"  {_c(_BOLD, 'Recommendations:')}")
        for i, rec in enumerate(analysis["recommendations"], 1):
            print(f"    {i}. {rec}")
        print()

    # Save combined report
    combined = {
        "plan": plan_data,
        "execution": exec_data,
        "analysis": analysis_data,
        "campaign_id": campaign_id,
        "timestamp": datetime.now().isoformat(),
    }
    outfile = f"full_cycle_{campaign_id}_{_timestamp()}.json"
    _write_json(combined, outfile)

    if args.json_output:
        print(json.dumps(combined, indent=2, default=str))

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent_runner",
        description="CLI for agent-driven TidePool phishing campaigns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Global options
    p.add_argument(
        "--url", default=os.environ.get("TIDEPOOL_URL", DEFAULT_BASE_URL),
        help=f"TidePool API base URL (env: TIDEPOOL_URL, default: {DEFAULT_BASE_URL}).",
    )
    p.add_argument(
        "--api-key", default=os.environ.get("TIDEPOOL_API_KEY"),
        help="API key for authentication (env: TIDEPOOL_API_KEY).",
    )
    p.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Print raw JSON output for machine parsing.",
    )

    subs = p.add_subparsers(dest="command", required=True, help="Available commands")

    # -- plan --
    sp = subs.add_parser("plan", help="Plan a campaign via the agent API.")
    sp.add_argument("--objective", required=True, help="Campaign objective / goal description.")
    sp.add_argument("--addressbook-id", required=True, type=int, help="Address book ID for targets.")
    sp.add_argument("--constraints", help="Optional constraints or notes for the planner.")
    sp.add_argument("--output", "-o", metavar="FILE", help="Output filename for the plan JSON.")

    # -- execute --
    sp = subs.add_parser("execute", help="Execute a saved campaign plan.")
    sp.add_argument("--plan-file", required=True, metavar="FILE", help="Path to a plan JSON file.")
    sp.add_argument("--smtp-profile-id", required=True, type=int, help="SMTP profile ID.")
    sp.add_argument("--landing-page-id", type=int, help="Landing page ID (optional).")
    sp.add_argument("--auto-start", action="store_true", help="Start sending immediately after creation.")

    # -- monitor --
    sp = subs.add_parser("monitor", help="Monitor a running campaign in real time.")
    sp.add_argument("--campaign-id", required=True, type=int, help="Campaign ID to monitor.")

    # -- analyze --
    sp = subs.add_parser("analyze", help="Analyze campaign results via the agent API.")
    sp.add_argument("--campaign-id", required=True, type=int, help="Campaign ID to analyze.")
    sp.add_argument("--output", "-o", metavar="FILE", help="Output filename for the analysis JSON.")

    # -- program --
    sp = subs.add_parser("program", help="Create an annual phishing program.")
    sp.add_argument("--addressbook-id", required=True, type=int, help="Address book ID for targets.")
    sp.add_argument("--campaigns-per-year", required=True, type=int, help="Number of campaigns per year.")
    sp.add_argument("--objective", help="Overall program objective.")
    sp.add_argument("--output", "-o", metavar="FILE", help="Output filename for the program JSON.")

    # -- generate-pretext --
    sp = subs.add_parser("generate-pretext", help="Generate a pretext email.")
    sp.add_argument("--category", required=True, choices=["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
                     help="Lure category.")
    sp.add_argument("--difficulty", required=True, type=int, choices=range(1, 6),
                     help="Difficulty level (1=easy to spot, 5=very convincing).")
    sp.add_argument("--audience", help="Target audience description.")
    sp.add_argument("--context", help="Additional context for the pretext generator.")
    sp.add_argument("--save", metavar="FILE", help="Save the generated pretext to a file.")

    # -- full-cycle --
    sp = subs.add_parser("full-cycle", help="End-to-end autonomous campaign cycle.")
    sp.add_argument("--objective", required=True, help="Campaign objective.")
    sp.add_argument("--addressbook-id", required=True, type=int, help="Address book ID for targets.")
    sp.add_argument("--smtp-profile-id", required=True, type=int, help="SMTP profile ID.")
    sp.add_argument("--no-approve", action="store_true",
                     help="Skip the approval prompt (for CI/CD integration).")

    return p


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.api_key:
        print(
            f"{_c(_YELLOW, 'WARNING')}: No API key provided.  "
            f"Set --api-key or TIDEPOOL_API_KEY env var.",
            file=sys.stderr,
        )

    client = TidePoolClient(
        base_url=args.url,
        api_key=args.api_key,
    )

    dispatch = {
        "plan": cmd_plan,
        "execute": cmd_execute,
        "monitor": cmd_monitor,
        "analyze": cmd_analyze,
        "program": cmd_program,
        "generate-pretext": cmd_generate_pretext,
        "full-cycle": cmd_full_cycle,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args, client)


if __name__ == "__main__":
    sys.exit(main())
