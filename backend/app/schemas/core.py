from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(default='', max_length=255)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_admin: bool
    is_active: bool = True
    mfa_enabled: bool = False
    model_config = {'from_attributes': True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserResponse


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    tool: str = Field(default='general', pattern='^(general|it|business|creative)$')
    chat_id: int | None = None
    agent_id: int | None = None


class AIChatResponse(BaseModel):
    response: str
    model: str
    chat_id: int


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_config = {'from_attributes': True}


class ChatSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    model_config = {'from_attributes': True}


class ChatDetail(ChatSummary):
    messages: list[MessageResponse]


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default='', max_length=10000)
    priority: str = Field(default='normal', pattern='^(low|normal|high|critical)$')


class TicketUpdate(BaseModel):
    status: str | None = Field(default=None, pattern='^(open|in_progress|resolved|closed)$')
    priority: str | None = Field(default=None, pattern='^(low|normal|high|critical)$')


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(default='device', max_length=100)
    serial_number: str = Field(default='', max_length=255)
    notes: str = Field(default='', max_length=10000)


class AssetUpdate(BaseModel):
    status: str | None = Field(default=None, pattern='^(active|maintenance|retired|lost)$')
    notes: str | None = Field(default=None, max_length=10000)


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


class AppSettingsUpdate(BaseModel):
    organization_name: str | None = Field(default=None, max_length=160)
    default_ai_model: str | None = Field(default=None, max_length=120)
    default_code_model: str | None = Field(default=None, max_length=120)



class DocumentAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    document_id: int | None = None


class DocumentAskResponse(BaseModel):
    answer: str
    model: str
    sources: list[dict[str, Any]]


class MemoryCreate(BaseModel):
    category: str = Field(default='general', max_length=80)
    key: str = Field(min_length=1, max_length=160)
    value: str = Field(min_length=1, max_length=12000)


class MemoryUpdate(BaseModel):
    category: str | None = Field(default=None, max_length=80)
    key: str | None = Field(default=None, min_length=1, max_length=160)
    value: str | None = Field(default=None, min_length=1, max_length=12000)


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=2000)
    system_prompt: str = Field(min_length=10, max_length=12000)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, min_length=10, max_length=12000)
    enabled: bool | None = None


class WorkflowStep(BaseModel):
    type: str = Field(pattern='^(ai_prompt|create_ticket|memory_write|integration_action|notify)$')
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default='', max_length=3000)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=20)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=3000)
    steps: list[WorkflowStep] | None = Field(default=None, min_length=1, max_length=20)
    enabled: bool | None = None


class WorkflowRunRequest(BaseModel):
    input_text: str = Field(default='', max_length=12000)


class CodeProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default='', max_length=3000)


class CodeFileUpsert(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    language: str = Field(default='text', max_length=80)
    content: str = Field(default='', max_length=200000)


class CodeTaskCreate(BaseModel):
    mode: str = Field(default='ask', pattern='^(ask|review|implement|test_plan)$')
    instruction: str = Field(min_length=2, max_length=20000)


class CodeTaskApplyResponse(BaseModel):
    task_id: int
    applied_files: list[str]


class IntegrationCreate(BaseModel):
    provider: str = Field(pattern='^(github|google|microsoft|webhook)$')
    name: str = Field(min_length=2, max_length=160)
    secret: str = Field(default='', max_length=10000)
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    secret: str | None = Field(default=None, max_length=10000)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class IntegrationActionRequest(BaseModel):
    action: str = Field(min_length=2, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowScheduleCreate(BaseModel):
    interval_minutes: int = Field(ge=5, le=10080)
    input_text: str = Field(default='', max_length=12000)


class NotificationUpdate(BaseModel):
    is_read: bool


class AgentToolPermissionCreate(BaseModel):
    connection_id: int
    action: str = Field(min_length=2, max_length=120)

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class OrganizationMemberAdd(BaseModel):
    email: EmailStr
    role: str = Field(default='member', pattern='^(owner|admin|member|customer)$')


class OrganizationMemberUpdate(BaseModel):
    role: str = Field(pattern='^(owner|admin|member|customer)$')


class OrganizationOnboardingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    onboarding_complete: bool | None = None


class SubscriptionUpdate(BaseModel):
    plan: str | None = Field(default=None, pattern='^(starter|professional|enterprise)$')
    status: str | None = Field(default=None, pattern='^(trialing|active|past_due|canceled)$')
    seats: int | None = Field(default=None, ge=1, le=100000)
    external_customer_id: str | None = Field(default=None, max_length=255)
    external_subscription_id: str | None = Field(default=None, max_length=255)


class PortalRequestCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=255)
    description: str = Field(default='', max_length=10000)

class MFAConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)

class OrganizationInviteCreate(BaseModel):
    email: EmailStr
    role: str = Field(default='member', pattern='^(admin|member|customer)$')

class OrganizationInviteAccept(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    full_name: str = Field(default='', max_length=255)
    password: str = Field(min_length=10, max_length=128)

class CheckoutCreate(BaseModel):
    plan: str = Field(pattern='^(starter|professional|enterprise)$')
    seats: int = Field(default=5, ge=1, le=100000)
