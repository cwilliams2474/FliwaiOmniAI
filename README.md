# OmniAI 3.1

Self-hosted AI and IT operations platform: AI chat that answers from your company documents, persistent memory, IT tickets, asset management, organizations with roles, MFA, and a full audit log. It runs on one Ubuntu server with Docker Compose.

```
Browser ──► Caddy (HTTPS) ──┬─ /api/* ──► backend  (FastAPI, Python 3.12) ──► PostgreSQL 16
                            └─ /*     ──► frontend (Next.js 14)              └─ uploads volume
                                         backend ──► AI provider (OpenAI-compatible, Anthropic, or none)
```

## What's in this release

| Module | What it does |
|---|---|
| Sign-in & security | Email + password (bcrypt), TOTP MFA with QR enrolment and 10 single-use recovery codes, password reset by email, rate-limited sign-in, server-side sessions you can see and revoke, forced password change for invited users |
| Organizations | Separate data per organization. Roles: owner, admin, technician, member, viewer. Last-owner protection; only owners grant owner |
| AI Chat | Private, saved conversations. Each question searches the organization's documents and memory, sends the best passages to the model and shows which sources it cited. With no model configured it returns the matching passages instead |
| Documents | Upload PDF, Word, HTML, Markdown, CSV and text. Text is split into passages and indexed with PostgreSQL full-text search. Duplicate detection by SHA-256 |
| Memory | Short organization facts (maintenance window, key servers, escalation contacts) included in every AI answer |
| IT Tickets | Per-org numbering (IT-1001…), priorities P1–P4, status, assignment, public replies and internal notes, related asset, related knowledge lookup. Members see only their own tickets |
| Assets | Tag (auto-generated if blank), type, OS, owner, location, serial, warranty with 60-day expiry flag, open-ticket count |
| Administration | Members and roles, add people with temporary passwords, sign a user out everywhere, reset a user's MFA, audit log with search, usage numbers, system health page |
| Backups | Database + uploaded-file backups with SHA-256 checksums, verification, isolated test restore, and a guarded production restore |
| **AI Agents** (3.1) | An admin defines an agent: instructions, an allow-list of tools, an approval mode and a step limit (max 10). Given a goal, the agent's AI model plans the steps up front; a plan that uses a tool outside the allow-list is refused before anything runs |
| **Agent runtime** (3.1) | Every agent or workflow run is a numbered list of steps with a recorded status. Steps that change things wait for an admin to approve or reject, with a note. A failed or rejected step stops the run and marks the rest skipped. Nothing retries automatically. Every decision is in the audit log |
| **Workflows & scheduling** (3.1) | Fixed step lists that run on demand or on a cron schedule (e.g. `0 7 * * 1-5`), in your time zone and DST-safe. Later steps can use earlier results with `{{step 1}}` and `{{date}}`. A scheduled run is skipped if the previous one is still waiting. Templates: morning priority digest, warranty check, stale-ticket nudge |
| **Integrations** (3.1) | Slack, Microsoft Teams and generic JSON webhooks, per organization. URLs and auth headers are encrypted with `ENCRYPTION_KEY` and never returned by the API. Test button and last-result status |
| **Notifications** (3.1) | In-app alerts with an unread badge: new tickets, assignments, replies, resolutions, approvals needed, failed runs. Assignments, replies to requesters, approvals and failed scheduled runs are also emailed when SMTP is set up |
| **Customer portal** (3.1) | People with the member role (employees or a customer's staff) get a simpler support view: send a request, follow their requests, ask the AI, see notifications. Add a customer as its own organization and give your technicians a role there |

Not in this release yet (planned next): Codex development workspace, billing, SSO/OIDC, Prometheus metrics, inbound email-to-ticket.

### Tools agents and workflows can use

| Tool | Changes things? | What it does |
|---|---|---|
| `tickets.search` | no | Find tickets by status, priority, text, age, unassigned |
| `tickets.get` | no | Read one ticket and its recent public replies |
| `assets.search` | no | Find assets by text or warranty end date |
| `knowledge.search` | no | Search documents |
| `memory.list` | no | Read organization memory |
| `ai.summarize` | no | Have the model summarize earlier results (needs an AI model) |
| `tickets.create` | yes | Create a ticket |
| `tickets.comment` | yes | Add an internal note (default) or a reply |
| `tickets.update` | yes | Change status or priority |
| `notify.team` | yes | In-app notification to members of a role or higher |
| `integration.send` | yes | Post to a Slack, Teams or webhook integration |

Approval modes: **writes** (default: approve every step marked "yes" above), **all**, or **none**. Only admins and owners approve. Technicians can start runs; whoever started a run, or an admin, can cancel it.

## Install on Ubuntu 22.04 / 24.04

**1. Install Docker** (skip if `docker compose version` already works):

```bash
sudo apt update && sudo apt install -y ca-certificates curl openssl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER   # then log out and back in
```

**2. Put the code on the server**, for example in `/opt/omniai`, and run the installer:

```bash
cd /opt/omniai
./scripts/install.sh
```

It asks for a domain name. With a domain (DNS pointing at the server, ports 80 and 443 open) you get automatic HTTPS. Leave it blank to run plain HTTP on port 80 inside your LAN.

**3. Open `https://your-domain/setup`** and create the first organization and owner account. Then, on the Account page, turn on MFA.

**4. Back up `.env`** somewhere safe (a password manager). It holds the database password and the key that encrypts MFA seeds.

## Connect an AI model

Edit `.env`, then `docker compose up -d backend`.

```bash
# OpenAI
AI_PROVIDER=openai
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini

# Fully local with Ollama running on the same server
AI_PROVIDER=openai
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=
AI_MODEL=llama3.1:8b

# Anthropic
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-...
AI_MODEL=<model id from docs.claude.com>
```

The System health page shows which provider is active. With `AI_PROVIDER=none`, chat still works and shows the matching passages from your documents.

## Upgrading from 3.0

Copy the new code over the old (keep `.env`), then:

```bash
./scripts/backup.sh
docker compose build && docker compose up -d   # applies migration 0002 automatically
```

Add `SCHEDULER_TIMEZONE=America/New_York` (or your zone) to `.env` if it isn't there.

## Day-to-day operations

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f backend` |
| Update to new code | `git pull && docker compose build && docker compose up -d` (migrations run automatically) |
| Locked-out owner: new password | `docker compose exec backend python -m app.cli reset-password you@example.com` |
| Lost MFA device | `docker compose exec backend python -m app.cli reset-mfa you@example.com` |
| List accounts | `docker compose exec backend python -m app.cli list-users` |

If email isn't configured, password-reset links are written to the backend log: `docker compose logs backend | grep reset-password`.

## Backups and restores

```bash
./scripts/backup.sh                                   # database + uploads, checksummed, verified, 14-day retention
./scripts/verify-backup.sh backups/20261017-020000    # checksums + archives readable
./scripts/restore-test.sh  backups/20261017-020000    # restore into a throwaway isolated container and check it
./scripts/restore-production.sh backups/20261017-020000
```

Nightly at 02:00:

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/omniai/scripts/backup.sh >> /var/log/omniai-backup.log 2>&1") | crontab -
```

Safeguards on a production restore: the backup must pass verification **and** a test restore first, you must type `RESTORE PRODUCTION`, and a fresh safety backup of the current state is taken before anything is replaced. Copy the `backups/` folder off the server (another machine, NAS or object storage); a backup on the same disk doesn't survive a disk failure.

## Roles

| Role | Can |
|---|---|
| Owner | Everything, including managing other owners |
| Admin | Members and roles (except owners), org settings, audit log, delete assets and any document |
| Technician | Work all tickets, internal notes, manage assets, upload documents, edit memory |
| Member | Raise and follow their own tickets, use AI chat |
| Viewer | Read everything, change nothing |

Automation: technicians start agent and workflow runs; admins create agents, workflows and integrations and approve or reject steps. Members get the support portal.

## Development

```bash
# backend (needs a local PostgreSQL 16)
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
createdb omniai_test
TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/omniai_test pytest

DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/omniai ENVIRONMENT=development \
  SECRET_KEY=dev-secret-key-dev-secret-key-1234 COOKIE_SECURE=false UPLOAD_DIR=./uploads \
  sh -c "alembic upgrade head && uvicorn app.main:app --reload"
# API docs: http://localhost:8000/api/docs (development only)

# frontend
cd frontend && npm install && npm run dev   # http://localhost:3000, proxies /api to :8000
```

New database changes: edit `backend/app/models.py`, then `alembic revision --autogenerate -m "describe change"` and review the generated file.
