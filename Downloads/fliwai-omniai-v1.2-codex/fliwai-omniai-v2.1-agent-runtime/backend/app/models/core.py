from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.time_utils import utcnow
from app.database.session import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default='')
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str] = mapped_column(String(128), default='')
    current_organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Chat(Base):
    __tablename__ = 'chats'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default='New Chat')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    messages = relationship('Message', back_populates='chat', cascade='all, delete-orphan')


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey('chats.id'))
    role: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    chat = relationship('Chat', back_populates='messages')


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DocumentChunk(Base):
    __tablename__ = 'document_chunks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('documents.id'), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(50), default='open')
    priority: Mapped[str] = mapped_column(String(50), default='normal')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(100), default='device')
    serial_number: Mapped[str] = mapped_column(String(255), default='')
    status: Mapped[str] = mapped_column(String(50), default='active')
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MemoryEntry(Base):
    __tablename__ = 'memory_entries'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    category: Mapped[str] = mapped_column(String(80), default='general')
    key: Mapped[str] = mapped_column(String(160))
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    system_prompt: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Workflow(Base):
    __tablename__ = 'workflows'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default='')
    steps_json: Mapped[str] = mapped_column(Text, default='[]')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkflowRun(Base):
    __tablename__ = 'workflow_runs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey('workflows.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='running')
    input_text: Mapped[str] = mapped_column(Text, default='')
    output_json: Mapped[str] = mapped_column(Text, default='[]')
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), default='')
    entity_id: Mapped[str] = mapped_column(String(80), default='')
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CodeProject(Base):
    __tablename__ = 'code_projects'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CodeFile(Base):
    __tablename__ = 'code_files'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('code_projects.id'), index=True)
    path: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(80), default='text')
    content: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CodeTask(Base):
    __tablename__ = 'code_tasks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('code_projects.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    mode: Mapped[str] = mapped_column(String(40), default='ask')
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default='completed')
    result_json: Mapped[str] = mapped_column(Text, default='{}')
    model: Mapped[str] = mapped_column(String(120), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class AppSetting(Base):
    __tablename__ = 'app_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default='')
    updated_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class UsageEvent(Base):
    __tablename__ = 'usage_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    units: Mapped[int] = mapped_column(Integer, default=1)
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class IntegrationConnection(Base):
    __tablename__ = 'integration_connections'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    secret_encrypted: Mapped[str] = mapped_column(Text, default='')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkflowSchedule(Base):
    __tablename__ = 'workflow_schedules'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey('workflows.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    input_text: Mapped[str] = mapped_column(Text, default='')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default='')
    level: Mapped[str] = mapped_column(String(30), default='info')
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AgentToolPermission(Base):
    __tablename__ = 'agent_tool_permissions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey('integration_connections.id'), index=True)
    action: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OrganizationMember(Base):
    __tablename__ = 'organization_members'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    role: Mapped[str] = mapped_column(String(40), default='member')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), default='starter')
    status: Mapped[str] = mapped_column(String(40), default='active')
    seats: Mapped[int] = mapped_column(Integer, default=5)
    external_customer_id: Mapped[str] = mapped_column(String(255), default='')
    external_subscription_id: Mapped[str] = mapped_column(String(255), default='')
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PortalRequest(Base):
    __tablename__ = 'portal_requests'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(40), default='open')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class SecurityToken(Base):
    __tablename__ = 'security_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey('organizations.id'), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    email: Mapped[str] = mapped_column(String(255), default='')
    role: Mapped[str] = mapped_column(String(40), default='member')
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class AgentRun(Base):
    __tablename__ = 'agent_runs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default='planning', index=True)
    plan_json: Mapped[str] = mapped_column(Text, default='[]')
    summary: Mapped[str] = mapped_column(Text, default='')
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentRunStep(Base):
    __tablename__ = 'agent_run_steps'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('agent_runs.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(255), default='')
    config_json: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(40), default='pending', index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, default='{}')
    error: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CodeRevision(Base):
    __tablename__ = 'code_revisions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('code_projects.id'), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey('code_tasks.id'), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    path: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(80), default='text')
    previous_content: Mapped[str] = mapped_column(Text, default='')
    new_content: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
