# Scale Testing Guide

## Overview

TidePool is designed to dispatch phishing simulation campaigns to large organizations. At scale, every component in the pipeline -- file ingestion, address book parsing, task queuing, email rendering, SMTP dispatch, and event tracking -- must perform reliably under sustained load.

Scale testing validates that:

- Ingestion completes within acceptable time windows for large address books.
- Celery workers dispatch emails at the configured throttle rate without starvation or backpressure collapse.
- PostgreSQL handles concurrent writes (campaign events, click tracking) without connection exhaustion.
- Redis maintains token-bucket state and Celery broker queues without running out of memory.
- The system degrades gracefully when a component is under-provisioned rather than failing silently.

This guide covers how to generate test data, configure a benchmark SMTP backend, run load tests at multiple tiers, and interpret the results.

---

## Prerequisites

- Docker and Docker Compose v2 installed.
- The base `docker-compose.yml` and `docker-compose.loadtest.yml` overlay present in the project root.
- Python 3.11+ with the project's dependencies installed (for running test data scripts).
- A BENCHMARK SMTP profile created (see below) -- this prevents test runs from hitting a real mail server.
- Sufficient system resources: at least 8 GB RAM and 4 CPU cores for the 400K tier.

---

## Generating Test Data

Use the included generator script to create address books at multiple size tiers:

```bash
python3 scripts/generate_test_addressbooks.py --tiers 10k,50k,100k,300k,400k
```

This produces CSV and XLSX files in `testdata/`:

```
testdata/
  addressbook_10k.csv
  addressbook_10k.xlsx
  addressbook_50k.csv
  addressbook_50k.xlsx
  addressbook_100k.csv
  addressbook_100k.xlsx
  addressbook_300k.csv
  addressbook_300k.xlsx
  addressbook_400k.csv
  addressbook_400k.xlsx
```

Each file contains realistic fake data (names, emails, departments, titles) suitable for exercising the full ingestion and dispatch pipeline.

---

## Setting Up the Benchmark Backend

Create an SMTP profile with `type=BENCHMARK`. This profile simulates SMTP delivery with configurable latency and failure rate, without sending real emails.

```bash
curl -s -X POST http://localhost:8000/api/v1/smtp-profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Load Test Benchmark",
    "type": "BENCHMARK",
    "config": {
      "simulated_latency_ms": 100,
      "failure_rate": 0.001
    }
  }' | python3 -m json.tool
```

Parameters:

| Parameter | Description | Recommended Value |
|---|---|---|
| `simulated_latency_ms` | Artificial per-email delay in milliseconds | 50--200 |
| `failure_rate` | Fraction of emails that simulate a delivery failure | 0.001 (0.1%) |

Note the returned `id` -- you will reference this profile when creating benchmark campaigns.

---

## Running Benchmarks

### Start the Load Test Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d
```

### Ingestion-Only Mode

Tests address book parsing and database insertion without dispatching emails. Useful for isolating ingestion bottlenecks.

```bash
python3 scripts/run_benchmark.py \
  --mode ingest \
  --addressbook testdata/addressbook_100k.csv \
  --smtp-profile-id <BENCHMARK_PROFILE_ID>
```

### Dispatch-Only Mode

Pre-loads recipients into the database and benchmarks only the Celery task dispatch and simulated SMTP delivery.

```bash
python3 scripts/run_benchmark.py \
  --mode dispatch \
  --campaign-id <PRE_LOADED_CAMPAIGN_ID>
```

### Full End-to-End Mode

Runs the complete pipeline: upload address book, create campaign, ingest recipients, dispatch all emails, and record events.

```bash
python3 scripts/run_benchmark.py \
  --mode full \
  --addressbook testdata/addressbook_400k.csv \
  --smtp-profile-id <BENCHMARK_PROFILE_ID> \
  --throttle-rate 10000
```

### Interpreting Results

The benchmark script outputs a summary including:

- **Ingestion time**: wall-clock time to parse the file and insert recipients.
- **Dispatch time**: wall-clock time from first task enqueue to last task completion.
- **Throughput**: emails dispatched per minute (sustained).
- **Error rate**: percentage of simulated delivery failures vs. actual task failures.
- **P50/P95/P99 latency**: per-email dispatch latency percentiles.

Compare these against the performance targets below.

---

## Performance Targets

| Tier | Recipients | Ingestion (CSV) | Ingestion (XLSX) | Dispatch Rate | Total Dispatch Time | Max Error Rate |
|------|-----------|-----------------|-------------------|---------------|---------------------|----------------|
| 1 | 10,000 | < 5s | < 15s | 5,000/min | < 3 min | < 0.1% |
| 2 | 50,000 | < 20s | < 60s | 8,000/min | < 8 min | < 0.1% |
| 3 | 100,000 | < 40s | < 120s | 10,000/min | < 12 min | < 0.1% |
| 4 | 300,000 | < 120s | < 360s | 10,000/min | < 35 min | < 0.1% |
| 5 | 400,000 | < 160s | < 480s | 10,000/min | < 45 min | < 0.1% |

These targets assume the BENCHMARK SMTP profile with `simulated_latency_ms=100` and workers scaled appropriately (see next section).

---

## Scaling Workers

### Formula

For N emails at a throttle rate of T emails/min, where each email takes L milliseconds of simulated latency:

```
workers_needed = ceil(N / (T * 60))    # minimum to avoid starvation
```

However, the practical constraint is concurrency. Each worker runs `--concurrency=8` prefork processes. Each process blocks for L ms per email. The maximum throughput per worker is:

```
emails_per_worker_per_min = (8 * 60000) / L
```

With L=100ms: each worker can handle ~4,800 emails/min.

To sustain 10,000 emails/min: `ceil(10000 / 4800) = 3 workers minimum`.

For the 400K tier at 10,000/min with overhead and connection contention, use at least 4--5 workers. In practice, scaling to 8 workers provides headroom for GC pauses and database lock contention.

### Scaling Command

```bash
# Scale to 8 worker replicas
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d --scale worker=8
```

### Example Calculation

- 400,000 emails
- Throttle rate: 10,000/min
- Simulated latency: 100ms per email
- Per-worker throughput: ~4,800 emails/min (8 processes x 600 emails/min/process)
- Workers needed: ceil(10000 / 4800) = 3 minimum, recommend 5+ for safety
- Total dispatch time estimate: 400000 / 10000 = 40 minutes

With 17 concurrent worker processes (ceil(10000 / 600)), distributed across 3 workers at concurrency=8 (24 total processes), you have sufficient headroom.

---

## PostgreSQL Tuning

The load test overlay applies the following PostgreSQL settings:

| Parameter | Value | Purpose |
|---|---|---|
| `shared_buffers` | 512MB | In-memory cache for table and index pages. Default 128MB is too low for concurrent campaign event writes. |
| `work_mem` | 64MB | Per-operation sort/hash memory. Helps with large queries during report generation. |
| `max_connections` | 200 | Supports multiple workers each maintaining connection pools. Default 100 is insufficient at scale. |
| `effective_cache_size` | 1GB | Query planner hint for available OS cache. Helps the planner choose index scans over sequential scans. |
| `checkpoint_completion_target` | 0.9 | Spreads checkpoint writes over 90% of the checkpoint interval, reducing I/O spikes. |
| `shm_size` | 1GB | Docker shared memory allocation. Required for shared_buffers > 256MB. |

### Connection Pooling Considerations

Each Celery worker process opens its own database connection pool. With 8 workers at concurrency=8 (64 processes), each maintaining a pool of 5 connections, you need up to 320 connections. The `max_connections=200` setting assumes not all processes will hold connections simultaneously. If you see `too many connections` errors:

1. Increase `max_connections` in the overlay.
2. Deploy PgBouncer as a connection pooler between workers and PostgreSQL.
3. Reduce the per-process pool size in the SQLAlchemy configuration.

---

## Redis Tuning

The load test overlay configures Redis for maximum throughput:

| Parameter | Value | Purpose |
|---|---|---|
| `maxmemory` | 2GB | Upper bound on Redis memory usage. Prevents the container from consuming all host memory. |
| `maxmemory-policy` | allkeys-lru | Evicts least-recently-used keys when memory limit is reached. Acceptable for a load test where old results can be discarded. |
| `save ""` | (disabled) | Disables RDB snapshots. Persistence is unnecessary during benchmarks and the fsync overhead hurts throughput. |
| `appendonly no` | (disabled) | Disables AOF persistence for the same reason. |

### Memory Requirements by Campaign Size

| Campaign Size | Broker Queue Overhead | Token Bucket State | Result Backend | Total Estimate |
|---|---|---|---|---|
| 10,000 | ~20MB | ~5MB | ~30MB | ~55MB |
| 50,000 | ~100MB | ~10MB | ~150MB | ~260MB |
| 100,000 | ~200MB | ~15MB | ~300MB | ~515MB |
| 300,000 | ~600MB | ~30MB | ~900MB | ~1.5GB |
| 400,000 | ~800MB | ~40MB | ~1.2GB | ~2GB |

At the 400K tier, Redis will approach the 2GB limit. The `allkeys-lru` eviction policy ensures the broker remains functional by evicting completed task results first.

### Celery Result Backend Cleanup

For sustained testing, configure result expiry to prevent unbounded growth:

```python
# In celery config
result_expires = 3600  # 1 hour
```

Or clear results between test runs:

```bash
docker compose exec redis redis-cli FLUSHDB
```

---

## Memory Considerations

### XLSX Parsing

openpyxl's `read_only` mode streams rows without loading the entire file into memory. For a 400K-row XLSX file:

- Peak memory: ~50MB
- Parse time: 5--8 minutes (openpyxl is pure Python)

For faster ingestion at scale, prefer CSV.

### CSV Parsing

Python's built-in `csv` module is memory-efficient:

- Peak memory: ~10MB for 400K rows (streaming, not buffered)
- Parse time: 10--30 seconds

### MailHog

MailHog stores messages in memory at approximately 5KB per message:

| Messages | Memory |
|---|---|
| 1,000 | ~5MB |
| 10,000 | ~50MB |
| 100,000 | ~500MB |

MailHog is suitable for small-scale validation (up to ~10K emails). For load testing at higher tiers, use the BENCHMARK SMTP profile instead. Do not point load tests at MailHog -- it will exhaust memory and crash.

---

## Monitoring During Tests

Run the resource monitor alongside your benchmark to capture time-series data:

```bash
python3 scripts/monitor_resources.py --interval 5 --output loadtest_resources.csv
```

This captures CPU, memory, disk I/O, and network throughput for all TidePool containers every 5 seconds. The output CSV can be plotted with any spreadsheet tool or with matplotlib:

```bash
python3 scripts/plot_resources.py --input loadtest_resources.csv --output loadtest_report.png
```

Key metrics to watch during a run:

- **Worker CPU**: should be 60--80% per process. Above 90% sustained indicates a bottleneck.
- **PostgreSQL connections**: monitor with `SELECT count(*) FROM pg_stat_activity;`. Should stay below `max_connections`.
- **Redis memory**: monitor with `redis-cli INFO memory`. Watch `used_memory_human`.
- **Celery queue depth**: monitor with `celery -A app.celery_app inspect active_queues`. A growing backlog indicates workers cannot keep up.

---

## Troubleshooting

### Worker Starvation

**Symptom**: Dispatch throughput is well below the throttle rate. Celery queue depth grows continuously.

**Cause**: Too few worker processes relative to the throttle rate and per-email latency.

**Fix**: Scale up workers:
```bash
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d --scale worker=8
```

### Redis Out of Memory

**Symptom**: Workers report `OOM command not allowed when used memory > 'maxmemory'` errors. Tasks fail to enqueue.

**Cause**: Result backend accumulating completed task metadata faster than it expires.

**Fix**:
1. Increase `maxmemory` in the overlay (e.g., 4GB if the host can support it).
2. Set `result_expires = 1800` (30 minutes) in Celery config.
3. Flush the result backend between test runs: `docker compose exec redis redis-cli SELECT 2 && FLUSHDB`.

### PostgreSQL Connection Exhaustion

**Symptom**: Workers crash with `FATAL: too many connections for role "tidepool"` or tasks fail with connection timeout errors.

**Cause**: Total worker processes x pool size exceeds `max_connections`.

**Fix**:
1. Increase `max_connections` in the overlay.
2. Reduce worker concurrency: `--concurrency=4` instead of 8.
3. Deploy PgBouncer between workers and PostgreSQL for connection multiplexing.

### Slow Ingestion

**Symptom**: Address book parsing takes much longer than expected. CPU is low during ingestion.

**Cause**: Disk I/O bottleneck (especially on VMs with virtual disks) or XLSX format overhead.

**Fix**:
1. Use CSV instead of XLSX. CSV parsing is 10--20x faster.
2. Ensure the testdata directory is on fast storage (SSD, not network mount).
3. For XLSX, verify openpyxl is using `read_only=True` mode (check the ingestion code).

### Celery Prefetch Causing Uneven Distribution

**Symptom**: Some workers are idle while others have large prefetch buffers. Task distribution is uneven.

**Cause**: Default prefetch multiplier is too high, causing one worker to hoard tasks.

**Fix**: The load test overlay sets `--prefetch-multiplier=4` and `-O fair`. If distribution is still uneven, reduce to `--prefetch-multiplier=1`.
