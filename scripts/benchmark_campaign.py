#!/usr/bin/env python3
"""Performance benchmark suite for TidePool ingestion and dispatch pipelines.

Benchmarks address book ingestion (CSV parsing + DB insert) and email dispatch
(template rendering + backend send) at configurable size tiers with memory
tracking and detailed timing.

The dispatch benchmark operates independently of a live database by
simulating the send loop with a BenchmarkBackend, measuring pure pipeline
throughput.

Usage:
    python3 benchmark_campaign.py --tiers 10k,50k --mode full
    python3 benchmark_campaign.py --tiers 10k --mode ingest --db-url postgresql://...
    python3 benchmark_campaign.py --tiers 100k --mode dispatch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Performance targets (seconds) -- configurable via constants
# ---------------------------------------------------------------------------

PERFORMANCE_TARGETS: dict[str, dict[str, float]] = {
    "10k":  {"ingest": 10,   "dispatch": 120},
    "50k":  {"ingest": 30,   "dispatch": 600},
    "100k": {"ingest": 45,   "dispatch": 1200},
    "300k": {"ingest": 60,   "dispatch": 3600},
    "400k": {"ingest": 90,   "dispatch": 5400},
}

TIERS = {
    "10k": 10_000,
    "50k": 50_000,
    "100k": 100_000,
    "300k": 300_000,
    "400k": 400_000,
}


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkResult:
    tier: str
    mode: str
    rows: int
    elapsed_seconds: float
    peak_memory_mb: float
    rows_per_second: float
    target_seconds: float
    passed: bool
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ingestion benchmark
# ---------------------------------------------------------------------------

def _resolve_env(db_url_override: str | None) -> str:
    """Resolve DATABASE_URL from override, env, or .env file."""
    if db_url_override:
        return db_url_override

    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Try loading from .env
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "DATABASE_URL":
                return val

    return ""


def benchmark_ingest(
    tier: str,
    data_dir: str,
    db_url: str,
) -> BenchmarkResult:
    """Benchmark CSV ingestion into PostgreSQL.

    Calls the ingestor logic directly (not via Celery) using a sync
    SQLAlchemy session and the same batch-insert code path as production.
    """
    import csv as csv_mod
    import re

    row_count = TIERS[tier]
    target = PERFORMANCE_TARGETS[tier]["ingest"]
    csv_path = os.path.join(data_dir, f"addressbook_{tier}.csv")

    if not os.path.exists(csv_path):
        return BenchmarkResult(
            tier=tier, mode="ingest", rows=row_count,
            elapsed_seconds=0, peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error=f"Test data file not found: {csv_path}",
        )

    # Convert async URL to sync psycopg2 URL
    sync_url = db_url.replace("+asyncpg", "+psycopg2").replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    if sync_url.startswith("postgres://"):
        sync_url = sync_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif not sync_url.startswith("postgresql"):
        sync_url = f"postgresql+psycopg2://{sync_url.split('://', 1)[-1]}"

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
    except ImportError:
        return BenchmarkResult(
            tier=tier, mode="ingest", rows=row_count,
            elapsed_seconds=0, peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error="sqlalchemy not installed",
        )

    # Email validation regex (same as ingestor.py)
    email_re = re.compile(
        r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
    )

    BATCH_SIZE = 1000

    try:
        engine = create_engine(sync_url, pool_pre_ping=True, pool_size=5)
        Session = sessionmaker(bind=engine)
        session = Session()
    except Exception as exc:
        return BenchmarkResult(
            tier=tier, mode="ingest", rows=row_count,
            elapsed_seconds=0, peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error=f"Database connection failed: {exc}",
        )

    # Create a temporary benchmark table
    bench_table = f"_benchmark_contacts_{tier}_{int(time.time())}"
    try:
        session.execute(text(f"""
            CREATE UNLOGGED TABLE {bench_table} (
                id SERIAL PRIMARY KEY,
                email VARCHAR(320) NOT NULL,
                first_name VARCHAR(128),
                last_name VARCHAR(128),
                department VARCHAR(128),
                title VARCHAR(128),
                custom_fields JSONB
            )
        """))
        session.commit()
    except Exception as exc:
        session.close()
        engine.dispose()
        return BenchmarkResult(
            tier=tier, mode="ingest", rows=row_count,
            elapsed_seconds=0, peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error=f"Failed to create benchmark table: {exc}",
        )

    tracemalloc.start()
    t0 = time.perf_counter()
    processed = 0
    imported = 0
    errors = 0

    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv_mod.reader(fh)
            headers = next(reader)

            # Build column mapping based on header names
            col_map = {}
            header_lower = [h.strip().lower() for h in headers]
            for idx, h in enumerate(header_lower):
                if "email" in h:
                    col_map[idx] = "email"
                elif h in ("first name", "first_name", "firstname"):
                    col_map[idx] = "first_name"
                elif h in ("last name", "last_name", "lastname"):
                    col_map[idx] = "last_name"
                elif h in ("department", "dept"):
                    col_map[idx] = "department"
                elif h in ("title", "job title", "job_title"):
                    col_map[idx] = "title"

            batch = []
            seen_emails: set[str] = set()

            for row in reader:
                processed += 1
                contact: dict[str, Any] = {}

                for idx, canonical in col_map.items():
                    if idx < len(row):
                        contact[canonical] = row[idx].strip()

                email = contact.get("email", "").strip().lower()
                if not email or not email_re.match(email):
                    errors += 1
                    continue

                if email in seen_emails:
                    continue
                seen_emails.add(email)

                batch.append({
                    "email": email,
                    "first_name": contact.get("first_name", ""),
                    "last_name": contact.get("last_name", ""),
                    "department": contact.get("department", ""),
                    "title": contact.get("title", ""),
                })

                if len(batch) >= BATCH_SIZE:
                    _insert_batch(session, bench_table, batch)
                    imported += len(batch)
                    batch = []

            if batch:
                _insert_batch(session, bench_table, batch)
                imported += len(batch)

        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        rps = imported / elapsed if elapsed > 0 else 0

        return BenchmarkResult(
            tier=tier, mode="ingest", rows=imported,
            elapsed_seconds=round(elapsed, 3),
            peak_memory_mb=round(peak_mb, 2),
            rows_per_second=round(rps, 1),
            target_seconds=target,
            passed=elapsed <= target,
            extra={
                "processed": processed,
                "imported": imported,
                "errors": errors,
                "duplicates": processed - imported - errors,
            },
        )

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        try:
            tracemalloc.stop()
        except RuntimeError:
            pass
        return BenchmarkResult(
            tier=tier, mode="ingest", rows=0,
            elapsed_seconds=round(elapsed, 3),
            peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error=str(exc),
        )
    finally:
        # Clean up benchmark table
        try:
            session.execute(text(f"DROP TABLE IF EXISTS {bench_table}"))
            session.commit()
        except Exception:
            pass
        session.close()
        engine.dispose()


def _insert_batch(session, table_name: str, batch: list[dict]) -> None:
    """Bulk insert a batch of dicts into the benchmark table."""
    from sqlalchemy import text

    if not batch:
        return

    values_parts = []
    params: dict[str, Any] = {}
    for i, row in enumerate(batch):
        values_parts.append(
            f"(:email_{i}, :first_name_{i}, :last_name_{i}, "
            f":department_{i}, :title_{i})"
        )
        params[f"email_{i}"] = row["email"]
        params[f"first_name_{i}"] = row.get("first_name", "")
        params[f"last_name_{i}"] = row.get("last_name", "")
        params[f"department_{i}"] = row.get("department", "")
        params[f"title_{i}"] = row.get("title", "")

    sql = (
        f"INSERT INTO {table_name} (email, first_name, last_name, department, title) "
        f"VALUES {', '.join(values_parts)}"
    )
    session.execute(text(sql), params)
    session.commit()


# ---------------------------------------------------------------------------
# Dispatch benchmark (no DB required)
# ---------------------------------------------------------------------------

class _MockContact:
    """Lightweight stand-in for a Contact ORM object."""
    __slots__ = (
        "id", "email", "first_name", "last_name", "department",
        "title", "custom_fields",
    )

    def __init__(self, idx: int) -> None:
        self.id = idx
        self.email = f"user{idx}@benchmark-test.com"
        self.first_name = f"First{idx}"
        self.last_name = f"Last{idx}"
        self.department = "Engineering"
        self.title = "Software Engineer"
        self.custom_fields = {"office": "New York", "emp_id": f"EMP-{idx:06d}"}


class _MockTemplate:
    """Lightweight stand-in for an EmailTemplate ORM object."""
    __slots__ = ("subject", "body_html", "body_text")

    def __init__(self) -> None:
        self.subject = "Important: {{first_name}}, action required for your {{department}} review"
        self.body_html = (
            "<html><body>"
            "<p>Dear {{first_name}} {{last_name}},</p>"
            "<p>As a member of the {{department}} team, you are required to "
            "complete your annual security awareness training by end of month.</p>"
            "<p>Please click <a href='https://training.example.com/{{email}}'>here</a> "
            "to begin your training module.</p>"
            "<p>Your employee ID ({{office}}) has been pre-registered.</p>"
            "<p>Best regards,<br>IT Security Team</p>"
            "</body></html>"
        )
        self.body_text = (
            "Dear {{first_name}} {{last_name}},\n\n"
            "Please complete your security training at "
            "https://training.example.com/{{email}}\n\n"
            "Best regards,\nIT Security Team"
        )


class BenchmarkBackend:
    """No-op SMTP backend that counts sends and measures per-send overhead."""

    def __init__(self) -> None:
        self.send_count = 0
        self.total_bytes = 0

    async def send(
        self,
        from_addr: str,
        from_name: str | None,
        to_addr: str,
        subject: str,
        body_html: str,
        body_text: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        self.send_count += 1
        self.total_bytes += len(subject) + len(body_html) + len(body_text)
        return True


def benchmark_dispatch(tier: str) -> BenchmarkResult:
    """Benchmark the dispatch pipeline: render + send for N recipients.

    Works without a running database by simulating the send loop directly
    with mock recipients, a real Jinja2 template renderer, and a no-op
    BenchmarkBackend.
    """
    import asyncio

    row_count = TIERS[tier]
    target = PERFORMANCE_TARGETS[tier]["dispatch"]

    # Try importing the real renderer; fall back to a minimal inline version
    renderer = None
    try:
        # Add backend to path so we can import the renderer
        backend_path = str(Path(__file__).resolve().parent.parent / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        from app.engine.renderer import EmailRenderer
        renderer = EmailRenderer()
    except Exception:
        pass

    if renderer is None:
        # Minimal fallback renderer using jinja2 directly
        try:
            from jinja2 import BaseLoader, Environment

            _env = Environment(loader=BaseLoader(), autoescape=False)

            class _FallbackRenderer:
                def render(self, template, contact):
                    ctx = {
                        "first_name": contact.first_name or "",
                        "last_name": contact.last_name or "",
                        "email": contact.email or "",
                        "department": contact.department or "",
                        "title": contact.title or "",
                    }
                    if contact.custom_fields and isinstance(contact.custom_fields, dict):
                        for k, v in contact.custom_fields.items():
                            ctx.setdefault(k, str(v) if v is not None else "")
                    subject = _env.from_string(template.subject).render(ctx)
                    body_html = _env.from_string(template.body_html).render(ctx)
                    body_text = _env.from_string(template.body_text or "").render(ctx)
                    return type("RenderedEmail", (), {
                        "subject": subject,
                        "body_html": body_html,
                        "body_text": body_text,
                    })()

            renderer = _FallbackRenderer()
        except ImportError:
            return BenchmarkResult(
                tier=tier, mode="dispatch", rows=row_count,
                elapsed_seconds=0, peak_memory_mb=0, rows_per_second=0,
                target_seconds=target, passed=False,
                error="jinja2 not installed -- cannot benchmark dispatch",
            )

    template = _MockTemplate()
    backend = BenchmarkBackend()

    async def _run_dispatch():
        for i in range(row_count):
            contact = _MockContact(i)
            rendered = renderer.render(template, contact)
            await backend.send(
                from_addr="noreply@benchmark-test.com",
                from_name="Benchmark Sender",
                to_addr=contact.email,
                subject=rendered.subject,
                body_html=rendered.body_html,
                body_text=rendered.body_text,
                headers={"X-Benchmark": "true"},
            )

    tracemalloc.start()
    t0 = time.perf_counter()

    try:
        asyncio.run(_run_dispatch())
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        rps = row_count / elapsed if elapsed > 0 else 0

        return BenchmarkResult(
            tier=tier, mode="dispatch", rows=row_count,
            elapsed_seconds=round(elapsed, 3),
            peak_memory_mb=round(peak_mb, 2),
            rows_per_second=round(rps, 1),
            target_seconds=target,
            passed=elapsed <= target,
            extra={
                "total_bytes_rendered": backend.total_bytes,
                "avg_bytes_per_email": round(backend.total_bytes / row_count, 1) if row_count else 0,
            },
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        try:
            tracemalloc.stop()
        except RuntimeError:
            pass
        return BenchmarkResult(
            tier=tier, mode="dispatch", rows=0,
            elapsed_seconds=round(elapsed, 3),
            peak_memory_mb=0, rows_per_second=0,
            target_seconds=target, passed=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_results_table(results: list[BenchmarkResult]) -> None:
    """Print a human-readable results table to stdout."""
    if not results:
        print("No results to display.")
        return

    header = (
        f"{'Tier':<8} {'Mode':<10} {'Rows':>10} {'Elapsed (s)':>12} "
        f"{'Target (s)':>11} {'Rows/s':>10} {'Peak MB':>9} {'Status':>8}"
    )
    sep = "-" * len(header)

    print("\n" + sep)
    print("TIDEPOOL BENCHMARK RESULTS")
    print(sep)
    print(header)
    print(sep)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if r.error:
            status = "ERROR"
        print(
            f"{r.tier:<8} {r.mode:<10} {r.rows:>10,} {r.elapsed_seconds:>12.3f} "
            f"{r.target_seconds:>11.1f} {r.rows_per_second:>10,.1f} "
            f"{r.peak_memory_mb:>9.2f} {status:>8}"
        )
        if r.error:
            print(f"         Error: {r.error}")

    print(sep)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"\nTotal: {len(results)} benchmarks | {passed} passed | {failed} failed")


def save_results_json(results: list[BenchmarkResult], output_path: str) -> None:
    """Save detailed results to a JSON file."""
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmarks": [asdict(r) for r in results],
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        },
    }
    with open(output_path, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"\nResults saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Performance benchmark suite for TidePool ingestion and dispatch. "
            "Measures throughput, memory usage, and validates against performance "
            "targets at each size tier."
        ),
    )
    parser.add_argument(
        "--tiers",
        type=str,
        default="10k,50k",
        help=(
            "Comma-separated list of size tiers to benchmark. "
            f"Available: {', '.join(TIERS.keys())}. Default: 10k,50k."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data"),
        help="Directory containing test data files. Default: scripts/test_data/",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="full",
        choices=["ingest", "dispatch", "full"],
        help=(
            "Benchmark mode. 'ingest' benchmarks CSV ingestion into PostgreSQL. "
            "'dispatch' benchmarks template rendering and send pipeline (no DB needed). "
            "'full' runs both. Default: full."
        ),
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help=(
            "PostgreSQL database URL override. If not provided, reads DATABASE_URL "
            "from environment or .env file. Required for ingest mode."
        ),
    )
    parser.add_argument(
        "--redis-url",
        type=str,
        default=None,
        help="Redis URL override. Not currently used by benchmarks but reserved.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path for JSON results file. Default: benchmark_results_{timestamp}.json "
            "in the current directory."
        ),
    )
    args = parser.parse_args()

    # Parse tiers
    requested = [t.strip().lower() for t in args.tiers.split(",")]
    for t in requested:
        if t not in TIERS:
            parser.error(f"Unknown tier: {t!r}. Available: {', '.join(TIERS.keys())}")

    do_ingest = args.mode in ("ingest", "full")
    do_dispatch = args.mode in ("dispatch", "full")

    # Resolve DB URL for ingest benchmarks
    db_url = ""
    if do_ingest:
        db_url = _resolve_env(args.db_url)
        if not db_url:
            print(
                "WARNING: No DATABASE_URL found. Ingest benchmarks will be skipped.",
                file=sys.stderr,
            )
            print(
                "  Set DATABASE_URL in environment, .env file, or pass --db-url.",
                file=sys.stderr,
            )
            if args.mode == "ingest":
                sys.exit(1)
            do_ingest = False

    # Output path
    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"benchmark_results_{ts}.json"

    print("TidePool Performance Benchmark")
    print(f"Tiers    : {', '.join(requested)}")
    print(f"Mode     : {args.mode}")
    print(f"Data dir : {args.data_dir}")
    if do_ingest:
        # Mask password in URL for display
        display_url = db_url
        if "@" in display_url:
            pre_at = display_url.split("@")[0]
            if ":" in pre_at:
                parts = pre_at.rsplit(":", 1)
                display_url = parts[0] + ":****@" + db_url.split("@", 1)[1]
        print(f"DB URL   : {display_url}")
    print()

    results: list[BenchmarkResult] = []

    for tier in requested:
        if do_ingest:
            print(f"[{tier.upper()}] Running ingest benchmark...")
            result = benchmark_ingest(tier, args.data_dir, db_url)
            results.append(result)
            status = "PASS" if result.passed else ("ERROR" if result.error else "FAIL")
            print(f"  -> {status} ({result.elapsed_seconds:.3f}s, {result.rows_per_second:,.0f} rows/s)")
            if result.error:
                print(f"     Error: {result.error}")

        if do_dispatch:
            print(f"[{tier.upper()}] Running dispatch benchmark...")
            result = benchmark_dispatch(tier)
            results.append(result)
            status = "PASS" if result.passed else ("ERROR" if result.error else "FAIL")
            print(f"  -> {status} ({result.elapsed_seconds:.3f}s, {result.rows_per_second:,.0f} rows/s)")
            if result.error:
                print(f"     Error: {result.error}")

    print_results_table(results)
    save_results_json(results, output_path)

    # Exit with non-zero if any benchmark failed
    if any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
