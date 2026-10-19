import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import security as sec
from app.audit import record
from app.config import get_settings
from app.db import get_db
from app.deps import OrgContext, get_current_user, get_org_ctx, require_role
from app.mailer import send_mail
from app.models import (
    AuditLog,
    AuthSession,
    ChatMessage,
    Conversation,
    Document,
    Membership,
    Organization,
    Priority,
    Role,
    Ticket,
    TicketStatus,
    User,
)
from app.routers.auth import unique_slug
from app.schemas import MeOut, Ok, iso, me_out

router = APIRouter(prefix="/orgs", tags=["organizations"])


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


@router.post("", response_model=MeOut)
def create_org(body: OrgCreateIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a platform administrator can create organizations.")
    org = Organization(name=body.name.strip(), slug=unique_slug(db, body.name))
    db.add(org)
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role=Role.owner))
    record(db, "org.created", org.name, user=user, org_id=org.id, request=request)
    db.commit()
    db.refresh(user)
    return me_out(user)


class OrgRenameIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


@router.patch("/current", response_model=Ok)
def rename_org(body: OrgRenameIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    old = ctx.org.name
    org = db.get(Organization, ctx.org.id)
    org.name = body.name.strip()
    record(db, "org.renamed", f"{old} → {org.name}", user=ctx.user, org_id=org.id, request=request)
    db.commit()
    return Ok()


# ---------- members ----------
class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    mfa_enabled: bool
    is_active: bool
    last_login_at: str | None


def _members(db: Session, org_id: uuid.UUID) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.org_id == org_id).order_by(User.name)
    ).all()
    return [
        MemberOut(user_id=u.id, name=u.name, email=u.email, role=m.role.value, mfa_enabled=u.mfa_enabled, is_active=u.is_active, last_login_at=iso(u.last_login_at))
        for m, u in rows
    ]


@router.get("/current/members", response_model=list[MemberOut])
def list_members(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return _members(db, ctx.org.id)


class InviteIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: Role = Role.member


class InviteOut(BaseModel):
    member: MemberOut
    temporary_password: str | None = None
    emailed: bool = False


def _guard_owner_change(ctx: OrgContext, *roles: Role) -> None:
    if Role.owner in roles and ctx.role != Role.owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an owner can grant or change the owner role.")


@router.post("/current/members", response_model=InviteOut)
def add_member(body: InviteIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    _guard_owner_change(ctx, body.role)
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    temp = None
    emailed = False
    if user:
        if db.scalar(select(Membership.id).where(Membership.user_id == user.id, Membership.org_id == ctx.org.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, f"{email} is already a member.")
    else:
        temp = "Omni-" + secrets.token_urlsafe(9) + "7a"
        user = User(email=email, name=body.name.strip(), password_hash=sec.hash_password(temp), must_change_password=True)
        db.add(user)
        db.flush()
    db.add(Membership(user_id=user.id, org_id=ctx.org.id, role=body.role))
    record(db, "member.added", f"{email} as {body.role.value}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    if temp:
        url = get_settings().public_url.rstrip("/")
        emailed = send_mail(
            email,
            f"You've been added to {ctx.org.name} on {get_settings().app_name}",
            f"{ctx.user.name} added you to {ctx.org.name}.\n\nSign in at {url}/login with:\nEmail: {email}\nTemporary password: {temp}\n\nYou'll be asked to choose a new password.",
        )
    m = next(x for x in _members(db, ctx.org.id) if x.user_id == user.id)
    return InviteOut(member=m, temporary_password=temp, emailed=emailed)


def _owner_count(db: Session, org_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(Membership.id)).where(Membership.org_id == org_id, Membership.role == Role.owner)) or 0


def _membership(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    m = db.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    return m


class RoleIn(BaseModel):
    role: Role


@router.patch("/current/members/{user_id}", response_model=Ok)
def change_role(user_id: uuid.UUID, body: RoleIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    m = _membership(db, ctx.org.id, user_id)
    _guard_owner_change(ctx, m.role, body.role)
    if m.role == Role.owner and body.role != Role.owner and _owner_count(db, ctx.org.id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "An organization needs at least one owner. Make someone else owner first.")
    old = m.role
    m.role = body.role
    record(db, "member.role_changed", f"{m.user.email}: {old.value} → {body.role.value}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    return Ok()


@router.delete("/current/members/{user_id}", response_model=Ok)
def remove_member(user_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    m = _membership(db, ctx.org.id, user_id)
    _guard_owner_change(ctx, m.role)
    if m.role == Role.owner and _owner_count(db, ctx.org.id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't remove the last owner.")
    email = m.user.email
    db.delete(m)
    record(db, "member.removed", email, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    return Ok()


def _only_here(db: Session, ctx: OrgContext, user_id: uuid.UUID) -> User:
    """Account-wide actions are allowed for org admins only when the person belongs to this org alone."""
    m = _membership(db, ctx.org.id, user_id)
    _guard_owner_change(ctx, m.role)
    others = db.scalar(select(func.count(Membership.id)).where(Membership.user_id == user_id, Membership.org_id != ctx.org.id)) or 0
    if others and not ctx.user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This person also belongs to other organizations. A platform administrator must do this.")
    return m.user


@router.post("/current/members/{user_id}/sign-out", response_model=Ok)
def sign_out_member(user_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    target = _only_here(db, ctx, user_id)
    now = datetime.now(timezone.utc)
    for s in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))):
        s.revoked_at = now
    record(db, "member.signed_out", target.email, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    return Ok()


@router.post("/current/members/{user_id}/reset-mfa", response_model=Ok)
def reset_member_mfa(user_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    target = _only_here(db, ctx, user_id)
    if target.id == ctx.user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use your own account page to change your MFA.")
    target.mfa_enabled = False
    target.mfa_secret_enc = None
    target.recovery_codes = []
    record(db, "member.mfa_reset", target.email, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    return Ok()


# ---------- audit & usage ----------
class AuditOut(BaseModel):
    id: int
    created_at: str
    actor: str
    action: str
    target: str
    ip: str | None
    detail: dict


class AuditPage(BaseModel):
    total: int
    items: list[AuditOut]


@router.get("/current/audit", response_model=AuditPage)
def audit_log(
    ctx: OrgContext = Depends(require_role(Role.admin)),
    db: Session = Depends(get_db),
    q: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    stmt = select(AuditLog).where(AuditLog.org_id == ctx.org.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(AuditLog.action.ilike(like) | AuditLog.target.ilike(like) | AuditLog.actor.ilike(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    return AuditPage(
        total=total,
        items=[AuditOut(id=a.id, created_at=iso(a.created_at), actor=a.actor, action=a.action, target=a.target, ip=a.ip, detail=a.detail or {}) for a in rows],
    )


class UsageOut(BaseModel):
    members: int
    open_tickets: int
    p1_open: int
    documents: int
    storage_bytes: int
    ai_messages_30d: int
    ai_tokens_30d: int


@router.get("/current/usage", response_model=UsageOut)
def usage(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    oid = ctx.org.id
    open_states = [TicketStatus.open, TicketStatus.in_progress, TicketStatus.waiting]
    since = datetime.now(timezone.utc) - timedelta(days=30)
    ai = db.execute(
        select(func.count(ChatMessage.id), func.coalesce(func.sum(ChatMessage.tokens_in + ChatMessage.tokens_out), 0))
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .where(Conversation.org_id == oid, ChatMessage.role == "assistant", ChatMessage.created_at >= since)
    ).one()
    return UsageOut(
        members=db.scalar(select(func.count(Membership.id)).where(Membership.org_id == oid)) or 0,
        open_tickets=db.scalar(select(func.count(Ticket.id)).where(Ticket.org_id == oid, Ticket.status.in_(open_states))) or 0,
        p1_open=db.scalar(select(func.count(Ticket.id)).where(Ticket.org_id == oid, Ticket.status.in_(open_states), Ticket.priority == Priority.p1)) or 0,
        documents=db.scalar(select(func.count(Document.id)).where(Document.org_id == oid)) or 0,
        storage_bytes=db.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.org_id == oid)) or 0,
        ai_messages_30d=ai[0] or 0,
        ai_tokens_30d=int(ai[1] or 0),
    )
