#!/usr/bin/env python3
"""CLI for launching TidePool phishing campaigns via the automation API.

Usage examples
--------------
Launch with immediate start::

    python quick_launch.py \\
        --excel contacts.xlsx \\
        --email-column "Email" \\
        --subject "Action Required: Password Reset" \\
        --body "Hi {{first_name}}, your password expires in 24 hours..." \\
        --from-name "IT Security" \\
        --from-address "security@company.com" \\
        --smtp-profile-id 1 \\
        --send-hours 8 \\
        --start

Preview only (no records created)::

    python quick_launch.py \\
        --excel contacts.xlsx \\
        --email-column "Email" \\
        --subject "Test" --body "Body" \\
        --from-name "Test" --from-address "t@t.com" \\
        --smtp-profile-id 1 \\
        --preview

Exit codes:
    0  Success
    1  Validation error (bad arguments, missing file, etc.)
    2  API error (server returned an error response)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("ERROR: the 'requests' library is required. Install it with: pip install requests", file=sys.stderr)
    sys.exit(1)


DEFAULT_BASE_URL = os.environ.get("TIDEPOOL_API_URL", "http://localhost:8000")
POLL_INTERVAL_SECONDS = 5


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Launch a TidePool phishing campaign from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required arguments
    p.add_argument(
        "--excel", required=True, metavar="FILE",
        help="Path to an Excel (.xlsx) or CSV file containing contacts.",
    )
    p.add_argument(
        "--email-column", required=True, metavar="COL",
        help="Name of the column that contains email addresses.",
    )
    p.add_argument(
        "--subject", required=True,
        help="Email subject line for the lure.",
    )
    p.add_argument(
        "--body", required=True,
        help="Email body. Supports {{first_name}}, {{last_name}}, {{department}}, {{company}} variables.",
    )
    p.add_argument(
        "--from-name", required=True,
        help="Sender display name.",
    )
    p.add_argument(
        "--from-address", required=True,
        help="Sender email address.",
    )
    p.add_argument(
        "--smtp-profile-id", required=True, type=int,
        help="ID of the SMTP profile to use for sending.",
    )

    # Optional arguments
    p.add_argument(
        "--first-name-column", default=None, metavar="COL",
        help="Column name for first names.",
    )
    p.add_argument(
        "--last-name-column", default=None, metavar="COL",
        help="Column name for last names.",
    )
    p.add_argument(
        "--department-column", default=None, metavar="COL",
        help="Column name for departments.",
    )
    p.add_argument(
        "--category", default="IT",
        choices=["IT", "HR", "FINANCE", "EXECUTIVE", "VENDOR"],
        help="Lure category (default: IT).",
    )
    p.add_argument(
        "--campaign-name", default=None, metavar="NAME",
        help="Campaign name (auto-generated if omitted).",
    )
    p.add_argument(
        "--landing-page-id", default=None, type=int,
        help="Landing page ID. Uses default credential harvester if omitted.",
    )
    p.add_argument(
        "--training-module-id", default=None, type=int,
        help="Training module ID. Uses default if omitted.",
    )
    p.add_argument(
        "--send-hours", default=24, type=int, metavar="N",
        help="Spread sends over N hours (default: 24).",
    )

    # Flags
    p.add_argument(
        "--start", action="store_true",
        help="Start sending immediately after creation.",
    )
    p.add_argument(
        "--preview", action="store_true",
        help="Preview the first 5 rendered emails without creating anything.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Validate everything without creating database records.",
    )

    # Connection
    p.add_argument(
        "--api-url", default=DEFAULT_BASE_URL,
        help=f"Base URL of the TidePool API (default: {DEFAULT_BASE_URL}).",
    )
    p.add_argument(
        "--token", default=os.environ.get("TIDEPOOL_TOKEN"),
        help="Bearer token for API authentication (or set TIDEPOOL_TOKEN env var).",
    )

    return p


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _headers(token: str | None) -> dict[str, str]:
    h: dict[str, str] = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _build_form_data(args: argparse.Namespace) -> dict[str, str]:
    """Build the multipart form fields from parsed arguments."""
    data: dict[str, str] = {
        "email_column": args.email_column,
        "lure_category": args.category,
        "lure_subject": args.subject,
        "lure_body": args.body,
        "from_name": args.from_name,
        "from_address": args.from_address,
        "smtp_profile_id": str(args.smtp_profile_id),
        "send_window_hours": str(args.send_hours),
        "start_immediately": str(args.start).lower(),
    }
    if args.first_name_column:
        data["first_name_column"] = args.first_name_column
    if args.last_name_column:
        data["last_name_column"] = args.last_name_column
    if args.department_column:
        data["department_column"] = args.department_column
    if args.campaign_name:
        data["campaign_name"] = args.campaign_name
    if args.landing_page_id is not None:
        data["landing_page_id"] = str(args.landing_page_id)
    if args.training_module_id is not None:
        data["training_module_id"] = str(args.training_module_id)
    return data


def _open_file(path: str) -> tuple:
    """Open a file for upload and return a (filename, file_obj, content_type) tuple."""
    basename = os.path.basename(path)
    ext = os.path.splitext(basename)[1].lower()
    content_type = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
    }.get(ext, "application/octet-stream")
    return (basename, open(path, "rb"), content_type)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_preview(args: argparse.Namespace) -> int:
    """Preview rendered emails."""
    url = urljoin(args.api_url + "/", "api/v1/automation/preview")
    file_tuple = _open_file(args.excel)

    try:
        resp = requests.post(
            url,
            headers=_headers(args.token),
            data=_build_form_data(args),
            files={"file": file_tuple},
            timeout=120,
        )
    finally:
        file_tuple[1].close()

    if resp.status_code != 200:
        print(f"ERROR: API returned {resp.status_code}: {resp.text}", file=sys.stderr)
        return 2

    data = resp.json()
    print(f"Total recipients: {data['total_recipients']}")
    print(f"Estimated duration: {data['estimated_duration_hours']:.1f} hours")
    print()

    for i, email in enumerate(data["emails"], 1):
        print(f"--- Preview #{i} ---")
        print(f"  To:      {email['to']}")
        print(f"  Subject: {email['subject']}")
        print(f"  Body:    {email['body_preview'][:200]}")
        print()

    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    """Create (and optionally start) a campaign."""
    url = urljoin(args.api_url + "/", "api/v1/automation/quick-launch")

    file_size = os.path.getsize(args.excel)
    print(f"File: {args.excel} ({file_size:,} bytes)")

    file_tuple = _open_file(args.excel)

    try:
        resp = requests.post(
            url,
            headers=_headers(args.token),
            data=_build_form_data(args),
            files={"file": file_tuple},
            timeout=300,
        )
    finally:
        file_tuple[1].close()

    if resp.status_code not in (200, 201):
        print(f"ERROR: API returned {resp.status_code}: {resp.text}", file=sys.stderr)
        return 2

    data = resp.json()
    campaign_id = data["campaign_id"]

    print(f"Campaign created: {data['name']}")
    print(f"  ID:         {campaign_id}")
    print(f"  Recipients: {data['total_recipients']}")
    print(f"  Status:     {data['status']}")
    if data.get("estimated_completion"):
        print(f"  ETA:        {data['estimated_completion']}")

    # If started, poll for progress.
    if args.start:
        print()
        print("Monitoring send progress (Ctrl+C to stop monitoring)...")
        return _poll_status(args, campaign_id)

    return 0


def _poll_status(args: argparse.Namespace, campaign_id: int) -> int:
    """Poll the campaign status endpoint until completion or interruption."""
    url = urljoin(args.api_url + "/", f"api/v1/automation/campaigns/{campaign_id}/status")

    try:
        while True:
            resp = requests.get(url, headers=_headers(args.token), timeout=30)
            if resp.status_code != 200:
                print(f"ERROR: Status check failed: {resp.status_code}", file=sys.stderr)
                return 2

            data = resp.json()
            sent = data.get("sent", 0)
            total = data.get("total", 0)
            pending = data.get("pending", 0)
            failed = data.get("failed", 0)
            status_val = data.get("status", "UNKNOWN")
            rate = data.get("rate_per_minute", 0)

            pct = (sent / total * 100) if total > 0 else 0
            bar_len = 40
            filled = int(bar_len * pct / 100)
            bar = "#" * filled + "-" * (bar_len - filled)

            print(
                f"\r  [{bar}] {pct:5.1f}%  "
                f"sent={sent} pending={pending} failed={failed}  "
                f"rate={rate:.1f}/min  status={status_val}   ",
                end="",
                flush=True,
            )

            if status_val in ("COMPLETED", "CANCELLED", "FAILED"):
                print()
                print(f"Campaign {campaign_id} finished with status: {status_val}")
                return 0

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Monitoring stopped. Campaign continues in the background.")
        return 0


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Validate the file and parameters without creating records.

    Performs the same upload + preview as cmd_preview but explicitly
    labels itself as a dry run.
    """
    print("DRY RUN -- validating inputs only, no records will be created.")
    print()
    return cmd_preview(args)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Validate the file exists.
    if not os.path.isfile(args.excel):
        print(f"ERROR: File not found: {args.excel}", file=sys.stderr)
        return 1

    ext = os.path.splitext(args.excel)[1].lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        print(f"ERROR: Unsupported file type '{ext}'. Use .xlsx, .xls, or .csv.", file=sys.stderr)
        return 1

    if not args.token:
        print("WARNING: No API token provided. Set --token or TIDEPOOL_TOKEN env var.", file=sys.stderr)

    if args.dry_run:
        return cmd_dry_run(args)
    elif args.preview:
        return cmd_preview(args)
    else:
        return cmd_launch(args)


if __name__ == "__main__":
    sys.exit(main())
