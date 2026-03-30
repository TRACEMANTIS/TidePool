# TidePool -- Deployment Guide

Comprehensive deployment instructions for the TidePool enterprise phishing
simulation platform.  Covers development, production, scaling, monitoring,
and operational security.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (Development)](#quick-start-development)
3. [Production Deployment](#production-deployment)
4. [Environment Variable Reference](#environment-variable-reference)
5. [Scaling](#scaling)
6. [Monitoring](#monitoring)
7. [Backup and Recovery](#backup-and-recovery)
8. [Troubleshooting](#troubleshooting)
9. [Security Checklist](#security-checklist)

---

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| Docker Engine | 24+ | 27+ |
| Docker Compose | v2.20+ | v2.30+ |
| RAM | 4 GB | 8 GB (for large recipient campaigns) |
| Disk | 20 GB | 50 GB+ (large address books, PDF reports, evidence retention) |
| CPU | 2 cores | 4+ cores (scales with worker count) |

**Additional requirements:**

- An SMTP relay or transactional email service account (one of):
  - Direct SMTP/SMTPS relay
  - AWS SES (with IAM credentials or instance role)
  - Mailgun (API key + verified domain)
  - SendGrid (API key)
- DNS records if using a custom tracking domain (A record + optional SPF/DKIM)
- TLS certificate for production (Let's Encrypt, commercial CA, or internal PKI)

---

## Quick Start (Development)

This section gets a local development stack running from a clean checkout.

### 1. Clone the repository

```bash
git clone <repo-url> TidePool
cd TidePool
```

### 2. Create the environment file

```bash
cp .env.example .env
```

### 3. Generate secrets

Generate a 64-character random `SECRET_KEY` (used for JWT signing):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate a Fernet `ENCRYPTION_KEY` (used for SMTP credential encryption at rest):

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Open `.env` and set both values:

```
SECRET_KEY=<paste SECRET_KEY output here>
ENCRYPTION_KEY=<paste ENCRYPTION_KEY output here>
```

Leave all other values at their defaults for development.

### 4. Start the stack

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

### 5. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 6. Create the initial admin user

There is no default admin account.  Create one with the CLI:

```bash
docker compose exec api python -m app.cli create-admin \
  --username admin \
  --email admin@example.com
```

You will be prompted for a password.  Alternatively, insert directly via SQL
(useful in CI/automated setups):

```bash
docker compose exec postgres psql -U tidepool -d tidepool -c "
  INSERT INTO users (username, email, hashed_password, is_active, is_admin, failed_login_attempts)
  VALUES (
    'admin',
    'admin@example.com',
    '\$(python3 -c \"from passlib.hash import bcrypt; print(bcrypt.hash('changeme'))\")',
    true,
    true,
    0
  );
"
```

### 7. Verify the stack

- **Frontend (dashboard):** http://localhost:3000
- **API docs (Swagger):** http://localhost:8000/docs
- **API docs (ReDoc):** http://localhost:8000/redoc
- **MailHog UI:** http://localhost:8025 -- all test emails land here
- **Health check:**

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

### 8. Configure a development SMTP profile

Point at MailHog (already running on the dev compose override):

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

---

## Production Deployment

### 1. Generate production secrets

```bash
# SECRET_KEY -- 64+ character random string for JWT signing
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# ENCRYPTION_KEY -- Fernet key for SMTP credential encryption at rest
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# DB_PASSWORD -- strong database password
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Configure `.env` for production

```bash
cp .env.example .env
```

Edit `.env` with production values:

```ini
# -- Database --
DB_PASSWORD=<generated-db-password>
DATABASE_URL=postgresql+asyncpg://tidepool:${DB_PASSWORD}@postgres:5432/tidepool

# -- Redis --
REDIS_URL=redis://redis:6379/0

# -- Celery --
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# -- Application --
SECRET_KEY=<generated-secret-key>
ENCRYPTION_KEY=<generated-fernet-key>
DEBUG=false
LOG_LEVEL=info
CORS_ORIGINS=["https://phishing.yourcompany.com"]
```

### 3. TLS termination with nginx reverse proxy

Place an nginx reverse proxy in front of the stack.  Example configuration:

```nginx
upstream tidepool_api {
    server 127.0.0.1:8000;
}

upstream tidepool_frontend {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name phishing.yourcompany.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name phishing.yourcompany.com;

    ssl_certificate     /etc/ssl/certs/tidepool.crt;
    ssl_certificate_key /etc/ssl/private/tidepool.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Security headers (supplement application-level headers)
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # API routes
    location /api/ {
        proxy_pass http://tidepool_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 50m;
    }

    # Health endpoint
    location /health {
        proxy_pass http://tidepool_api;
        proxy_set_header Host $host;
    }

    # OpenAPI docs
    location /docs {
        proxy_pass http://tidepool_api;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://tidepool_api;
        proxy_set_header Host $host;
    }

    # Frontend (SPA)
    location / {
        proxy_pass http://tidepool_frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. Start the production stack

```bash
docker compose up -d
```

Do NOT include the dev compose override in production.

### 5. Run migrations

```bash
docker compose exec api alembic upgrade head
```

### 6. Create admin user

```bash
docker compose exec api python -m app.cli create-admin \
  --username admin \
  --email admin@yourcompany.com
```

### 7. Configure SMTP profiles via API

Obtain a JWT first:

```bash
TOKEN=$(curl -s -X POST https://phishing.yourcompany.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**Direct SMTP relay:**

```bash
curl -s -X POST https://phishing.yourcompany.com/api/v1/smtp-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Corporate SMTP Relay",
    "backend_type": "SMTP",
    "host": "smtp.yourcompany.com",
    "port": 587,
    "username": "phishing-svc@yourcompany.com",
    "password": "smtp-password",
    "use_tls": true,
    "use_ssl": false,
    "from_address": "security-awareness@yourcompany.com",
    "from_name": "IT Security Team"
  }'
```

**AWS SES:**

```bash
curl -s -X POST https://phishing.yourcompany.com/api/v1/smtp-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AWS SES",
    "backend_type": "SES",
    "from_address": "noreply@yourcompany.com",
    "from_name": "Security Awareness",
    "config": {
      "region": "us-east-1",
      "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
      "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    }
  }'
```

**Mailgun:**

```bash
curl -s -X POST https://phishing.yourcompany.com/api/v1/smtp-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mailgun",
    "backend_type": "MAILGUN",
    "from_address": "phishing@mg.yourcompany.com",
    "from_name": "Security Team",
    "config": {
      "api_key": "key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "domain": "mg.yourcompany.com"
    }
  }'
```

**SendGrid:**

```bash
curl -s -X POST https://phishing.yourcompany.com/api/v1/smtp-profiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SendGrid",
    "backend_type": "SENDGRID",
    "from_address": "phishing@yourcompany.com",
    "from_name": "Security Team",
    "config": {
      "api_key": "SG.xxxxxxxxxxxxxxxxxxxx.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    }
  }'
```

### 8. Verify health

```bash
curl -s https://phishing.yourcompany.com/health | python3 -m json.tool
```

### 9. Set up log rotation

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

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_PASSWORD` | Yes | `tidepool_dev` | PostgreSQL password |
| `DATABASE_URL` | Yes | (constructed from DB_PASSWORD) | Full async SQLAlchemy connection string |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis connection for caching and real-time counters |
| `CELERY_BROKER_URL` | Yes | `redis://redis:6379/1` | Celery task broker URL |
| `CELERY_RESULT_BACKEND` | Yes | `redis://redis:6379/2` | Celery result backend URL |
| `SECRET_KEY` | Yes | -- (must be set) | JWT signing key; minimum 32 characters |
| `ENCRYPTION_KEY` | Yes | -- (must be set) | Fernet key for SMTP credential encryption at rest |
| `DEBUG` | No | `false` | Enable debug mode (verbose SQL logging, detailed errors) |
| `LOG_LEVEL` | No | `info` | Logging level: debug, info, warning, error |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | JSON list of allowed CORS origins |
| `SMTP_HOST` | No | `mailhog` | Default SMTP host (for .env convenience; profiles override) |
| `SMTP_PORT` | No | `1025` | Default SMTP port |
| `SMTP_USERNAME` | No | (empty) | Default SMTP username |
| `SMTP_PASSWORD` | No | (empty) | Default SMTP password |
| `SMTP_USE_TLS` | No | `false` | Default SMTP TLS setting |
| `SMTP_FROM_ADDRESS` | No | `noreply@tidepool.local` | Default sender address |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | JWT access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | JWT refresh token lifetime in days |
| `RATE_LIMIT_DEFAULT` | No | `100/minute` | Default API rate limit |
| `RATE_LIMIT_TRACKING` | No | `300/minute` | Rate limit for tracking endpoints |
| `RATE_LIMIT_AUTH` | No | `10/minute` | Rate limit for authentication endpoints |
| `MAX_LOGIN_ATTEMPTS` | No | `5` | Failed logins before account lockout |
| `LOGIN_LOCKOUT_MINUTES` | No | `15` | Lockout duration after max failed attempts |
| `MAX_UPLOAD_SIZE_MB` | No | `50` | Maximum file upload size in MB |
| `ALLOWED_UPLOAD_EXTENSIONS` | No | `.xlsx,.xls,.csv` | Allowed address book file types |

---

## Scaling

### Worker scaling

Scale Celery workers to increase email dispatch throughput:

```bash
docker compose up -d --scale worker=N
```

**Guideline:** 1 worker (4 concurrency threads each) per 50,000 emails/day.

| Daily volume | Workers | Total concurrency |
|---|---|---|
| Up to 50K | 1 | 4 |
| 50K - 200K | 2-4 | 8-16 |
| 200K+ | 4-8+ | 16-32+ |

### Redis as bottleneck indicator

Monitor Redis memory and command latency.  If `INFO` shows:

- `used_memory` approaching `maxmemory` -- increase Redis memory or add a
  dedicated Redis instance for the Celery broker
- `instantaneous_ops_per_sec` consistently above 50K -- consider Redis Cluster

```bash
docker compose exec redis redis-cli INFO memory
docker compose exec redis redis-cli INFO stats | grep instantaneous_ops_per_sec
```

### Redis memory configuration

For large campaigns, set explicit memory limits:

```bash
# In docker-compose.yml, under the redis service:
command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

### PostgreSQL tuning

For production with large datasets (high contact counts, millions of tracking
events), tune these parameters in a custom `postgresql.conf` or via
environment variables:

```yaml
# docker-compose.yml postgres service
environment:
  POSTGRES_DB: tidepool
  POSTGRES_USER: tidepool
  POSTGRES_PASSWORD: ${DB_PASSWORD}
command:
  - "postgres"
  - "-c"
  - "shared_buffers=1GB"
  - "-c"
  - "work_mem=64MB"
  - "-c"
  - "max_connections=200"
  - "-c"
  - "effective_cache_size=3GB"
  - "-c"
  - "maintenance_work_mem=256MB"
  - "-c"
  - "random_page_cost=1.1"
```

---

## Monitoring

### Health endpoint

```bash
curl -s http://localhost:8000/health
```

Returns JSON with service status.  Use this for load balancer health checks
and uptime monitoring.

### Celery Flower for task monitoring

Add Flower to your compose stack:

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

Access at http://localhost:5555.  Flower provides:

- Active/reserved/completed task counts
- Worker status and resource usage
- Task execution time histograms
- Failed task details and stack traces

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

**Daily automated backup via cron:**

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
| Campaign data | 2 years | Compliance reporting needs |
| Tracking events | 1 year | Aggregate before purging |
| Audit logs | 3 years | Compliance / forensic value |
| PDF reports | Indefinite | Generated artifacts, small footprint |
| Redis counters | 7 days (auto-expire) | Real-time only; rolled up to PostgreSQL |

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

### Log locations

| Service | How to access |
|---|---|
| API | `docker compose logs api` |
| Worker | `docker compose logs worker` |
| Beat scheduler | `docker compose logs beat` |
| PostgreSQL | `docker compose logs postgres` |
| Redis | `docker compose logs redis` |
| Frontend | `docker compose logs frontend` |

Add `--tail=N` for the last N lines, `--follow` for streaming.

### Restart individual services

```bash
docker compose restart api
docker compose restart worker
docker compose restart beat
```

---

## Security Checklist

Before exposing TidePool to any network beyond localhost, verify every item:

- [ ] **Change all default secrets.**  `SECRET_KEY`, `ENCRYPTION_KEY`, and
      `DB_PASSWORD` must all be unique, random, production-strength values.
      The application refuses to start if `SECRET_KEY` is the placeholder
      value or shorter than 32 characters.

- [ ] **Restrict network access.**  Only the reverse proxy (nginx) should be
      reachable from the network.  Backend ports (8000, 5432, 6379) should
      be bound to 127.0.0.1 or firewalled:
      ```yaml
      # docker-compose.yml -- bind to localhost only
      ports:
        - "127.0.0.1:8000:8000"
      ```

- [ ] **Enable TLS everywhere.**  Terminate TLS at the reverse proxy.
      Set `SMTP_USE_TLS=true` or `SMTP_USE_SSL=true` for outbound mail.
      Use `CORS_ORIGINS` with HTTPS URLs only.

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
