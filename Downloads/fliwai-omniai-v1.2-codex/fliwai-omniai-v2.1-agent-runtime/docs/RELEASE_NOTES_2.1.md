# FLIWAI OmniAI 2.1 Release Notes

## Agent Runtime 2.0

- Added persistent agent runs and per-step execution history.
- Agents generate bounded plans using only supported internal step types.
- Permitted external integration actions are organization-scoped and require explicit approval before execution.
- Approval and rejection events are audited.
- Runs stop safely on rejected approvals or failed steps.

## Codex 2.0

- Added unified diff previews for proposed file changes.
- Applying a Codex implementation now records per-file revision snapshots.
- Added guarded rollback that refuses to overwrite files changed after the selected revision.
- Existing safe-relative-path protections remain in force.

## Platform

- Application version: `2.1.0`.
- Schema journal: `210` (`v2.1-agent-runtime`).
- Existing v2.0 data remains compatible; new tables are additive.
