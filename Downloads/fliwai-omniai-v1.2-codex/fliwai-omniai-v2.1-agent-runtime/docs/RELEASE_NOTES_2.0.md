# FLIWAI OmniAI v2.0 Final Release Notes

## Final changes from RC1

- Promoted application version from `2.0.0-rc1` to `2.0.0`.
- Advanced journaled schema marker from 200 to 201 (`v2.0-final`).
- Added native Ubuntu/Linux `backup.sh`, `verify-backup.sh`, `restore.sh`, and `smoke-test.sh`.
- Added path-safe checksum verification and explicit destructive restore confirmation.
- Added backup tamper-detection verification.
- Replaced deprecated `datetime.utcnow()` usage with a UTC helper compatible with Python 3.13 while preserving the existing naive-UTC database contract.
- Added Node/npm toolchain constraints and kept all direct dependencies exact-pinned.
- Added Bash syntax validation to CI.
- Moved the default optional Grafana host port to 3002 to avoid common application-port collisions; override with `GRAFANA_PORT`.
- Reworked operator, recovery, and release documentation around Ubuntu-first deployment.

## Known release gate that remains environment-dependent

The packaging environment cannot resolve `@playwright/test` from its internal npm mirror, so a complete Next.js production build and browser E2E run cannot be truthfully claimed here. GitHub Actions and a normal npm-connected deployment environment are configured to perform those gates.
