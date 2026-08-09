# FLIWAI OmniAI

## v2.1 highlights

- Agent Runtime 2.0 with persisted plans, step state, approval gates, and organization-scoped runs.
- External integration actions pause for explicit user approval before execution.
- Codex 2.0 adds unified diff previews, revision snapshots, and guarded rollback.
- Dashboard includes an Agents workspace with live run/approval history.
 v2.0 Final

FLIWAI OmniAI is a locally deployable AI operating platform combining authenticated AI chat, document RAG, IT operations, multi-organization tenancy, workflows, integrations, notifications, enterprise security, a sandboxed Codex-style development workspace, customer portal capabilities, and SaaS foundations.

v2.0 Final closes the release-candidate gaps around Linux operations, recovery, release evidence, and runtime maintenance. It does **not** claim regulatory certification or replace an independent penetration test for high-sensitivity deployments.

## v2.0 Final highlights

- Journaled, idempotent upgrade path with explicit schema version `210` (`v2.1-agent-runtime`).
- Schema-aware readiness and deep health checks for database and upload storage.
- Structured JSON HTTP logs with `X-Request-ID` correlation.
- In-process request/error/latency metrics plus token-protected Prometheus export.
- Optional Prometheus + Grafana Docker overlay.
- Checksummed PostgreSQL + uploaded-file backup bundles.
- Native Ubuntu/Linux backup, verification, restore, and smoke-test scripts.
- Guarded destructive restore requiring `--confirm-restore`.
- Playwright desktop and mobile Chromium E2E projects.
- GitHub Actions gates for backend tests, compilation, frontend build, dependency audit, browser E2E, and Bash script syntax.
- Python 3.13-safe UTC timestamp helper for legacy naive-UTC database columns.
- Existing MFA, password recovery, OIDC foundation, invitations, Stripe Checkout adapter, tenant isolation, Codex guardrails, workflows, and integrations remain in place.

## Upgrade from v2.0 RC1 or v1.8

Preserve your existing `.env`, PostgreSQL Docker volume, upload volume, and especially your existing `JWT_SECRET`.

On Ubuntu, from the project root:

```bash
docker compose down
docker compose up -d --build
./scripts/smoke-test.sh
```

The no-argument smoke test checks FastAPI from inside the backend container, so it is independent of host port mappings.

After upgrade, `/health/ready` reports `schema_version: 210` internally when the final migration journal is current.

## First-time Ubuntu setup

```bash
cp .env.example .env
nano .env
docker compose up -d --build
./scripts/smoke-test.sh
```

Set at minimum:

- `POSTGRES_PASSWORD`
- the matching password inside `DATABASE_URL`
- a long random `JWT_SECRET`
- `OPENAI_API_KEY` when AI features are required

Open the application using the frontend host port configured for your environment. Your current Ubuntu installation can continue using its existing Docker port overrides.

## Production HTTPS

Copy `.env.production.example` to `.env`, replace every placeholder, point DNS at the host, and run:

```bash
cp .env.production.example .env
nano .env
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy terminates HTTPS and forwards `/api/*` to FastAPI. PostgreSQL and FastAPI are not directly published in the production Compose file.

## Observability

Administrators can view summarized application metrics at `/monitoring/metrics`. Prometheus can scrape `/monitoring/prometheus`; in production this endpoint requires `METRICS_TOKEN` rather than a user session.

To use the optional Prometheus/Grafana overlay, set `METRICS_TOKEN` and `GRAFANA_ADMIN_PASSWORD`, create `secrets/metrics_token` containing the same metrics token, then run:

```bash
printf '%s' "$METRICS_TOKEN" > secrets/metrics_token
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
```

Grafana defaults to localhost port 3002 and can be changed with `GRAFANA_PORT`. See `docs/OBSERVABILITY.md`.

## Backup and recovery on Ubuntu

Create a database + uploads backup bundle:

```bash
./scripts/backup.sh
```

Verify it:

```bash
./scripts/verify-backup.sh ./backups/omniai-backup-YYYYMMDD-HHMMSS
```

Restore requires an explicit destructive-action switch:

```bash
./scripts/restore.sh ./backups/omniai-backup-YYYYMMDD-HHMMSS --confirm-restore
```

The Windows PowerShell equivalents remain in `scripts/` for cross-platform operators. Read `docs/DISASTER_RECOVERY.md` before restoring important data.

## Browser E2E

After installing frontend dependencies and Playwright Chromium:

```bash
cd frontend
npm install
npx playwright install --with-deps chromium
npm run e2e:chromium
```

Run both desktop and mobile projects with:

```bash
npm run e2e
```

## Release validation

From the repository root:

```bash
PYTHONPATH=backend pytest -q backend/tests backend/tests_test_*.py
python -m compileall -q backend/app
bash -n scripts/backup.sh scripts/verify-backup.sh scripts/restore.sh scripts/smoke-test.sh
./scripts/smoke-test.sh
```

Then complete `docs/RELEASE_CHECKLIST.md`, including a restore drill against a disposable environment.

## Dependency policy

Python and direct frontend dependencies are exact-version pinned. The frontend release expects Node 22 and npm 10. The packaging environment used for this build could not obtain `@playwright/test` from its internal npm mirror, so it could not generate a trustworthy `package-lock.json`; GitHub CI or your normal npm-connected environment remains the authority for the complete transitive dependency resolution. Do not fabricate or hand-edit a lockfile.

## Security boundaries

- Keep `.env` and runtime secrets out of source control.
- Preserve `JWT_SECRET`; stored integration secrets depend on a key derived from it.
- Codex edits only its virtual OmniAI project workspace and requires explicit apply; it does not expose arbitrary browser-to-host shell execution.
- Generic webhooks reject localhost/private-network destinations.
- Operational data is scoped to the authenticated user's active organization.
- MFA/security changes revoke existing sessions.
- Production Prometheus export requires a dedicated metrics token.
- The built-in rate limiter and metrics collector are single-process controls; introduce shared infrastructure before horizontally scaling backend replicas.
- Perform an independent penetration test before high-sensitivity or regulated production use.

## Verification performed for this package

- Backend test suite: 27/27 passed.
- Python source compilation: passed.
- Migration idempotence/schema journal test: passed with current schema constant `210`.
- Tenant isolation, Codex safety, MFA, security-token, scheduler, middleware, document, observability, and integration tests remain green.
- Bash operator scripts: syntax validation passed.
- Backup verifier: passed against an independently generated checksummed fixture.
- Frontend dependency installation/build could not execute in the packaging environment because its internal npm mirror does not provide `@playwright/test`; CI and your Docker/network environment remain the final browser/build gate.

## Release documentation

- `docs/RELEASE_CHECKLIST.md`
- `docs/SECURITY_REVIEW.md`
- `docs/DISASTER_RECOVERY.md`
- `docs/OBSERVABILITY.md`
- `docs/PRODUCTION_RUNBOOK.md`
