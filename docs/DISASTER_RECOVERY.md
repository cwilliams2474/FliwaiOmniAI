# OmniAI Disaster Recovery Runbook

## Recovery objectives

For the single-host Docker deployment, target an initial **RPO of 24 hours** and **RTO of 4 hours**. Tighter objectives require automated off-host backups and a tested standby environment.

## Ubuntu backup procedure

1. Run `./scripts/backup.sh` from the project root.
2. Run `./scripts/verify-backup.sh <created-folder>`.
3. Copy the verified bundle to encrypted off-host storage.
4. Keep `.env` / secret-management backups separate from application data. Never commit them to Git.

A valid bundle contains a PostgreSQL SQL dump, uploaded files, and a SHA-256 manifest that inventories every file.

## Ubuntu restore drill

Restore into a disposable environment first whenever possible:

```bash
./scripts/restore.sh <bundle> --confirm-restore
./scripts/smoke-test.sh
```

Then verify:

- `/health/live`, `/health/ready`, and `/health/deep`
- administrator sign-in and MFA
- one tenant's ticket/document data
- one uploaded document can be opened/indexed
- scheduled workflows are not duplicated

Record drill date, elapsed recovery time, operator, source backup timestamp, and any discrepancies.

## Windows operators

Equivalent `.ps1` backup, verification, restore, and smoke scripts remain in `scripts/`.

## Secret loss

The existing `JWT_SECRET` is also used to derive encryption for integration secrets. Losing or changing it makes stored connector secrets unreadable. Preserve it in an external secret vault and rotate connectors deliberately when rotating that secret.

## Incident rule

Do not restore a backup over the only production copy until the backup checksum passes and the target environment is explicitly confirmed.
