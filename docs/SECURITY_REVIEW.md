# v2.0 Security Review Notes

## Trust boundaries

1. Browser to Caddy/HTTPS.
2. Caddy to frontend/backend on the private Docker network.
3. Backend to PostgreSQL.
4. Backend to external AI/integration providers.
5. Scheduler/workflow engine to permission-scoped integration actions.
6. Codex virtual workspace to proposed file changes; the browser does not receive arbitrary host-shell execution.

## Controls present

- JWT sessions with server-side token-version revocation.
- MFA/TOTP and one-time expiring security tokens.
- Organization-scoped operational records and membership checks.
- Admin-gated platform operations.
- Rate limiting and security response headers.
- Encrypted connector/MFA secrets derived from the deployment secret.
- SSRF restrictions for generic webhooks.
- Codex path traversal protections and explicit apply step.
- Dedicated production metrics token.
- Structured request logs with request correlation IDs.
- Checksummed backup bundles with restore confirmation.

## Release-candidate limitations

- In-process rate limiting and request metrics reset when the backend restarts and do not coordinate across multiple backend replicas. Use Redis or an API gateway before horizontal scaling.
- The v1-to-v2 migration system is additive and journaled but is not a full reversible migration framework. Production upgrades must be rehearsed against a database copy and paired with a verified backup.
- Integration credentials depend on the existing `JWT_SECRET` derivation. Secret rotation requires a planned connector-secret migration or re-entry.
- Billing and OIDC require provider-specific production configuration and end-to-end validation in the target environment.
- The application still needs an independent penetration test before handling high-sensitivity customer workloads.
