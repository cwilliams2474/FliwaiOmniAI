# Production Operations Runbook

## Deploy

1. Rehearse the release against a copy of production data.
2. Verify a fresh backup using `scripts/verify-backup.sh`.
3. Pull/copy the approved release artifact to the host.
4. Preserve the existing `.env` and `JWT_SECRET`; merge newly required settings deliberately.
5. Run `docker compose -f docker-compose.prod.yml up -d --build`.
6. Confirm `docker compose -f docker-compose.prod.yml ps` reports healthy services.
7. Verify public `/api/health/live`, `/api/health/ready`, and `/api/health/deep` through HTTPS.
8. Test administrator login, normal-member login, tenant switching, and one critical workflow.

## Rollback

The v2.0 release-candidate migration is additive, but rollback still requires care because newer writes may use newer schema/data expectations. Prefer application rollback only after confirming compatibility. If data rollback is required, restore a **verified pre-deploy backup** into a controlled target rather than manually deleting migration state.

## Logs

Use `docker compose -f docker-compose.prod.yml logs -f backend` for immediate diagnostics. Backend request completion records are JSON and include `request_id`, normalized path, status, and latency. Match `X-Request-ID` from a failed browser/API response to the backend log record.

## Monitoring

Monitor liveness, readiness, and deep health. The optional Prometheus/Grafana overlay is documented in `docs/OBSERVABILITY.md`.

## Incident triage order

1. Certificate/DNS/reverse proxy.
2. Container health and recent restarts.
3. `/health/ready` schema/database state.
4. `/health/deep` upload-storage state.
5. Backend request logs using request ID.
6. PostgreSQL capacity/connections.
7. External provider status only after local boundaries are healthy.
