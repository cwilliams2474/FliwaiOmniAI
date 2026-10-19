"""Initial schema: identity, organizations, audit, tickets, assets, knowledge, chat.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TS = sa.DateTime(timezone=True)

role = sa.Enum("owner", "admin", "technician", "member", "viewer", name="role")
ticketstatus = sa.Enum("open", "in_progress", "waiting", "resolved", "closed", name="ticketstatus")
priority = sa.Enum("P1", "P2", "P3", "P4", name="priority")
assetstatus = sa.Enum("in_stock", "in_service", "repair", "retired", name="assetstatus")
docstatus = sa.Enum("processing", "indexed", "failed", name="docstatus")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("is_superuser", sa.Boolean, nullable=False),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False),
        sa.Column("mfa_secret_enc", sa.Text),
        sa.Column("recovery_codes", sa.JSON, nullable=False),
        sa.Column("must_change_password", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_login_at", TS),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("ticket_seq", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )

    op.create_table(
        "memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("user_id", "org_id"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(400)),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "password_resets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("used_at", TS),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="SET NULL")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(320), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("target", sa.String(400), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
        sa.Column("ip", sa.String(64)),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "assets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag", sa.String(60), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("asset_type", sa.String(60), nullable=False),
        sa.Column("os", sa.String(100), nullable=False),
        sa.Column("assigned_to_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("status", assetstatus, nullable=False),
        sa.Column("serial_number", sa.String(120), nullable=False),
        sa.Column("purchase_date", sa.Date),
        sa.Column("warranty_end", sa.Date),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("org_id", "tag"),
    )
    op.create_index("ix_assets_org_id", "assets", ["org_id"])

    op.create_table(
        "tickets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("priority", priority, nullable=False),
        sa.Column("status", ticketstatus, nullable=False),
        sa.Column("requester_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("assignee_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("asset_id", UUID, sa.ForeignKey("assets.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("resolved_at", TS),
        sa.UniqueConstraint("org_id", "number"),
    )
    op.create_index("ix_tickets_org_id", "tickets", ["org_id"])
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "ticket_comments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticket_id", UUID, sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("internal", sa.Boolean, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])

    op.create_table(
        "documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("status", docstatus, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("chunk_count", sa.Integer, nullable=False),
        sa.Column("uploaded_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("document_id", UUID, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR, sa.Computed("to_tsvector('english', content)", persisted=True)),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_org_id", "document_chunks", ["org_id"])
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["tsv"], postgresql_using="gin")

    op.create_table(
        "memory_entries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_memory_entries_org_id", "memory_entries", ["org_id"])

    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_conversations_org_id", "conversations", ["org_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON, nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    for t in (
        "chat_messages",
        "conversations",
        "memory_entries",
        "document_chunks",
        "documents",
        "ticket_comments",
        "tickets",
        "assets",
        "audit_logs",
        "password_resets",
        "auth_sessions",
        "memberships",
        "organizations",
        "users",
    ):
        op.drop_table(t)
    for e in (docstatus, assetstatus, priority, ticketstatus, role):
        e.drop(op.get_bind(), checkfirst=True)
