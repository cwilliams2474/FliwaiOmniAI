"""3.1: notifications, integrations, agents, workflows, runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TS = sa.DateTime(timezone=True)

runstatus = sa.Enum("running", "awaiting_approval", "completed", "failed", "rejected", "cancelled", name="runstatus")
stepstatus = sa.Enum("pending", "awaiting_approval", "approved", "running", "succeeded", "failed", "rejected", "skipped", name="stepstatus")
# approvalmode is used by three tables, so create it once explicitly.
approvalmode = postgresql.ENUM("writes", "all", "none", name="approvalmode", create_type=False)
approvalmode_create = postgresql.ENUM("writes", "all", "none", name="approvalmode")


def upgrade() -> None:
    op.add_column("organizations", sa.Column("run_seq", sa.Integer, nullable=False, server_default="0"))
    approvalmode_create.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("link", sa.String(300), nullable=False),
        sa.Column("read_at", TS),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "org_id", "read_at"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "integrations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("secret_enc", sa.Text, nullable=False),
        sa.Column("secret_hint", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("last_ok", sa.Boolean),
        sa.Column("last_error", sa.Text, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("org_id", "name"),
    )
    op.create_index("ix_integrations_org_id", "integrations", ["org_id"])

    op.create_table(
        "agents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("instructions", sa.Text, nullable=False),
        sa.Column("tools", sa.JSON, nullable=False),
        sa.Column("approval_mode", approvalmode, nullable=False),
        sa.Column("max_steps", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("created_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("org_id", "name"),
    )
    op.create_index("ix_agents_org_id", "agents", ["org_id"])

    op.create_table(
        "workflows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("steps", sa.JSON, nullable=False),
        sa.Column("schedule", sa.String(100), nullable=False),
        sa.Column("approval_mode", approvalmode, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("next_run_at", TS),
        sa.Column("last_run_at", TS),
        sa.Column("created_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("org_id", "name"),
    )
    op.create_index("ix_workflows_org_id", "workflows", ["org_id"])
    op.create_index("ix_workflows_next_run_at", "workflows", ["next_run_at"])

    op.create_table(
        "runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("agent_id", UUID, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("workflow_id", UUID, sa.ForeignKey("workflows.id", ondelete="SET NULL")),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("approval_mode", approvalmode, nullable=False),
        sa.Column("status", runstatus, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("started_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("finished_at", TS),
        sa.UniqueConstraint("org_id", "number"),
    )
    op.create_index("ix_runs_org_id", "runs", ["org_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])

    op.create_table(
        "run_steps",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("run_id", UUID, sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("tool", sa.String(60), nullable=False),
        sa.Column("args", sa.JSON, nullable=False),
        sa.Column("why", sa.Text, nullable=False),
        sa.Column("requires_approval", sa.Boolean, nullable=False),
        sa.Column("status", stepstatus, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("decided_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", TS),
        sa.Column("decision_note", sa.Text, nullable=False),
        sa.Column("started_at", TS),
        sa.Column("finished_at", TS),
        sa.UniqueConstraint("run_id", "ordinal"),
    )
    op.create_index("ix_run_steps_run_id", "run_steps", ["run_id"])


def downgrade() -> None:
    for t in ("run_steps", "runs", "workflows", "agents", "integrations", "notifications"):
        op.drop_table(t)
    for e in (stepstatus, runstatus, approvalmode_create):
        e.drop(op.get_bind(), checkfirst=True)
    op.drop_column("organizations", "run_seq")
