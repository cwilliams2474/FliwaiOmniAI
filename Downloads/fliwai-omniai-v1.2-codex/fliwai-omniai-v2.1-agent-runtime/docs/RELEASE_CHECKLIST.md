# v2.0 Final Release Checklist

A release is not production-approved until all applicable items are checked with fresh evidence.

## Build and automated verification

- [ ] Backend test suite passes.
- [ ] Backend Python compilation passes.
- [ ] Bash operator scripts pass `bash -n`.
- [ ] Next.js production build passes.
- [ ] Chromium Playwright E2E passes.
- [ ] Mobile Chromium Playwright project passes.
- [ ] Dependency audits have no unresolved high/critical findings.
- [ ] Docker images build from a clean checkout.

## Data and recovery

- [ ] Upgrade a copy of the previous production database and confirm readiness reports schema version 210.
- [ ] Run `./scripts/backup.sh` and checksum verification.
- [ ] Restore the verified backup into a disposable environment.
- [ ] Confirm database records and uploaded files after restore.
- [ ] Record measured RPO/RTO from the drill.

## Security

- [ ] Replace all example database/JWT/metrics/Grafana secrets.
- [ ] Configure HTTPS and confirm HSTS on the production hostname.
- [ ] Enable MFA for organization owners and platform administrators.
- [ ] Verify CORS contains only intended production origins.
- [ ] Verify SMTP, Stripe, OIDC, and integration secrets are not committed to Git.
- [ ] Confirm Prometheus scrape token is required in production.
- [ ] Review administrator accounts and organization membership.
- [ ] Test account disablement and session revocation.
- [ ] Complete an independent penetration test before regulated/high-sensitivity use.

## Operations

- [ ] `/health/live`, `/health/ready`, and `/health/deep` are monitored.
- [ ] Request logs are collected off-host or by the hosting platform.
- [ ] Prometheus/Grafana or equivalent monitoring is configured.
- [ ] Alerts exist for availability, 5xx error rate, resource pressure, and missed backups.
- [ ] Production domain DNS and certificate renewal have been verified.

## UX/accessibility

- [ ] Keyboard-only sign-in and primary navigation work.
- [ ] Focus indicators are visible.
- [ ] Dashboard is usable at mobile viewport widths.
- [ ] Forms expose accessible names.
- [ ] Error/status messages are announced to assistive technology.
