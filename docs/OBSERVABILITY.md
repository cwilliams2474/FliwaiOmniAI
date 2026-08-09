# Observability

OmniAI v2.0 emits structured JSON request logs to stdout and exposes two monitoring surfaces:

- `GET /monitoring/metrics` — authenticated administrator summary for the application UI.
- `GET /monitoring/prometheus` — Prometheus text format. In production it requires `Authorization: Bearer <METRICS_TOKEN>` or `X-Metrics-Token`.

Every HTTP response includes `X-Request-ID`; the same identifier is included in request completion logs. Preserve that value when tracing user-reported failures.

## Optional local Prometheus + Grafana

1. Generate a long random `METRICS_TOKEN` and place it in `.env`.
2. Create `secrets/metrics_token` with exactly the same value and no extra explanatory text.
3. Set a strong `GRAFANA_ADMIN_PASSWORD` in `.env`.
4. Start the application plus observability stack:

   `docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build`

5. Grafana is intentionally bound to localhost only at `http://localhost:${GRAFANA_PORT:-3002}`.

For public production monitoring, put Grafana behind your identity-aware access layer rather than publishing Grafana directly directly.

## Initial alerts to configure

- readiness probe unavailable for 2 consecutive minutes;
- HTTP 5xx rate above 2% for 5 minutes;
- sustained request latency materially above your normal baseline;
- PostgreSQL disk usage above 80%;
- backup verification has not succeeded within the expected RPO window.
