# TidePool

Enterprise-scale phishing simulation platform for security awareness testing.

## Overview

TidePool is a self-hosted phishing simulation platform designed for organizations that need to conduct organization-wide security awareness campaigns at scale. It handles the complete campaign lifecycle -- planning, email delivery, landing page hosting, interaction tracking, real-time monitoring, risk scoring, and compliance reporting -- in a single integrated stack. Campaigns scale to large recipient populations with configurable throttling, bounce detection, and automatic pause controls.

The platform is privacy-safe by design. Credential harvester pages log interaction metadata only (which fields were submitted, timestamps, user-agent strings) and never capture or store actual credentials. Every action is recorded in a tamper-evident audit trail with chained SHA-256 integrity hashes and configurable retention policies.

TidePool is also agent-ready. The entire platform can be driven end-to-end by AI agents through its MCP (Model Context Protocol) server or standard REST API. An included orchestrator can autonomously plan campaigns, generate pretexts with progressive difficulty, execute sends, monitor results in real time, and produce analysis reports -- with configurable safety gates that require human approval before execution.

## Features

### Campaign Management

- Multi-step campaign creation wizard with real-time validation
- Configurable send windows and per-campaign throttle rates
- Campaign scheduling with Celery Beat (recurring and one-shot)
- Real-time monitoring dashboard with live metrics via Redis counters
- Automatic bounce detection and campaign auto-pause on threshold breach

### Email Engine

- Pluggable SMTP backends: direct relay, Amazon SES, Mailgun, SendGrid
- Jinja2 template rendering with per-recipient variable substitution
- Tracking pixel injection and link rewriting for open/click analytics
- Redis token-bucket throttling with configurable rates per backend
- Scales to large campaigns via Celery worker pool (default concurrency: 4)

### Address Book Management

- Streaming Excel/CSV ingestion with a low memory footprint
- Automatic column detection and mapping for common HR export formats
- Deduplication and email validation on import
- Contact grouping and department segmentation

### Pretext Library

- 15 built-in pretext templates across 5 categories (IT, HR, Finance, Executive, Vendor)
- Difficulty rating system (1-5) for progressive training programs
- Red flag annotations for alignment with post-campaign training
- Custom template creation with a variable substitution system

### Landing Pages

- 5 built-in login page templates (Microsoft 365, Google, Okta, VPN, generic corporate)
- URL cloner with SSRF protection for replicating external pages
- GrapesJS visual editor for building custom landing pages
- Privacy-safe credential harvester (logs field names only, discards submitted values)

### Reporting and Compliance

- Executive summary generation with auto-generated findings and recommendations
- Department-level risk scoring and trend analysis across campaigns
- PDF export via WeasyPrint, Excel export via openpyxl
- Compliance package generation (ZIP archive with evidence artifacts, SHA-256 integrity chains)
- Full audit trail with chained integrity hashes (7-year default retention)

### Security

- Dual authentication: scoped and expirable API keys + JWT (15-minute access tokens, 7-day refresh tokens)
- SMTP credentials encrypted at rest with Fernet symmetric encryption
- Tiered rate limiting per endpoint (auth: 10/min, default: 100/min, tracking: 300/min)
- Security headers: HSTS, X-Frame-Options, Content-Security-Policy
- Account lockout after 5 failed attempts (15-minute cooldown)
- Password complexity enforcement
- SSRF protection on the URL cloner
- Anti-enumeration responses on tracking endpoints

### AI Agent Integration

- MCP (Model Context Protocol) server for Claude Code and other MCP-compatible clients
- AI-powered pretext generation via Anthropic Claude API (optional -- falls back to built-in library)
- Autonomous campaign planning, execution, monitoring, and analysis via orchestrator
- Annual program planning with progressive difficulty scheduling
- Safety gates: auto-execute disabled by default, configurable recipient thresholds (default 1,000)

## Architecture

```
                                 INTERNET
                                    |
                               [ TLS / nginx ]
                                    |
                +-------------------+-------------------+
                |                                       |
         [ Frontend SPA ]                         [ FastAPI ]
         React 19 / Vite                          uvicorn x4
         port 3000 (dev)                          port 8000
                                                       |
                                      +----------------+----------------+
                                      |                |                |
                                 [ Celery         [ Celery        [ Redis 7 ]
                                   Worker ]         Beat ]         db0: counters
                                   x4 conc.        scheduler       db1: broker
                                      |                |           db2: results
                                      +-------+--------+
                                              |
                                       [ PostgreSQL 16 ]
                                              |
                +-----------------------------+-----------------------------+
                |                             |                             |
          [ SMTP Relay ]               [ AWS SES ]              [ Mailgun / SendGrid ]
                |                             |                             |
                +-----------------------------+-----------------------------+
                                              |
                                        RECIPIENT INBOX
                                              |
                                        opens / clicks
                                              |
                                     [ Tracking Endpoints ]  -->  Redis + PostgreSQL
```

**Stack summary:** Python 3.13 / FastAPI / SQLAlchemy 2.0 / Celery / Redis 7 / PostgreSQL 16 on the backend. React 19 / TypeScript / Vite / Tailwind CSS / Recharts / GrapesJS on the frontend. Docker Compose for orchestration.

## Quick Start

```bash
# Clone and configure
git clone https://github.com/TRACEMANTIS/TidePool.git
cd TidePool
cp .env.example .env
python3 scripts/generate_secrets.py --append-to .env

# Launch stack
docker compose up -d
docker compose exec api alembic upgrade head

# Create admin user
python3 scripts/setup_first_admin.py

# Access
# Dashboard: http://localhost:3000
# API docs:  http://localhost:8000/docs
# MailHog:   http://localhost:8025 (dev mode)
```

For production deployment, TLS configuration, scaling, monitoring, and backup procedures, see [DEPLOY.md](DEPLOY.md).

## Agent-Driven Campaigns

TidePool can be driven entirely by AI agents. The included `agent_runner.py` script provides a CLI interface to the orchestrator:

```bash
# Plan a campaign
python3 scripts/agent_runner.py plan \
  --objective "Q2 phishing readiness assessment" \
  --addressbook-id 1

# Full autonomous cycle (plan -> approve -> execute -> monitor -> analyze)
python3 scripts/agent_runner.py full-cycle \
  --objective "Monthly security test" \
  --addressbook-id 1 \
  --smtp-profile-id 1
```

For MCP integration with Claude Code or other MCP-compatible clients:

```bash
# Add TidePool MCP server to Claude Code config
cp tidepool-mcp.json ~/.claude/
```

The MCP server exposes campaign management, address book operations, monitoring, and reporting as tool calls that agents can invoke directly.

## API

TidePool exposes a REST API with OpenAPI documentation available at `/docs` when the stack is running.

- **14 router modules, 80+ endpoints**
- Key endpoint groups: `/auth`, `/campaigns`, `/addressbooks`, `/templates`, `/landing-pages`, `/tracking`, `/reports`, `/audit`, `/agents`, `/automation`, `/monitor`, `/webhooks`, `/smtp-profiles`, `/health`
- Dual auth: Bearer JWT tokens for interactive use, `X-API-Key` header for programmatic access
- All endpoints return JSON; tracking endpoints return pixel/redirect responses

## Project Structure

```
TidePool/
  backend/
    app/
      api/              # FastAPI routers (14 modules)
      agents/           # AI agent integration (MCP tools, orchestrator, pretext engine)
      engine/           # Email dispatch, throttling, bounce handling, scheduling
      models/           # SQLAlchemy ORM models
      reports/          # Metrics aggregation, PDF/CSV export, compliance packages
      config.py         # Pydantic settings (env-driven configuration)
    tests/              # pytest suite (7 test modules)
  frontend/
    src/
      pages/            # 11 React page components
      components/       # Layout, sidebar, GrapesJS editor, preview panels
      api/              # API client modules
  landing_page_templates/   # 6 login page templates (O365, Google, Okta, VPN, generic, training)
  pretext_library/          # Built-in pretext templates
  scripts/                  # CLI tools (agent runner, setup, secrets, MCP server)
  docker-compose.yml        # Production compose
  docker-compose.dev.yml    # Development compose (includes MailHog)
  tidepool-mcp.json         # MCP server configuration for Claude Code
```

## Documentation

- [DEPLOY.md](DEPLOY.md) -- Deployment guide: dev setup, production hardening, scaling, monitoring, backup, security checklist
- [ARCHITECTURE.md](ARCHITECTURE.md) -- Technical architecture: data flows, database schema, API design, security model, engine internals, frontend architecture

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.13, FastAPI 0.115+, SQLAlchemy 2.0, Celery 5.4, Redis 5.0+ |
| Frontend | React 19, TypeScript 5.7, Vite 6, Tailwind CSS 4, Recharts 2, GrapesJS 0.21 |
| Database | PostgreSQL 16 |
| Queue | Redis 7, Celery 5.4 |
| Auth | JWT (python-jose), API keys, bcrypt (passlib), Fernet encryption |
| Email | aiosmtplib 3.0, httpx 0.28 (SES/Mailgun/SendGrid API) |
| Reporting | WeasyPrint 63 (PDF), openpyxl 3.1 (Excel) |
| AI | Anthropic Claude API (optional), MCP protocol |
| Testing | pytest 8, pytest-asyncio, factory-boy |
| Deployment | Docker, Docker Compose |
