#!/usr/bin/env python3
"""Docker resource monitor for TidePool containers.

Polls `docker stats --no-stream` at a configurable interval and logs resource
usage (CPU, memory, network I/O, block I/O) to a CSV file. Prints a summary
of peak resource usage per container on exit.

Usage:
    python3 monitor_resources.py
    python3 monitor_resources.py --interval 2 --duration 300 --containers tidepool
    python3 monitor_resources.py --output /tmp/resource_log.csv --interval 10
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing docker stats output
# ---------------------------------------------------------------------------

def _parse_mem_value(s: str) -> float:
    """Parse a memory string like '123.4MiB' or '1.2GiB' into megabytes."""
    s = s.strip()
    match = re.match(r"([\d.]+)\s*(B|KiB|MiB|GiB|TiB|KB|MB|GB|TB)", s, re.IGNORECASE)
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1 / (1024 * 1024),
        "kb": 1 / 1024,
        "kib": 1 / 1024,
        "mb": 1.0,
        "mib": 1.0,
        "gb": 1024.0,
        "gib": 1024.0,
        "tb": 1024 * 1024.0,
        "tib": 1024 * 1024.0,
    }
    return value * multipliers.get(unit, 1.0)


def _parse_cpu_percent(s: str) -> float:
    """Parse a CPU percentage string like '12.34%' into a float."""
    s = s.strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return 0.0


def poll_docker_stats(container_prefix: str | None = None) -> list[dict]:
    """Run `docker stats --no-stream` and parse the output.

    Returns a list of dicts, one per container, with keys:
        container_name, cpu_percent, mem_usage_mb, mem_limit_mb, net_io, block_io
    """
    cmd = [
        "docker", "stats", "--no-stream",
        "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        print("ERROR: 'docker' command not found. Is Docker installed?", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print("WARNING: docker stats timed out.", file=sys.stderr)
        return []

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"WARNING: docker stats returned error: {stderr}", file=sys.stderr)
        return []

    entries = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        name = parts[0].strip()
        if container_prefix and not name.startswith(container_prefix):
            continue

        # Parse memory usage: "123.4MiB / 1.952GiB"
        mem_parts = parts[2].split("/")
        mem_usage = _parse_mem_value(mem_parts[0]) if len(mem_parts) >= 1 else 0.0
        mem_limit = _parse_mem_value(mem_parts[1]) if len(mem_parts) >= 2 else 0.0

        entries.append({
            "container_name": name,
            "cpu_percent": _parse_cpu_percent(parts[1]),
            "mem_usage_mb": round(mem_usage, 2),
            "mem_limit_mb": round(mem_limit, 2),
            "net_io": parts[3].strip(),
            "block_io": parts[4].strip(),
        })

    return entries


# ---------------------------------------------------------------------------
# CSV logger
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "timestamp", "container_name", "cpu_percent", "mem_usage_mb",
    "mem_limit_mb", "net_io", "block_io",
]


class ResourceLogger:
    """Writes resource samples to a CSV file."""

    def __init__(self, output_path: str) -> None:
        self.output_path = output_path
        self._fh = open(output_path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=CSV_COLUMNS)
        self._writer.writeheader()
        self._sample_count = 0

    def write_sample(self, timestamp: str, entries: list[dict]) -> None:
        for entry in entries:
            row = {"timestamp": timestamp, **entry}
            self._writer.writerow(row)
        self._fh.flush()
        self._sample_count += len(entries)

    @property
    def sample_count(self) -> int:
        return self._sample_count

    def close(self) -> None:
        self._fh.close()


# ---------------------------------------------------------------------------
# Peak tracking
# ---------------------------------------------------------------------------

class PeakTracker:
    """Track peak CPU and memory per container."""

    def __init__(self) -> None:
        self._peaks: dict[str, dict[str, float]] = {}

    def update(self, entries: list[dict]) -> None:
        for entry in entries:
            name = entry["container_name"]
            if name not in self._peaks:
                self._peaks[name] = {
                    "peak_cpu_percent": 0.0,
                    "peak_mem_mb": 0.0,
                    "mem_limit_mb": entry["mem_limit_mb"],
                }
            current = self._peaks[name]
            current["peak_cpu_percent"] = max(
                current["peak_cpu_percent"], entry["cpu_percent"]
            )
            current["peak_mem_mb"] = max(
                current["peak_mem_mb"], entry["mem_usage_mb"]
            )
            current["mem_limit_mb"] = entry["mem_limit_mb"]

    def print_summary(self) -> None:
        if not self._peaks:
            print("\nNo container data collected.")
            return

        print("\n" + "=" * 70)
        print("RESOURCE MONITOR SUMMARY -- Peak Values per Container")
        print("=" * 70)
        header = f"{'Container':<35} {'Peak CPU %':>11} {'Peak Mem MB':>13} {'Limit MB':>10}"
        print(header)
        print("-" * 70)

        for name in sorted(self._peaks):
            p = self._peaks[name]
            print(
                f"{name:<35} {p['peak_cpu_percent']:>11.2f} "
                f"{p['peak_mem_mb']:>13.2f} {p['mem_limit_mb']:>10.2f}"
            )

        print("=" * 70)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_stop_requested = False


def _signal_handler(signum, frame):
    global _stop_requested
    _stop_requested = True


def run_monitor(
    interval: int,
    output_path: str,
    duration: int,
    container_prefix: str | None,
) -> None:
    """Main monitoring loop. Polls docker stats and logs to CSV."""
    global _stop_requested

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger = ResourceLogger(output_path)
    tracker = PeakTracker()

    prefix_display = container_prefix or "(all)"
    print(f"Monitoring Docker containers (prefix: {prefix_display})")
    print(f"Interval : {interval}s")
    print(f"Duration : {'unlimited' if duration <= 0 else f'{duration}s'}")
    print(f"Output   : {output_path}")
    print("Press Ctrl+C to stop.\n")

    start_time = time.monotonic()
    poll_count = 0

    try:
        while not _stop_requested:
            # Check duration limit
            if duration > 0:
                elapsed = time.monotonic() - start_time
                if elapsed >= duration:
                    print(f"\nDuration limit ({duration}s) reached.")
                    break

            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            entries = poll_docker_stats(container_prefix)
            poll_count += 1

            if entries:
                logger.write_sample(timestamp, entries)
                tracker.update(entries)

                # Print a compact status line
                names = ", ".join(e["container_name"] for e in entries[:3])
                if len(entries) > 3:
                    names += f" (+{len(entries) - 3} more)"
                print(f"[{timestamp}] {len(entries)} containers: {names}")
            else:
                print(f"[{timestamp}] No matching containers found.")

            # Sleep in small increments to remain responsive to signals
            sleep_end = time.monotonic() + interval
            while not _stop_requested and time.monotonic() < sleep_end:
                time.sleep(min(0.5, sleep_end - time.monotonic()))

    finally:
        logger.close()
        elapsed_total = time.monotonic() - start_time
        print(f"\nMonitoring stopped after {elapsed_total:.1f}s ({poll_count} polls)")
        print(f"Data written to: {output_path} ({logger.sample_count} records)")
        tracker.print_summary()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Docker resource monitor for TidePool containers. "
            "Polls 'docker stats --no-stream' at a configurable interval and "
            "logs CPU, memory, network I/O, and block I/O to a CSV file. "
            "Prints a summary of peak resource usage per container on exit."
        ),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in seconds. Default: 5.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Path for the output CSV file. "
            "Default: resource_monitor_{timestamp}.csv in the current directory."
        ),
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help=(
            "Maximum monitoring duration in seconds. "
            "0 means unlimited (run until Ctrl+C). Default: 0."
        ),
    )
    parser.add_argument(
        "--containers",
        type=str,
        default="tidepool",
        help=(
            "Filter containers by name prefix. Only containers whose name "
            "starts with this string are monitored. Use empty string for all "
            "containers. Default: 'tidepool'."
        ),
    )
    args = parser.parse_args()

    if args.interval < 1:
        parser.error("Interval must be at least 1 second.")

    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"resource_monitor_{ts}.csv"

    container_prefix = args.containers if args.containers else None

    run_monitor(
        interval=args.interval,
        output_path=output_path,
        duration=args.duration,
        container_prefix=container_prefix,
    )


if __name__ == "__main__":
    main()
