# TidePool -- Architecture Documentation

Technical architecture reference for the TidePool enterprise phishing
simulation platform.  This document covers the full system: services,
data flows, database schema, API design, security model, email engine,
reporting pipeline, and frontend architecture.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Deployment Topology](#deployment-topology)
4. [Data Flow](#data-flow)
5. [Database Schema](#database-schema)
6. [API Architecture](#api-architecture)
7. [Security Architecture](#security-architecture)
8. [Frontend Architecture](#frontend-architecture)
9. [Email Engine](#email-engine)
10. [Reporting Pipeline](#reporting-pipeline)

---

## System Overview

```
                    Recipients                          Operators
                       |                                    |
                 [ DNS: t.domain ]                  [ DNS: app.domain ]
                       |                                    |
               [ Tracking LB ]                      [ Dashboard LB ]
               (public, internet)                   (restricted access)
                       |                                    |
            +----------+----------+              +----------+----------+
            |          |          |              |                     |
        [track-1] [track-2] [track-N]       [ FastAPI ]          [ Frontend SPA ]
        tracking_app.py (stateless)         uvicorn x4           React 19 + Vite
            |          |          |         port 8000             port 3000 (dev)
            +----------+----------+---------+                    port 80 (prod/nginx)
                       |                    |
                       |     +--------------+-----------------+
                       |     |              |                  |
                       | [ Celery       [ Celery          [ Redis 7 ]
                       |   Worker ]       Beat ]           3 databases:
                       |   x4 conc.      scheduler         db0: cache/counters
                       |      |              |              db1: broker
                       |      |              |              db2: results
                       |      +------+-------+
                       |             |
                       +------+------+
                              |
                       [ PostgreSQL 16 ]
                        tidepool database

                    +-------------------+-------------------+
                    |                   |                   |
              [ SMTP Relay ]      [ AWS SES ]      [ Mailgun / SendGrid ]
                    |                   |                   |
                    +-------------------+-------------------+
                                        |
                                   RECIPIENT INBOX
                                        |
                                   opens / clicks
                                        |
                              [ Tracking Tier ]
                              /api/v1/tracking/*
                              (dedicated instances)
                                        |
                                +-------+-------+
                                |               |
                           [ Redis ]     [ PostgreSQL ]
                           real-time     persistent
                           counters      events
```

### Component Descriptions

| Component | Container | Purpose |
|---|---|---|
| **API** | `tidepool-api` | FastAPI application serving the REST API (4 uvicorn workers). Handles authentication, CRUD, tracking pixel/link endpoints, and report generation. |
| **Worker** | `tidepool-worker` | Celery worker processing async tasks: email dispatch, address book imports, bounce processing, metric aggregation. Default concurrency: 4. |
| **Beat** | `tidepool-beat` | Celery beat scheduler running periodic tasks: campaign launch checks (60s), progress monitoring (120s), daily cleanup (02:00 UTC), metric aggregation (03:00 UTC). |
| **PostgreSQL** | `tidepool-postgres` | Primary data store for all persistent state: users, campaigns, contacts, templates, tracking events, audit logs, report snapshots. |
| **Redis** | `tidepool-redis` | Three logical databases. db0: real-time tracking counters and event feeds. db1: Celery task broker. db2: Celery result backend. Also hosts token-bucket state for email throttling. |
| **Frontend** | `tidepool-frontend` | React 19 SPA built with Vite, served via nginx in production. Communicates exclusively through the REST API. nginx proxies `/api/*` to the API container. |
| **MailHog** | `tidepool-mailhog` (dev only) | SMTP sink that captures all outbound email during development. Web UI on port 8025. |

---

## Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Runtime** | Python | 3.13 | Backend language |
| **Web framework** | FastAPI | 0.115+ | Async REST API with OpenAPI docs |
| **ASGI server** | Uvicorn | 0.34+ | Production ASGI server (4 workers) |
| **ORM** | SQLAlchemy | 2.0+ | Async ORM with mapped_column declarative style |
| **Migrations** | Alembic | 1.14+ | Database schema versioning |
| **Database** | PostgreSQL | 16 (Alpine) | Primary persistent store |
| **Cache / broker** | Redis | 7 (Alpine) | Task broker, result backend, real-time counters, throttle state |
| **Task queue** | Celery | 5.4+ | Distributed task execution |
| **Auth (JWT)** | python-jose | 3.3+ | JWT creation and verification |
| **Auth (passwords)** | passlib + bcrypt | 1.7+ | Password hashing |
| **Encryption** | cryptography (Fernet) | 42+ | Field-level encryption for SMTP credentials |
| **Email sending** | aiosmtplib | 3.0+ | Async SMTP client |
| **HTTP client** | httpx | 0.28+ | Async HTTP for Mailgun/SendGrid API calls |
| **Rate limiting** | slowapi | 0.1.9+ | API request rate limiting |
| **Input sanitization** | bleach | 6.0+ | HTML sanitization |
| **PDF generation** | WeasyPrint | 63+ | Executive report PDF rendering |
| **Spreadsheet** | openpyxl | 3.1+ | Excel address book parsing |
| **HTML parsing** | BeautifulSoup4 + lxml | 4.12+ / 5.0+ | Landing page cloning |
| **Templating** | Jinja2 | 3.1+ | Email template rendering |
| **Frontend framework** | React | 19 | UI component framework |
| **Build tool** | Vite | 6.2+ | Frontend bundler with HMR |
| **Styling** | Tailwind CSS | 4.1+ | Utility-first CSS |
| **State management** | Zustand | 5.0+ | Lightweight client state |
| **Data fetching** | TanStack React Query | 5.67+ | Server state, caching, refetching |
| **Routing** | React Router | 7.4+ | Client-side routing |
| **Charts** | Recharts | 2.15+ | Campaign analytics charts |
| **Page builder** | GrapesJS | 0.21+ | Visual landing page editor |
| **Prod web server** | nginx | Alpine | Static file serving, reverse proxy, tracking/dashboard domain routing |
| **Containerization** | Docker + Compose | v2 | Local development and staging orchestration |
| **Infrastructure** | Terraform | 1.5+ | AWS infrastructure provisioning (VPC, ECS, RDS, ElastiCache, ALB) |
| **Container orchestration** | ECS Fargate | -- | Production container orchestration (serverless, per-tier scaling) |

---

## Deployment Topology

In production, TidePool separates into distinct tiers to isolate
recipient-facing tracking traffic from operator-facing dashboard traffic.

### Why the split exists

During active campaigns, tracking endpoints receive burst traffic as
recipients open emails and click links.  If tracking and dashboard share
the same application instances, a traffic spike from a large campaign can
degrade the operator experience -- slow dashboard loads, delayed report
generation, or API timeouts.  Separating the tiers ensures that:

- Operators always have a responsive dashboard regardless of campaign load.
- The tracking tier can scale independently (it is stateless and
  horizontally scalable).
- Security posture improves: the tracking load balancer is public-facing,
  while the dashboard load balancer is access-restricted.

### Tier communication

All tiers share the same PostgreSQL database and Redis instance.  There
is no direct service-to-service communication between tiers.

- **Tracking tier** writes events to PostgreSQL (`tracking_events` table)
  and pushes real-time counters to Redis.  It reads only the
  `campaign_recipients` table (token lookup) and campaign configuration.
- **Dashboard/API tier** reads from both PostgreSQL and Redis for
  reporting and real-time monitoring.  It writes campaign configuration,
  templates, address books, and other management data to PostgreSQL.
- **Worker tier** reads tasks from the Redis broker (db1), queries
  PostgreSQL for campaign and recipient data, and writes send results
  back to both stores.
- **Celery beat** (exactly one instance) writes periodic task messages to
  the Redis broker.

### Tracking application

The tracking tier runs `tracking_app.py`, a minimal FastAPI application
that mounts only the tracking router, health check, and essential
middleware.  It does not include authentication, admin endpoints, or
reporting routes.  This reduces the attack surface of the public-facing
tier and keeps the container image lean.

---

## Data Flow

### Campaign Lifecycle

```
    +-------+     schedule      +-----------+     beat check     +---------+
    | DRAFT | ----------------> | SCHEDULED | -----------------> | RUNNING |
    +-------+                   +-----------+   (every 60s)      +---------+
        |                                                          |     |
        | cancel                                        complete   |     | bounce rate
        v                                                  |       |     | > 5%
  +-----------+                                            v       |     v
  | CANCELLED | <------ cancel ---------------------- +-----------+  +--------+
  +-----------+                                       | COMPLETED |  | PAUSED |
                                                      +-----------+  +--------+
                                                                        |
                                                                resume  |
                                                                        v
                                                                    RUNNING
```

1. **DRAFT:** Campaign created with template, SMTP profile, and recipients.
   Editable.
2. **SCHEDULED:** Send window configured.  Celery beat checks every 60s for
   campaigns whose `send_window_start` has arrived.
3. **RUNNING:** `dispatch_campaign` task fans out `send_batch` sub-tasks.
   Recipients are processed in batches (max 200 per task) with staggered
   countdown delays.
4. **COMPLETED:** `check_campaign_progress` detects zero pending recipients
   and marks the campaign complete.
5. **PAUSED:** Auto-triggered by `BounceMonitor` when bounce rate exceeds
   5% after 100+ sends.  Can be manually resumed.
6. **CANCELLED:** Terminal state.  Running batches check for this status and
   skip remaining sends.

### Email Sending Flow

```
Campaign (SCHEDULED)
        |
        v
[Celery Beat: check_and_launch_scheduled]  -- every 60s
        |
        v
[dispatch_campaign task]
  |-- Load campaign config from PostgreSQL
  |-- Create CampaignRecipient records (if not pre-populated)
  |-- Calculate throttle rate (sends/minute)
  |-- Initialize Redis counters
  |-- Fan out send_batch sub-tasks
        |
        v
[send_batch task]  (one per batch of up to 200 recipients)
  |-- Load campaign, SMTP profile, email template
  |-- For each recipient:
  |     |-- Throttle: acquire token from Redis token bucket
  |     |-- Render template with tracking pixel + tracked links
  |     |-- Send via SMTP backend (SmtpRelay / SES / Mailgun / SendGrid)
  |     |-- Record SENT event in PostgreSQL
  |     |-- Update recipient status
  |-- Update Redis counters (sent/failed/pending)
        |
        v
[check_campaign_progress task]
  |-- Count remaining PENDING recipients
  |-- If zero: mark campaign COMPLETED
  |-- If non-zero: re-enqueue self after 60s
```

### Tracking Flow

**Note:** In production, tracking endpoints run as an independent service
(`tracking_app.py`) on dedicated instances behind the tracking load
balancer.  The data flow below is identical regardless of whether tracking
runs as part of the full API or as the standalone tracking application.

```
Recipient opens email / clicks link / submits form
        |
        v
HTTP request to /api/v1/tracking/{open|click|submit}/{token}
        |
        v
[Tracking Router]
  |-- Validate recipient token (UUID lookup)
  |-- Extract metadata (user_agent, IP, timestamp)
        |
        v
[EventRecorder]
  |-- Write TrackingEvent to PostgreSQL
  |     |-- Deduplication: opens increment open_count on existing row
  |     |-- Submissions: record field NAMES only (never values)
  |-- Push to Redis (best-effort, non-blocking)
  |     |-- Increment counter: tidepool:rt:{campaign_id}:{event_type}
  |     |-- Push to event feed: tidepool:feed:{campaign_id}
        |
        v
[Response]
  |-- Open: 1x1 transparent GIF
  |-- Click: 302 redirect to landing page or original URL
  |-- Submit: 200 + optional redirect to training URL
```

### Address Book Ingestion Flow

```
User uploads .xlsx / .xls / .csv via /api/v1/addressbooks
        |
        v
[API endpoint]
  |-- Validate file extension and size (max 50 MB)
  |-- Create AddressBook record (status: PENDING)
  |-- Save file to upload directory
  |-- Enqueue Celery task
        |
        v
[Celery ingestor task]
  |-- Update AddressBook status to PROCESSING
  |-- Stream-parse file (openpyxl for Excel, csv module for CSV)
  |-- Apply column mapping (auto-detect or user-specified)
  |-- Deduplicate contacts within the book (email + address_book_id unique)
  |-- Batch INSERT contacts (configurable batch size)
  |-- Update AddressBook status to COMPLETED with row_count
  |-- On failure: status = FAILED with error details
```

---

## Database Schema

### Entity-Relationship Diagram

```
+------------------+       +---------------------+       +-------------------+
|     users        |       |    api_keys          |       |   email_templates |
+------------------+       +---------------------+       +-------------------+
| PK id            |<------| FK user_id           |       | PK id             |
|    username (UQ) |       |    key_prefix        |  +----| FK created_by     |
|    email (UQ)    |       |    key_hash (UQ)     |  |    |    name           |
|    hashed_pass   |       |    name              |  |    |    category (enum)|
|    is_active     |       |    scopes (JSONB)    |  |    |    difficulty 1-5  |
|    is_admin      |       |    is_active         |  |    |    subject         |
|    full_name     |       |    expires_at        |  |    |    body_html       |
|    failed_logins |       |    last_used_at      |  |    |    body_text       |
|    locked_until  |       |    created_at        |  |    |    variables(JSONB)|
|    created_at    |       |    updated_at        |  |    |    created_at      |
|    updated_at    |       +---------------------+  |    |    updated_at      |
+------------------+                                 |    +-------------------+
   |   |   |   |                                     |
   |   |   |   +---------------------------+         |
   |   |   |                               |         |
   |   |   +---------------+               |         |
   |   |                   |               |         |
   |   |   +---------------+--+   +--------+------+  |    +-------------------+
   |   |   |  smtp_profiles    |   | landing_pages |  |    |  address_books    |
   |   |   +-------------------+   +---------------+  |    +-------------------+
   |   +---| FK created_by     |   | PK id         |  |    | PK id             |
   |       |    name            |   | FK created_by-+--+    |    name           |
   |       |    backend_type    |   |    name        |       |    source_filename|
   |       |    host            |   |    page_type   |       |    import_status  |
   |       |    port            |   |    html_content|       |    row_count      |
   |       |    username        |   |    config(JSON)|       |    column_mapping |
   |       |    password (ENC)  |   |    redirect_url|       |    created_at     |
   |       |    use_tls/use_ssl |   |    created_at  |       |    updated_at     |
   |       |    from_address    |   |    updated_at  |       +-------------------+
   |       |    from_name       |   +---------------+              |
   |       |    config (JSONB)  |       |                          |
   |       |    enc_creds (ENC) |       |               +----------+--------+
   |       |    created_at      |       |               |    contacts       |
   |       |    updated_at      |       |               +-------------------+
   |       +-------------------+       |               | PK id             |
   |              |                     |               | FK address_book_id|
   |              |                     |               |    email (IDX)    |
   |   +----------+---------------------+               |    first_name     |
   |   |                                                |    last_name      |
   |   |   +-------------------------------------------+|    department     |
   |   |   |                                            |    title          |
   v   v   v                                            |    custom_fields  |
+------------------+                                    |    is_valid_email |
|   campaigns      |                                    |    do_not_email   |
+------------------+                                    |    bounce_count   |
| PK id            |                                    |    created_at     |
| FK smtp_profile  |                                    |    updated_at     |
| FK email_template|                                    +-------------------+
| FK landing_page  |                                           |
| FK created_by    |                                           |
|    name          |        +-------------------+              |
|    description   |        | campaign_recipients|              |
|    status (enum) |        +-------------------+              |
|    send_window_* |        | PK campaign_id  --+--> campaigns |
|    throttle_rate |        | PK contact_id   --+--> contacts  |
|    training_url  |        |    token (UQ,IDX) |              |
|    training_delay|        |    status (enum)  |              |
|    created_at    |        |    sent_at        |              |
|    updated_at    |        |    delivered_at   |              |
+------------------+        +-------------------+              |
        |                                                      |
        |                                                      |
        |           +-------------------+          +-----------+--------+
        |           | tracking_events   |          |   groups           |
        +-----------+-------------------+          +--------------------+
        |           | PK id             |          | PK id              |
        |           | FK campaign_id    |          |    name            |
        |           |    recipient_token|          |    description     |
        |           |    event_type     |          |    created_at      |
        |           |    timestamp      |          |    updated_at      |
        |           |    metadata(JSONB)|          +--------------------+
        |           | IDX (campaign,    |                   |
        |           |      event_type)  |          +--------+-----------+
        |           +-------------------+          |  group_members     |
        |                                          +--------------------+
        |           +-------------------+          | PK group_id     ---|---> groups
        +-----------+ report_snapshots  |          | PK contact_id   ---|---> contacts
        |           +-------------------+          +--------------------+
        |           | PK id             |
        |           | FK campaign_id    |
        |           | FK generated_by   |   +-------------------+
        |           |    report_type    |   | training_redirects|
        |           |    generated_at   |   +-------------------+
        |           |    data (JSONB)   |   | PK id             |
        |           |    file_path      |   | FK campaign_id    |
        |           +-------------------+   |    recipient_token|
        |                                   |    redirected_at  |
        |                                   |    user_agent     |
        |   +-------------------+           |    ip_address     |
        |   |   audit_logs      |           |    created_at     |
        |   +-------------------+           |    updated_at     |
        |   | PK id             |           +-------------------+
        |   |    actor          |
        |   |    action         |
        |   |    resource_type  |
        |   |    resource_id    |
        |   |    before_state   |
        |   |    after_state    |
        |   |    ip_address     |
        |   |    timestamp      |
        |   +-------------------+
```

### Table Summary (15 tables)

| Table | Rows (typical) | Key purpose |
|---|---|---|
| `users` | 10-50 | Platform operators (admins, analysts) |
| `api_keys` | 10-100 | Programmatic API access; bcrypt-hashed, scoped |
| `campaigns` | 10-500 | Central orchestration entity linking template, SMTP, and recipients |
| `smtp_profiles` | 2-10 | SMTP/SES/Mailgun/SendGrid configs; credentials encrypted at rest |
| `email_templates` | 20-200 | Phishing pretext templates with Jinja2 variables and difficulty rating |
| `landing_pages` | 10-100 | Credential capture pages (built-in templates, cloned, or custom HTML) |
| `address_books` | 5-50 | Container for imported contact lists |
| `contacts` | 1K-500K | Individual recipient records with email, department, custom fields |
| `groups` | 5-50 | Logical groupings of contacts |
| `group_members` | 1K-500K | Many-to-many: contacts <-> groups |
| `campaign_recipients` | 1K-500K per campaign | Per-campaign recipient state; UUID token for tracking |
| `tracking_events` | 10K-5M per campaign | Immutable event log: SENT, DELIVERED, OPENED, CLICKED, SUBMITTED, REPORTED |
| `report_snapshots` | 1-5 per campaign | Persisted report data (JSONB) + optional PDF file path |
| `audit_logs` | 10K+ | Immutable record of all state-changing API actions |
| `training_redirects` | 0-100K per campaign | Records when phished users were redirected to training |

### Index Strategy

| Index | Table | Columns | Rationale |
|---|---|---|---|
| Primary key | All tables | `id` | Row lookup |
| `ix_tracking_events_campaign_event` | `tracking_events` | `(campaign_id, event_type)` | Fast event aggregation per campaign and type |
| `recipient_token` (unique) | `campaign_recipients` | `token` | O(1) token lookup for tracking endpoints |
| `recipient_token` (index) | `tracking_events` | `recipient_token` | Per-recipient event timeline queries |
| `uq_contact_email_book` | `contacts` | `(email, address_book_id)` | Deduplication within an address book |
| `email` (index) | `contacts` | `email` | Cross-book contact lookup for bounce processing |
| `key_prefix` (index) | `api_keys` | `key_prefix` | Fast API key candidate lookup (first 11 chars) |
| `key_hash` (unique) | `api_keys` | `key_hash` | Uniqueness guarantee on hashed keys |

---

## API Architecture

### Authentication Flow

TidePool supports two parallel authentication methods:

**1. JWT Bearer Token (web dashboard)**

```
POST /api/v1/auth/login  { username, password }
        |
        v
  Verify password (bcrypt) + check lockout
        |
        v
  Issue access_token (15 min) + refresh_token (7 days)
        |
        v
  Client sends: Authorization: Bearer <access_token>
        |
        v
  On expiry: POST /api/v1/auth/refresh { refresh_token }
```

**2. API Key (programmatic access)**

```
POST /api/v1/auth/api-keys  { name, scopes, expires_in_days }
        |
        v
  Generate 44-char random key, bcrypt-hash it, store hash
  Return raw key exactly once
        |
        v
  Client sends: X-API-Key: <raw_key>
        |
        v
  Lookup by key_prefix (first 11 chars), bcrypt-verify
  Check expiry, update last_used_at
  Enforce scope restrictions (wildcard matching)
```

**Resolution order in `get_current_user`:** X-API-Key header is checked
first.  If absent, falls back to Bearer token.  If neither is valid,
returns 401.

### Rate Limiting Tiers

| Tier | Limit | Applies to |
|---|---|---|
| Auth | 10/minute | `/api/v1/auth/login`, `/api/v1/auth/refresh` |
| Tracking | 300/minute | `/api/v1/tracking/*` |
| Default | 100/minute | All other endpoints |

Rate limiting uses `slowapi` (backed by Redis) with `get_remote_address`
as the key function.  X-Forwarded-For is respected for clients behind a
reverse proxy.

### Router Organization

| Router module | Prefix | Tag | Endpoint count (approx) | Description |
|---|---|---|---|---|
| `health` | `/health` | health | 1 | Liveness/readiness probe |
| `auth` | `/api/v1/auth` | auth | 7 | Login, refresh, register, me, change-password, API key CRUD |
| `campaigns` | `/api/v1/campaigns` | campaigns | 6+ | Campaign CRUD, launch, pause, resume, cancel |
| `smtp_profiles` | `/api/v1/smtp-profiles` | smtp-profiles | 5+ | SMTP profile CRUD + connection test |
| `addressbooks` | `/api/v1/addressbooks` | addressbooks | 5+ | Address book upload, list, detail, delete |
| `templates` | `/api/v1/templates` | templates | 5+ | Email template CRUD + preview |
| `landing_pages` | `/api/v1/landing-pages` | landing-pages | 5+ | Landing page CRUD + clone from URL |
| `tracking` | `/api/v1/tracking` | tracking | 4 | Open pixel, click redirect, form submission, phish report |
| `reports` | `/api/v1/reports` | reports | 5+ | Campaign metrics, department breakdown, trend analysis, exports |
| `monitor` | `/api/v1/monitor` | monitor | 3+ | Real-time campaign progress, bounce rate status |
| `audit` | `/api/v1/audit` | audit | 2+ | Audit log query and export |
| `automation` | `/api/v1/automation` | automation | 3+ | Automated campaign scheduling and API-driven dispatch |
| `training` | `/api/v1/training` | training | 2+ | Training redirect tracking |
| `webhooks` | `/api/v1/webhooks` | webhooks | 3+ | Bounce/complaint webhook receivers (SES SNS, Mailgun, SendGrid) |

### Request Lifecycle (Middleware Stack)

Middleware executes in reverse registration order (last added = first
executed).  The registration order in `create_app()` is:

```
1. CORSMiddleware          -- registered first, executes last on inbound
2. SecurityHeadersMiddleware
3. RequestSizeLimitMiddleware
4. AuditMiddleware          -- registered last, executes first on inbound
```

**Inbound request path:**

```
Client Request
    |
    v
[AuditMiddleware]           -- Record actor, action, resource for POST/PUT/DELETE
    |                          (skips /api/v1/tracking/* and /health)
    v
[RequestSizeLimitMiddleware] -- Reject if Content-Length > 1 MB (or 50 MB for multipart)
    |
    v
[SecurityHeadersMiddleware]  -- (no-op on inbound; adds headers to response)
    |
    v
[CORSMiddleware]             -- Validate Origin, handle preflight OPTIONS
    |
    v
[Rate Limiter]               -- slowapi check against tier limit
    |
    v
[Router / Endpoint]          -- Auth dependency resolves user (JWT or API key)
    |
    v
[Response]                   -- Flows back through middleware in reverse
    |
    v
[SecurityHeadersMiddleware]  -- Inject: X-Frame-Options, X-Content-Type-Options,
                                HSTS, X-XSS-Protection, Referrer-Policy,
                                Permissions-Policy
    |
    v
Client Response
```

---

## Security Architecture

### Encryption at Rest

**SMTP credentials:** The `SmtpProfile.password` and
`SmtpProfile.encrypted_credentials` columns use a custom SQLAlchemy
`EncryptedField` type decorator backed by Fernet symmetric encryption.

- Encryption key: `ENCRYPTION_KEY` environment variable (valid Fernet key)
- Key rotation: Multiple comma-separated keys supported via `MultiFernet`.
  The first key encrypts; all keys are tried during decryption.
- Storage format: Fernet token, base64-encoded, stored as TEXT in PostgreSQL

**Passwords:** User passwords are hashed with bcrypt via `passlib`.  API key
raw values are also bcrypt-hashed; only the hash and an 11-character prefix
(for lookup) are stored.

### Transport Security

- **HSTS:** `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  injected by `SecurityHeadersMiddleware` on every response.
- **TLS termination:** Handled by nginx reverse proxy in production.
- **SMTP TLS:** Configurable per SMTP profile (`use_tls` for STARTTLS,
  `use_ssl` for implicit TLS).

### Input Validation Layers

1. **Pydantic schemas:** All request bodies validated through Pydantic v2
   models with field constraints.
2. **Request size limits:** 1 MB for JSON bodies, 50 MB for multipart
   (file uploads).
3. **File type whitelist:** Address book uploads restricted to `.xlsx`,
   `.xls`, `.csv`.
4. **HTML sanitization:** `bleach` available for template content
   sanitization.
5. **SQL injection:** Prevented by SQLAlchemy parameterized queries
   throughout.

### SSRF Protection

Landing page cloning (`cloner.py`) fetches external URLs.  Protection
measures:

- URL scheme whitelist (HTTP/HTTPS only)
- Content-type validation on response
- Timeout enforcement (30s)
- Response size limits

### Privacy Design (Credential Harvester)

The `EventRecorder.record_submission()` method stores only field *names*
(`field_names_submitted`), never field *values*.  This is by design -- the
platform proves susceptibility without capturing actual credentials.

The Redis event feed for submissions includes only `field_count` (integer),
not field names.

### Audit Trail

All state-changing API requests (POST, PUT, DELETE, PATCH) are logged by
`AuditMiddleware` to the `audit_logs` table:

- **Actor:** Username (from JWT), API key prefix, or "anonymous"
- **Action:** HTTP method + path
- **Resource:** Type and ID parsed from the URL
- **IP address:** Client IP (X-Forwarded-For aware)
- **Timestamp:** Server-generated `now()`
- **Before/after state:** Available when using the standalone
  `log_audit_event()` function within endpoints

High-volume tracking endpoints (`/api/v1/tracking/*`) and health checks
are excluded from audit logging.

### Rate Limiting Strategy

Three tiers enforced by `slowapi`:

| Tier | Rate | Purpose |
|---|---|---|
| Auth | 10/min | Brute-force prevention on login |
| Tracking | 300/min | High-volume pixel/click/submit endpoints |
| Default | 100/min | General API protection |

Account lockout: 5 failed login attempts triggers a 15-minute lockout.
The lockout state is stored in the `users` table (`failed_login_attempts`,
`locked_until`).

---

## Frontend Architecture

### Build and Serving

- **Development:** Vite dev server with HMR (`npm run dev`), proxied through
  Docker Compose port mapping.
- **Production:** Two-stage Docker build. Stage 1: `node:20-alpine` runs
  `npm ci && npm run build`. Stage 2: `nginx:alpine` serves the static
  `dist/` directory with SPA fallback routing.  In the production topology,
  nginx also handles domain-based routing: requests to the tracking domain
  are proxied to dedicated tracking instances (`tracking_app.py`), while
  requests to the dashboard domain are proxied to the full API tier and
  frontend.

### Code Organization

```
frontend/src/
  main.tsx                -- React entry point
  App.tsx                 -- Router setup, layout wiring
  api/                    -- HTTP client layer
    client.ts             -- Axios instance with interceptors (auth, refresh)
    auth.ts               -- Login, refresh, register API calls
    campaigns.ts          -- Campaign CRUD
    addressbooks.ts       -- Address book upload + list
    templates.ts          -- Template CRUD
    landing_pages.ts      -- Landing page CRUD
    reports.ts            -- Report generation + export
    monitor.ts            -- Real-time campaign monitoring
    settings.ts           -- SMTP profile management
    audit.ts              -- Audit log queries
  store/
    auth.ts               -- Zustand auth store (tokens, user, login/logout)
  hooks/
    useAuth.ts            -- Auth convenience hook
  pages/
    Login.tsx             -- Authentication page
    Dashboard.tsx         -- Overview metrics
    Campaigns.tsx         -- Campaign list
    CampaignCreate.tsx    -- Campaign creation wizard
    CampaignDetail.tsx    -- Single campaign view with live tracking
    AddressBooks.tsx      -- Contact management
    Templates.tsx         -- Email template editor
    LandingPages.tsx      -- Landing page manager
    Reports.tsx           -- Report generation and export
    Settings.tsx          -- SMTP profiles, system config
    AuditLog.tsx          -- Audit trail viewer
  components/
    Layout.tsx            -- App shell with sidebar
    Sidebar.tsx           -- Navigation sidebar
    LandingPageEditor.tsx -- GrapesJS visual editor integration
    LandingPagePreview.tsx-- Landing page preview
    LoadingSpinner.tsx    -- Loading indicator
    ErrorBoundary.tsx     -- React error boundary
  types/
    index.ts              -- Shared TypeScript type definitions
```

### State Management

**Zustand** store (`store/auth.ts`) manages:

- JWT access and refresh tokens
- Current user profile
- Login/logout actions
- Token persistence (localStorage)

All server state (campaigns, contacts, templates, etc.) is managed by
**TanStack React Query** with:

- Automatic background refetching
- Cache invalidation on mutations
- Optimistic updates for UI responsiveness
- Stale-while-revalidate patterns

### Data Fetching

The Axios client (`api/client.ts`) provides:

- Base URL configuration
- Automatic `Authorization: Bearer` header injection
- 401 interceptor that triggers token refresh
- Response error normalization

React Query hooks wrap every API module, providing:

- `useQuery` for reads (with staleTime, refetchInterval for live data)
- `useMutation` for writes (with onSuccess cache invalidation)
- Pagination support via `useInfiniteQuery` where applicable

### Component Hierarchy

```
App
  ErrorBoundary
    Routes
      Login                              -- unauthenticated
      Layout                             -- authenticated shell
        Sidebar
        Dashboard
        Campaigns -> CampaignCreate
                  -> CampaignDetail
        AddressBooks
        Templates
        LandingPages -> LandingPageEditor (GrapesJS)
                     -> LandingPagePreview
        Reports
        Settings
        AuditLog
```

---

## Email Engine

### Batch Dispatch Strategy

The dispatcher (`engine/dispatcher.py`) processes campaigns in three phases:

1. **Preparation:** Load campaign, create `CampaignRecipient` records (if
   not pre-populated by the API), calculate throttle rate and batch size.

2. **Fan-out:** Split pending recipients into batches of up to 200. Each
   batch becomes a `send_batch` Celery task with a staggered `countdown`
   (batch_index * 2 seconds) to avoid thundering herd.

3. **Progress monitoring:** Schedule `check_campaign_progress` task after
   an estimated 50% completion time.  The task re-enqueues itself every 60s
   until all recipients are processed.

| Parameter | Default | Configurable via |
|---|---|---|
| Max batch size | 200 | `_MAX_BATCH_SIZE` constant |
| Default send window | 4 hours | `_DEFAULT_WINDOW_HOURS` constant |
| Max throttle rate | 10,000/min | `calculate_throttle()` cap |
| Min throttle rate | 1/min | `calculate_throttle()` floor |
| Batch task retries | 3 | `@celery.task(max_retries=3)` |
| Retry delay | 30s | `default_retry_delay=30` |

### Throttling Algorithm (Redis Token Bucket)

The `SendThrottle` class (`engine/throttle.py`) implements an atomic
Redis-based token bucket using a Lua script:

```
Bucket parameters:
  - max_tokens   = rate_per_minute (allows burst up to 1 minute's capacity)
  - refill_rate  = rate_per_minute / 60.0 (tokens per second)

On acquire():
  1. EVALSHA the Lua script atomically:
     - Load current tokens and last_refill timestamp
     - Calculate refill based on elapsed time
     - If tokens >= 1: decrement and return 1 (acquired)
     - Else: return 0 (denied)
  2. If denied, back off exponentially (10ms initial, 500ms cap)
  3. Retry until a token is acquired

Bucket keys auto-expire after 24 hours.
```

### SMTP Backend Abstraction

The `SmtpBackend` ABC (`engine/smtp_backends.py`) defines a uniform
`send()` and `test_connection()` interface.  The factory function
`get_backend(smtp_profile)` instantiates the correct subclass:

| BackendType | Class | Transport |
|---|---|---|
| `SMTP` | `SmtpRelayBackend` | aiosmtplib (async SMTP/SMTPS) |
| `SES` | `SesBackend` | boto3 (run in executor to avoid blocking) |
| `MAILGUN` | `MailgunBackend` | httpx async POST to Mailgun API |
| `SENDGRID` | `SendGridBackend` | httpx async POST to SendGrid v3 API |

### Bounce Handling Flow

```
Webhook arrives (SES SNS / Mailgun / SendGrid)
        |
        v
[Webhook router: /api/v1/webhooks/{provider}]
        |
        v
[Provider-specific parser]
  |-- SESBounceProcessor.parse_sns_notification()
  |-- MailgunBounceProcessor.parse_webhook()
  |-- SendGridBounceProcessor.parse_webhook()
        |
        v
[Normalize to BounceEvent dataclass]
  |-- recipient_email
  |-- bounce_type: HARD / SOFT / COMPLAINT
  |-- message (diagnostic text)
  |-- timestamp
        |
        v
[Celery task: process_bounce_notification]
        |
        v
[BounceHandler.process_bounce()]
  |-- Look up CampaignRecipient by email (+ optional campaign_id)
  |-- Update recipient status to BOUNCED (hard/complaint)
  |-- Record TrackingEvent with bounce metadata
  |-- Flag Contact:
  |     |-- HARD bounce: is_valid_email = false, bounce_count++
  |     |-- COMPLAINT: do_not_email = true
  |     |-- SOFT bounce: bounce_count++
```

### Auto-Pause Logic

The `BounceMonitor` (`engine/bounce_monitor.py`) protects sender reputation:

- **Threshold:** 5% bounce rate
- **Minimum sample:** 100 emails sent (prevents false positives on small batches)
- **Check sources:** Redis counters first (fast path), PostgreSQL fallback
- **Action:** Sets campaign status to PAUSED, records audit event with full
  bounce breakdown
- **Recovery:** Manual resume via API after address book cleanup

---

## Reporting Pipeline

### Metrics Aggregation

The `MetricsAggregator` (`reports/aggregator.py`) computes analytics at
four levels:

1. **Campaign-level:** Total recipients, event counts (sent/delivered/
   opened/clicked/submitted/reported), rates, time-to-first-click
   (median + p90), hourly send distribution, event timeline.

2. **Department-level:** Per-department breakdown with individual recipient
   risk scoring, headcount-adjusted participation rates, and department
   risk scores.

3. **Trend analysis:** Cross-campaign comparison of open/click/submit rates
   with directional assessment (improving/stable/declining based on 2%
   threshold).

4. **Organisation risk:** Headcount-weighted average of department scores.

**Real-time path (Redis):**

```
Event occurs -> EventRecorder -> Redis HINCRBY tidepool:rt:{campaign_id}:{type}
                              -> Redis RPUSH tidepool:feed:{campaign_id}
```

**Persistent path (PostgreSQL):**

```
Event occurs -> EventRecorder -> INSERT tracking_events
Daily at 03:00 UTC -> aggregate_daily_metrics task -> ReportSnapshot rows
```

### Risk Scoring Formula

**Recipient-level** (`calculate_recipient_risk`):

```
score = 0.0
if CLICKED:   score += 0.4
if SUBMITTED: score += 0.6
if REPORTED:  score -= 0.2
return clamp(score, 0.0, 1.0)
```

Examples:
- Only opened: 0.0 (no risk action)
- Clicked only: 0.4
- Clicked + submitted: 1.0
- Clicked + submitted + reported: 0.8
- Reported only: 0.0 (floor clamp)

**Department-level** (`calculate_department_risk`):

```
avg = mean(recipient_scores)
adjusted = avg / participation_rate     # low participation inflates risk
return clamp(adjusted, 0.0, 1.0)
```

**Organisation-level** (`calculate_org_risk`):

```
weighted_sum = sum(dept_score * dept_headcount for each department)
org_score = weighted_sum / total_headcount
return clamp(org_score, 0.0, 1.0)
```

**Risk level labels:**

| Score range | Label |
|---|---|
| [0.0, 0.2) | Low |
| [0.2, 0.4) | Moderate |
| [0.4, 0.6) | High |
| [0.6, 0.8) | Critical |
| [0.8, 1.0] | Severe |

### Export Formats

| Format | Implementation | Use case |
|---|---|---|
| **PDF** | WeasyPrint renders an HTML template with inline SVG charts, cover page, table of contents, executive summary, department breakdown, risk assessment, and recommendations. Falls back to raw HTML if WeasyPrint is unavailable. | Executive stakeholder delivery |
| **CSV** | `csv.DictWriter` streaming response | Data analysis, import into BI tools |
| **JSON** | Structured JSON with `_metadata` header (timestamp, filename, format) | API integration, archival |

### Celery Beat Schedule

| Task | Interval | Purpose |
|---|---|---|
| `check_and_launch_scheduled` | 60s | Launch campaigns whose send window has opened |
| `check_all_campaign_progress` | 120s | Mark completed campaigns, detect stalled sends |
| `cleanup_expired_data` | Daily 02:00 UTC | Remove expired tokens and temporary data |
| `aggregate_daily_metrics` | Daily 03:00 UTC | Roll up tracking events into report snapshots |
