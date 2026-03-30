# TidePool -- Deployment Guide

Comprehensive deployment instructions for the TidePool phishing simulation
platform.  Covers development, single-host staging, production (AWS with
Terraform), scaling, monitoring, and operational security.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Production Architecture](#production-architecture)
3. [Terraform Deployment (AWS)](#terraform-deployment-aws)
4. [Staging with Docker Compose](#staging-with-docker-compose)
5. [Configuration Reference](#configuration-reference)
6. [Scaling Guide](#scaling-guide)
7. [Monitoring](#monitoring)
8. [Backup and Recovery](#backup-and-recovery)
9. [Security Checklist](#security-checklist)
10. [Troubleshooting](#troubleshooting)

---

## Development Setup

### Quick start

```bash
git clone <repo-url> TidePool
cd TidePool
cp .env.example .env
```

Generate secrets and paste them into `.env`:

```bash
# SECRET_KEY -- JWT signing key
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# ENCRYPTION_KEY -- Fernet key for SMTP credential encryption at rest
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Leave all other values at their defaults for development.

### Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

This starts seven containers:

| Container | Port | Purpose |
|---|---|---|
| `tidepool-api` | 8000 | FastAPI backend with hot-reload |
| `tidepool-worker` | -- | Celery worker (email dispatch, imports) |
| `tidepool-beat` | -- | Celery beat scheduler |
| `tidepool-postgres` | 5432 | PostgreSQL 16 database |
| `tidepool-redis` | 6379 | Redis 7 (broker, cache, counters) |
| `tidepool-frontend-dev` | 3000 | Vite dev server with HMR |
| `tidepool-mailhog` | 1025/8025 | SMTP sink + web UI |

The `docker-compose.dev.yml` overlay adds:

- Hot-reload for the backend (code mounted as a volume, uvicorn `--reload`)
- Vite HMR for the frontend
- MailHog for email testing (captures all outbound mail)

### Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### Creating the first admin user

There is no default admin account.  Create one with the CLI:

```bash
docker compose exec api python -m app.cli create-admin \
  --username admin \
  --email admin@example.com
```

You will be prompted for a password.

### MailHog for email testing

MailHog captures all outbound email in development.  No emails leave the host.

- **Web UI:** http://localhost:8025 -- view all captured messages
- **SMTP endpoint:** `mailhog:1025` (from within Docker network)

Create an SMTP profile pointing at MailHog:

```bash
curl -s -X POST http://localhost:8000/api/v1/smtp-profiles \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dev MailHog",
    "backend_type": "SMTP",
    "host": "mailhog",
    "port": 1025,
    "use_tls": false,
    "use_ssl": false,
    "from_address": "phishing-test@tidepool.local",
    "from_name": "TidePool Dev"
  }'
```

### Verify the stack

- **Frontend (dashboard):** http://localhost:3000
- **API docs (Swagger):** http://localhost:8000/docs
- **API docs (ReDoc):** http://localhost:8000/redoc
- **Health check:**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

---

## Production Architecture

Production deployments separate the **tracking tier** from the
**dashboard/API tier** so that burst traffic from campaign recipients
cannot degrade the operator experience.

### Architecture diagram

```
                    Recipients                          Operators
                       |                                    |
                 [ DNS: t.domain ]                  [ DNS: app.domain ]
                       |                                    |
               [ Tracking ALB ]                     [ Dashboard ALB ]
               (public, internet)                   (restricted access)
                       |                                    |
            +----------+----------+              +----------+----------+
            |          |          |              |                     |
        [track-1] [track-2] [track-N]       [api-1] [api-2]     [frontend]
            |          |          |              |
            +----------+----------+--------------+
                       |                    |
                 [ Redis Cluster ]    [ PostgreSQL ]
                       |                (primary + replica)
                       |
              [ Celery Workers ]  -->  [ SMTP / SES ]
                  [beat (1x)]
```

### Tier descriptions

**Tracking tier** -- Stateless FastAPI instances behind a public-facing
load balancer.  All recipient traffic (open pixels, click redirects, form
submissions) routes here.  These instances run `tracking_app.py`, a
minimal subset of the full API that exposes only the tracking endpoints.
Horizontally scalable -- add or remove instances based on campaign volume.
Writes events to both Redis (real-time counters) and PostgreSQL (persistent
event log).

**Dashboard/API tier** -- The full FastAPI application behind a separate
load balancer with restricted access (IP allowlist, VPN, or internal
network only).  Serves the admin dashboard, campaign management, reporting,
and all operator-facing API endpoints.  Isolated from the tracking traffic
so that recipient bursts do not affect operator responsiveness.

**Worker tier** -- Celery workers handling email dispatch, address book
imports, bounce processing, and metric aggregation.  No inbound network
traffic.  Scale the number of workers to match campaign sending volume.
A single Celery beat instance runs the periodic task scheduler.

**Data tier** -- Managed PostgreSQL (primary + read replica) and managed
Redis, shared by all application tiers.  Both services live in private
subnets with no public accessibility.

---

## Terraform Deployment (AWS)

### Prerequisites

- AWS account with sufficient IAM permissions (ECS, RDS, ElastiCache, ALB,
  VPC, Route 53, SES, ECR, CloudWatch, Secrets Manager)
- Terraform >= 1.5
- A domain managed in Route 53 (or ability to create DNS records)
- ACM certificate covering both the tracking and dashboard subdomains

### Quick start

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform plan
terraform apply
```

### What gets created

Terraform provisions the following infrastructure:

- **VPC** with public and private subnets across two availability zones
- **Two Application Load Balancers:** one public-facing for the tracking
  tier, one restricted for the dashboard/API tier
- **ECS Fargate services:** tracking, API, frontend, worker, and beat --
  each as a separate ECS service with independent scaling
- **RDS PostgreSQL** (primary instance + optional read replica) in private
  subnets
- **ElastiCache Redis** cluster in private subnets
- **SES** domain identity and DKIM verification (for email sending)
- **ECR repositories** for container images
- **CloudWatch** log groups, dashboard, and metric alarms
- **Secrets Manager** entries for database password, SECRET_KEY, and
  ENCRYPTION_KEY

### Building and pushing container images

After Terraform creates the ECR repositories:

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# Build and push the backend image
docker build -t tidepool-backend ./backend
docker tag tidepool-backend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/tidepool-backend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/tidepool-backend:latest

# Build and push the frontend image
docker build -t tidepool-frontend ./frontend
docker tag tidepool-frontend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/tidepool-frontend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/tidepool-frontend:latest
```

### Post-deploy steps

**Run database migrations** via ECS exec:

```bash
aws ecs execute-command \
  --cluster tidepool \
  --task <api-task-id> \
  --container api \
  --interactive \
  --command "alembic upgrade head"
```

**Create the initial admin user:**

```bash
aws ecs execute-command \
  --cluster tidepool \
  --task <api-task-id> \
  --container api \
  --interactive \
  --command "python -m app.cli create-admin --username admin --email admin@example.com"
```

### Scaling guidance

Adjust these variables in `terraform.tfvars` to control scaling:

| Variable | Default | Description |
|---|---|---|
| `tracking_min_count` | 2 | Minimum tracking tier tasks (ECS desired count floor) |
| `tracking_max_count` | 10 | Maximum tracking tier tasks (auto-scaling ceiling) |
| `tracking_cpu_target` | 60 | CPU utilization percentage target for tracking auto-scaling |
| `api_desired_count` | 2 | Dashboard/API tier task count |
| `worker_desired_count` | 2 | Celery worker task count |
| `beat_desired_count` | 1 | Celery beat (always 1 -- do not increase) |

The tracking tier auto-scales based on ALB request count and CPU
utilization.  During active campaigns, tracking instances scale up
automatically and scale back down during quiet periods.

### Cost optimization

- **NAT gateway:** A single NAT gateway is provisioned by default.  For
  high-availability, enable a second NAT gateway in `terraform.tfvars`
  (doubles NAT cost).
- **Instance sizing:** Fargate task CPU and memory are configurable per
  service.  Start with 0.5 vCPU / 1 GB for tracking tasks and scale up
  only if needed.
- **RDS:** Use `db.t4g.medium` for development/staging.  Switch to
  `db.r6g.large` or larger for production workloads with high event volume.
- **Reserved capacity:** For steady-state deployments, purchase Savings
  Plans for Fargate and RDS Reserved Instances to reduce cost.

---

## Staging with Docker Compose

The `docker-compose.prod.yml` file provides a single-host staging
environment that mirrors the production topology.  This is useful for
integration testing before deploying to AWS.

### Start the staging stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

This runs separate containers for the tracking tier, API tier, frontend,
workers, beat, PostgreSQL, and Redis -- all on one host with nginx routing
traffic by domain name.

### Nginx routing

Nginx listens on ports 80 and 443 and routes requests based on the
`Host` header:

- Requests to the **tracking domain** (e.g., `t.example.com`) are proxied
  to the tracking containers.
- Requests to the **dashboard domain** (e.g., `app.example.com`) are
  proxied to the API and frontend containers.

Set `TRACKING_DOMAIN` and `DASHBOARD_DOMAIN` in your `.env` file to match
your DNS configuration.

### Scaling the tracking tier

```bash
docker compose -f docker-compose.prod.yml up -d --scale tracking=4
```

Nginx automatically load-balances across all tracking container replicas.

---

## Configuration Reference

### Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_PASSWORD` | Yes | `tidepool_dev` | PostgreSQL password |
| `DATABASE_URL` | Yes | (constructed from DB_PASSWORD) | Full async SQLAlchemy connection string |

### Redis

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection for caching and real-time counters |
| `CELERY_BROKER_URL` | Yes | `redis://redis:6379/1` | Celery task broker URL |
| `CELERY_RESULT_BACKEND` | Yes | `redis://redis:6379/2` | Celery result backend URL |

### Auth

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | -- (must be set) | JWT signing key; minimum 32 characters |
| `ENCRYPTION_KEY` | Yes | -- (must be set) | Fernet key for SMTP credential encryption at rest |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | JWT access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | JWT refresh token lifetime in days |
| `MAX_LOGIN_ATTEMPTS` | No | `5` | Failed logins before account lockout |
| `LOGIN_LOCKOUT_MINUTES` | No | `15` | Lockout duration after max failed attempts |

### SMTP

| Variable | Required | Default | Description |
|---|---|---|---|
| `SMTP_HOST` | No | `mailhog` | Default SMTP host (for .env convenience; profiles override) |
| `SMTP_PORT` | No | `1025` | Default SMTP port |
| `SMTP_USERNAME` | No | (empty) | Default SMTP username |
| `SMTP_PASSWORD` | No | (empty) | Default SMTP password |
| `SMTP_USE_TLS` | No | `false` | Default SMTP TLS setting |
| `SMTP_FROM_ADDRESS` | No | `noreply@tidepool.local` | Default sender address |

### Application

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEBUG` | No | `false` | Enable debug mode (verbose SQL logging, detailed errors) |
| `LOG_LEVEL` | No | `info` | Logging level: debug, info, warning, error |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | JSON list of allowed CORS origins |
| `RATE_LIMIT_DEFAULT` | No | `100/minute` | Default API rate limit |
| `RATE_LIMIT_TRACKING` | No | `300/minute` | Rate limit for tracking endpoints |
| `RATE_LIMIT_AUTH` | No | `10/minute` | Rate limit for authentication endpoints |
| `MAX_UPLOAD_SIZE_MB` | No | `50` | Maximum file upload size in MB |
| `ALLOWED_UPLOAD_EXTENSIONS` | No | `.xlsx,.xls,.csv` | Allowed address book file types |

### Domain Routing (Production / Staging)

| Variable | Required | Default | Description |
|---|---|---|---|
| `TRACKING_DOMAIN` | Production | -- | Domain for tracking tier (e.g., `t.example.com`). Used by nginx and ALB routing. |
| `DASHBOARD_DOMAIN` | Production | -- | Domain for dashboard/API tier (e.g., `app.example.com`). Used by nginx and ALB routing. |

### Header Signing

| Variable | Required | Default | Description |
|---|---|---|---|
| `HEADER_SIGNING_KEY` | No | (empty) | HMAC key for signing custom headers on outbound emails |

### Agent / AI

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | No | (empty) | API key for AI-assisted template generation (optional feature) |

---

## Scaling Guide

### Tracking tier

The tracking tier is stateless and horizontally scalable.  In AWS, it
auto-scales based on ALB request count and CPU utilization.  Each tracking
instance handles open pixels, click redirects, and form submissions
independently -- there is no shared state beyond Redis and PostgreSQL.

To handle campaign bursts, increase `tracking_max_count` in Terraform.
For Docker Compose staging, use `--scale tracking=N`.

### Worker tier

Scale Celery workers to match email dispatch volume.  Each worker runs
with a default concurrency of 4 threads.

**Guideline formula:**

```
desired_workers = peak_emails_per_minute / (concurrency * 60)
```

For example, if you need to sustain 1,000 emails per minute with
concurrency of 4:

```
desired_workers = 1000 / (4 * 60) = ~5 workers
```

In Docker Compose:

```bash
docker compose up -d --scale worker=N
```

In Terraform, adjust `worker_desired_count`.

### Database scaling

**Vertical scaling:** Increase the RDS instance class for write-heavy
workloads (large campaigns generating many tracking events
simultaneously).

**Read replicas:** Add an RDS read replica and point dashboard/reporting
queries at it to offload the primary.  Tracking writes always go to the
primary instance.

### PostgreSQL tuning

For production deployments with high event volume, tune these parameters:

```yaml
# docker-compose.yml postgres service (or RDS parameter group)
shared_buffers: 1GB
work_mem: 64MB
max_connections: 200
effective_cache_size: 3GB
maintenance_work_mem: 256MB
random_page_cost: 1.1
```

### Redis scaling

Monitor Redis memory usage.  If `used_memory` approaches `maxmemory`,
either increase the ElastiCache node size or configure memory limits:

```bash
# For Docker Compose deployments
command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

If `instantaneous_ops_per_sec` is consistently high under campaign load,
consider upgrading to a larger ElastiCache node type or enabling Redis
Cluster mode.

---

## Monitoring

### Health endpoint

```bash
curl -s https://app.example.com/health | python3 -m json.tool
```

Returns JSON with service status.  Use this for load balancer health checks
and uptime monitoring.  The tracking tier exposes the same `/health`
endpoint independently.

### CloudWatch dashboard (AWS)

Terraform creates a CloudWatch dashboard with panels for:

- ECS task count per service (tracking, API, worker)
- ALB request count and latency (tracking ALB and dashboard ALB)
- RDS CPU, connections, and IOPS
- ElastiCache memory usage and evictions
- Celery queue depth (via custom metric)

### Key metrics to watch

| Metric | Source | Warning threshold | Critical threshold |
|---|---|---|---|
| Tracking ALB latency (p99) | CloudWatch | > 500ms | > 2s |
| Tracking ALB 5xx rate | CloudWatch | > 1% | > 5% |
| ECS tracking task CPU | CloudWatch | > 70% sustained | > 90% sustained |
| Redis memory utilization | ElastiCache | > 70% | > 85% |
| RDS CPU utilization | CloudWatch | > 70% sustained | > 85% sustained |
| RDS free storage | CloudWatch | < 20% | < 10% |
| Celery queue depth | Custom metric | > 1000 tasks | > 5000 tasks |
| Campaign bounce rate | Application | > 3% | > 5% (auto-pause) |

### Alert configuration

Terraform configures SNS-based alerts for critical thresholds.  Set the
`alert_email` variable in `terraform.tfvars` to receive notifications.

### Celery Flower for task monitoring

Add Flower to your compose stack for detailed task visibility:

```yaml
# Append to docker-compose.yml services:
flower:
  build:
    context: ./backend
    dockerfile: Dockerfile
  container_name: tidepool-flower
  command: celery -A app.celery_app flower --port=5555 --basic_auth=admin:changeme
  env_file:
    - .env
  environment:
    - CELERY_BROKER_URL=redis://redis:6379/1
  ports:
    - "5555:5555"
  depends_on:
    - redis
  restart: unless-stopped
  networks:
    - tidepool
```

Access at http://localhost:5555.  Flower provides active/completed task
counts, worker status, execution time histograms, and failed task details.

### PostgreSQL monitoring queries

**Active connections:**

```sql
SELECT count(*) AS active, state
FROM pg_stat_activity
WHERE datname = 'tidepool'
GROUP BY state;
```

**Table sizes:**

```sql
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       pg_size_pretty(pg_relation_size(relid)) AS data_size,
       pg_size_pretty(pg_indexes_size(relid)) AS index_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

**Slow queries (requires `pg_stat_statements` extension):**

```sql
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;
```

### Redis memory monitoring

```bash
# Current memory usage
docker compose exec redis redis-cli INFO memory | grep used_memory_human

# Key count by prefix
docker compose exec redis redis-cli --scan --pattern "tidepool:*" | \
  sed 's/:[^:]*$//' | sort | uniq -c | sort -rn
```

---

## Backup and Recovery

### PostgreSQL backup

**Automated daily backup (Docker Compose):**

```bash
# /etc/cron.d/tidepool-backup
0 1 * * * root docker compose -f /path/to/TidePool/docker-compose.yml \
  exec -T postgres pg_dump -U tidepool -d tidepool \
  | gzip > /backups/tidepool-$(date +\%Y\%m\%d).sql.gz 2>/dev/null
```

**Manual backup:**

```bash
docker compose exec -T postgres pg_dump -U tidepool -d tidepool \
  | gzip > tidepool-backup-$(date +%Y%m%d-%H%M%S).sql.gz
```

**Restore:**

```bash
gunzip -c tidepool-backup-20260327.sql.gz | \
  docker compose exec -T postgres psql -U tidepool -d tidepool
```

**RDS automated backups (AWS):** Terraform configures RDS with automated
daily backups and a configurable retention period (default: 7 days).
Point-in-time recovery is available within the retention window.

### Redis snapshot schedule

**Docker Compose:** Redis is configured with default RDB persistence.  For
explicit control, add snapshot settings:

```bash
command: redis-server --save 900 1 --save 300 10 --save 60 10000
```

**AWS ElastiCache:** Terraform configures automatic daily snapshots with
a configurable retention period.  Manual snapshots can be created via the
AWS console or CLI before maintenance operations.

### ECS task definition versioning

Every ECS deployment creates a new task definition revision.  To roll back
to a previous version:

```bash
# List recent revisions
aws ecs list-task-definitions --family tidepool-api --sort DESC --max-items 5

# Update service to use a previous revision
aws ecs update-service \
  --cluster tidepool \
  --service tidepool-api \
  --task-definition tidepool-api:<previous-revision>
```

### Evidence and report files

Back up the Docker volumes and any report/upload directories:

```bash
# Back up Docker volumes
docker run --rm -v tidepool_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-volume-$(date +%Y%m%d).tar.gz /data

# Back up upload directory (if mounted)
tar czf uploads-$(date +%Y%m%d).tar.gz /var/lib/tidepool/uploads/
```

### Retention policy

| Data | Suggested retention | Notes |
|---|---|---|
| Campaign data | Per organizational policy | Retain as needed for reporting |
| Tracking events | 1 year | Aggregate before purging |
| Audit logs | Per organizational policy | Compliance / forensic value |
| PDF reports | Indefinite | Generated artifacts, small footprint |
| Redis counters | 7 days (auto-expire) | Real-time only; rolled up to PostgreSQL |

---

## Security Checklist

Before exposing TidePool to any network beyond localhost, verify every item:

- [ ] **Change all default secrets.**  `SECRET_KEY`, `ENCRYPTION_KEY`, and
      `DB_PASSWORD` must all be unique, random, production-strength values.
      The application refuses to start if `SECRET_KEY` is the placeholder
      value or shorter than 32 characters.

- [ ] **Tracking ALB is public; dashboard ALB is restricted.**  The
      tracking tier load balancer must be internet-accessible (recipients
      need to reach it).  The dashboard/API load balancer should be
      restricted to operator IP ranges, VPN, or internal network only.

- [ ] **All inter-service traffic stays in private subnets.**  ECS tasks,
      RDS, and ElastiCache communicate over private subnets.  No
      application container should have a public IP.

- [ ] **Database and Redis are not publicly accessible.**  RDS and
      ElastiCache security groups allow inbound connections only from
      application subnets.

- [ ] **Container images scanned for vulnerabilities.**  Integrate ECR
      image scanning or a third-party scanner (Trivy, Grype) into your
      CI/CD pipeline.  Do not deploy images with critical CVEs.

- [ ] **Secrets in AWS Secrets Manager, not environment variables.**
      Database passwords, SECRET_KEY, and ENCRYPTION_KEY should be stored
      in Secrets Manager and injected into ECS task definitions via
      `valueFrom`.  Do not hardcode secrets in task definitions or
      Terraform state.

- [ ] **Restrict network access (Docker Compose).**  Only the reverse
      proxy (nginx) should be reachable from the network.  Backend ports
      (8000, 5432, 6379) should be bound to 127.0.0.1 or firewalled:
      ```yaml
      # docker-compose.yml -- bind to localhost only
      ports:
        - "127.0.0.1:8000:8000"
      ```

- [ ] **Enable TLS everywhere.**  Terminate TLS at the load balancer or
      reverse proxy.  Set `SMTP_USE_TLS=true` or `SMTP_USE_SSL=true` for
      outbound mail.  Use `CORS_ORIGINS` with HTTPS URLs only.

- [ ] **Review CORS origins.**  Set `CORS_ORIGINS` to the exact production
      frontend URL(s).  Do not use wildcards.

- [ ] **Encrypt database backups.**  Pipe `pg_dump` output through GPG or
      use encrypted storage:
      ```bash
      pg_dump ... | gpg --encrypt --recipient backup@yourcompany.com \
        > tidepool-backup.sql.gz.gpg
      ```

- [ ] **API key rotation schedule.**  Establish a rotation cadence (e.g.,
      every 90 days).  API keys support expiration via `expires_in_days`.

- [ ] **Audit log review process.**  Schedule regular review of the audit
      log via the `/api/v1/audit` endpoint or direct database queries.
      All state-changing API calls (POST, PUT, DELETE) are logged with
      actor, resource, and IP address.

- [ ] **Disable debug mode.**  Ensure `DEBUG=false` in production.  Debug
      mode enables verbose SQL logging and detailed error responses.

- [ ] **Rate limiting is active.**  The application enforces three tiers:
      - Auth endpoints: 10/minute
      - Tracking endpoints: 300/minute
      - All other endpoints: 100/minute

- [ ] **Account lockout is configured.**  After 5 failed login attempts,
      accounts are locked for 15 minutes.

- [ ] **File upload restrictions.**  Only `.xlsx`, `.xls`, and `.csv` files
      are accepted.  Maximum upload size is 50 MB.  Multipart requests
      are capped at 50 MB; all other request bodies at 1 MB.

- [ ] **Credential harvester data handling.**  TidePool records only
      submitted field *names*, never field *values*.  Verify this behavior
      in your deployment by reviewing tracking event metadata.

- [ ] **Docker runs as non-root.**  The backend Dockerfile creates and
      switches to `appuser`.  Verify with:
      ```bash
      docker compose exec api whoami
      # Expected output: appuser
      ```

---

## Troubleshooting

### Migrations fail

**Symptom:** `alembic upgrade head` exits with an error.

**Causes and fixes:**

1. **Database not ready:** Wait for the healthcheck to pass before running
   migrations.  Use `docker compose exec api alembic upgrade head` (the
   `depends_on` condition ensures PostgreSQL is healthy).

2. **Conflicting migration heads:** Run `alembic heads` to check.  If
   multiple heads exist, create a merge migration:
   ```bash
   docker compose exec api alembic merge heads -m "merge"
   ```

3. **Connection refused:** Verify `DATABASE_URL` matches the PostgreSQL
   container's hostname and credentials.

### Worker not processing tasks

**Symptom:** Campaigns stay in SCHEDULED or RUNNING state; no emails sent.

**Checks:**

```bash
# Verify worker is running
docker compose ps worker

# Check worker logs
docker compose logs --tail=100 worker

# Verify Redis connectivity from the worker
docker compose exec worker python -c "
import redis; r = redis.from_url('redis://redis:6379/1'); print(r.ping())
"

# Check Celery task queue depth
docker compose exec redis redis-cli LLEN celery
```

### Emails not sending

**Symptom:** Tasks complete but emails are not received.

**Checks:**

1. **In development:** Check MailHog at http://localhost:8025.
2. **In production:** Verify SMTP profile credentials:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/smtp-profiles/{id}/test \
     -H "Authorization: Bearer $TOKEN"
   ```
3. Check worker logs for SMTP errors:
   ```bash
   docker compose logs worker | grep -i "smtp\|send.*failed"
   ```

### Bounce rate too high (campaign auto-paused)

**Symptom:** Campaign status changes to PAUSED unexpectedly.

TidePool auto-pauses campaigns when the bounce rate exceeds 5% (after at
least 100 emails sent).  This protects sender reputation.

**Resolution:**

1. Check bounce breakdown in the campaign monitoring endpoint.
2. Clean the address book -- remove invalid addresses flagged with
   `is_valid_email = false`.
3. Resume the campaign after cleaning:
   ```bash
   curl -s -X POST http://localhost:8000/api/v1/campaigns/{id}/resume \
     -H "Authorization: Bearer $TOKEN"
   ```

### Tracking tier at max scale

**Symptom:** Tracking ALB returns 503 errors or latency spikes during
active campaigns.

**Causes and fixes:**

1. **Auto-scaling ceiling reached:** Increase `tracking_max_count` in
   Terraform and re-apply.  The tracking tier is stateless, so adding
   more instances has no coordination overhead.

2. **Database connection exhaustion:** Each tracking instance opens
   connections to PostgreSQL.  Verify `max_connections` on RDS can
   accommodate `tracking_max_count * connections_per_task`.  Consider
   using PgBouncer or RDS Proxy for connection pooling.

3. **Rate limiting too aggressive:** If legitimate tracking requests are
   being rate-limited, increase `RATE_LIMIT_TRACKING` or remove the
   per-IP limit for the tracking tier (recipients share corporate
   egress IPs).

### Redis memory exhaustion during burst

**Symptom:** Redis returns OOM errors or evicts keys unexpectedly during
large campaign sends.

**Causes and fixes:**

1. **Insufficient maxmemory:** Increase the Redis instance size or raise
   `maxmemory`.  Monitor `used_memory` relative to `maxmemory` during
   campaign peaks.

2. **Event feed unbounded growth:** The `tidepool:feed:{campaign_id}`
   lists grow with every tracking event.  Verify that the feed trimming
   logic (LTRIM) is running.  If feeds are excessively large, trim
   manually:
   ```bash
   redis-cli LTRIM tidepool:feed:<campaign_id> -1000 -1
   ```

3. **Celery result backend accumulation:** Completed task results in
   Redis db2 may accumulate.  Set `result_expires` in Celery config to
   auto-expire old results (default: 24 hours).

### Log locations

| Service | How to access |
|---|---|
| API | `docker compose logs api` |
| Worker | `docker compose logs worker` |
| Beat scheduler | `docker compose logs beat` |
| Tracking | `docker compose logs tracking` |
| PostgreSQL | `docker compose logs postgres` |
| Redis | `docker compose logs redis` |
| Frontend | `docker compose logs frontend` |

Add `--tail=N` for the last N lines, `--follow` for streaming.

In AWS, all container logs are available in CloudWatch Logs under the
`/ecs/tidepool` log group prefix.

### Restart individual services

```bash
# Docker Compose
docker compose restart api
docker compose restart worker
docker compose restart beat
docker compose restart tracking

# ECS (force new deployment)
aws ecs update-service --cluster tidepool --service tidepool-api --force-new-deployment
```

### Set up log rotation (Docker Compose)

Add to `/etc/logrotate.d/tidepool`:

```
/var/log/tidepool/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
```

For Docker-managed logs:

```bash
# In /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "5"
  }
}
```
