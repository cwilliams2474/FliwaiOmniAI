"""IT tickets.

Visibility: members (requesters) see only tickets they raised and public comments.
Viewers see everything read-only. Technicians and above work tickets.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_db
from app.deps import OrgContext, get_org_ctx
from app.models import Asset, Membership, Organization, Priority, Role, Ticket, TicketComment, TicketStatus
from app.notify import members_with_role, notify
from app.schemas import UserBrief, iso

router = APIRouter(prefix="/tickets", tags=["tickets"])


class CommentOut(BaseModel):
    id: uuid.UUID
    author: UserBrief | None
    body: str
    internal: bool
    created_at: str


class TicketOut(BaseModel):
    id: uuid.UUID
    number: int
    key: str
    title: str
    description: str
    priority: str
    status: str
    requester: UserBrief | None
    assignee: UserBrief | None
    asset_id: uuid.UUID | None
    created_at: str
    updated_at: str
    resolved_at: str | None


class TicketDetail(TicketOut):
    comments: list[CommentOut]


class TicketPage(BaseModel):
    total: int
    items: list[TicketOut]


def _brief(u):
    return UserBrief.model_validate(u) if u else None


def _out(t: Ticket) -> dict:
    return dict(
        id=t.id,
        number=t.number,
        key=f"IT-{t.number}",
        title=t.title,
        description=t.description,
        priority=t.priority.value,
        status=t.status.value,
        requester=_brief(t.requester),
        assignee=_brief(t.assignee),
        asset_id=t.asset_id,
        created_at=iso(t.created_at),
        updated_at=iso(t.updated_at),
        resolved_at=iso(t.resolved_at),
    )


def _is_requester_only(ctx: OrgContext) -> bool:
    return ctx.role == Role.member


def _get(db: Session, ctx: OrgContext, number: int) -> Ticket:
    t = db.scalar(select(Ticket).where(Ticket.org_id == ctx.org.id, Ticket.number == number))
    if not t or (_is_requester_only(ctx) and t.requester_id != ctx.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ticket IT-{number} not found.")
    return t


def _check_member(db: Session, ctx: OrgContext, user_id: uuid.UUID | None) -> None:
    if user_id and not db.scalar(select(Membership.id).where(Membership.org_id == ctx.org.id, Membership.user_id == user_id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The assignee must be a member of this organization.")


def _check_asset(db: Session, ctx: OrgContext, asset_id: uuid.UUID | None) -> None:
    if asset_id and not db.scalar(select(Asset.id).where(Asset.org_id == ctx.org.id, Asset.id == asset_id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That asset isn't in this organization.")


@router.get("", response_model=TicketPage)
def list_tickets(
    ctx: OrgContext = Depends(get_org_ctx),
    db: Session = Depends(get_db),
    status_: list[TicketStatus] = Query(default=[], alias="status"),
    priority: Priority | None = None,
    assignee: str | None = Query(default=None, description="'me', 'none', or a user id"),
    q: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    stmt = select(Ticket).where(Ticket.org_id == ctx.org.id)
    if _is_requester_only(ctx):
        stmt = stmt.where(Ticket.requester_id == ctx.user.id)
    if status_:
        stmt = stmt.where(Ticket.status.in_(status_))
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if assignee == "me":
        stmt = stmt.where(Ticket.assignee_id == ctx.user.id)
    elif assignee == "none":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif assignee:
        try:
            stmt = stmt.where(Ticket.assignee_id == uuid.UUID(assignee))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assignee must be 'me', 'none' or a user id.")
    if q:
        like = f"%{q}%"
        conds = [Ticket.title.ilike(like), Ticket.description.ilike(like)]
        digits = q.upper().removeprefix("IT-")
        if digits.isdigit():
            conds.append(Ticket.number == int(digits))
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Ticket.priority, Ticket.created_at.desc()).limit(limit).offset(offset))
    return TicketPage(total=total, items=[TicketOut(**_out(t)) for t in rows])


class TicketIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=20000)
    priority: Priority = Priority.p3
    assignee_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None


@router.post("", response_model=TicketDetail, status_code=201)
def create_ticket(body: TicketIn, request: Request, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    if ctx.role == Role.viewer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers can't create tickets.")
    if _is_requester_only(ctx) and body.assignee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only technicians can assign tickets.")
    _check_member(db, ctx, body.assignee_id)
    _check_asset(db, ctx, body.asset_id)
    org = db.scalar(select(Organization).where(Organization.id == ctx.org.id).with_for_update())
    org.ticket_seq += 1
    t = Ticket(
        org_id=org.id,
        number=org.ticket_seq,
        title=body.title.strip(),
        description=body.description,
        priority=body.priority,
        requester_id=ctx.user.id,
        assignee_id=body.assignee_id,
        asset_id=body.asset_id,
    )
    db.add(t)
    record(db, "ticket.created", f"IT-{t.number} {t.title}", user=ctx.user, org_id=org.id, request=request)
    link = f"/tickets/{t.number}"
    if t.assignee_id:
        notify(db, org.id, [t.assignee_id], "ticket.assigned", f"IT-{t.number} assigned to you: {t.title}", t.description[:300], link, exclude=ctx.user.id, email=True)
    else:
        notify(db, org.id, members_with_role(db, org.id, Role.technician), "ticket.new", f"New {t.priority.value} ticket IT-{t.number}: {t.title}",
               f"Raised by {ctx.user.name}.", link, exclude=ctx.user.id, email=t.priority in (Priority.p1, Priority.p2))
    db.commit()
    db.refresh(t)
    return TicketDetail(**_out(t), comments=[])


@router.get("/{number}", response_model=TicketDetail)
def get_ticket(number: int, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, number)
    show_internal = ctx.at_least(Role.technician) or ctx.role == Role.viewer
    comments = [
        CommentOut(id=c.id, author=_brief(c.author), body=c.body, internal=c.internal, created_at=iso(c.created_at))
        for c in t.comments
        if show_internal or not c.internal
    ]
    return TicketDetail(**_out(t), comments=comments)


class TicketPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    priority: Priority | None = None
    status: TicketStatus | None = None
    assignee_id: uuid.UUID | None = None
    unassign: bool = False
    asset_id: uuid.UUID | None = None


@router.patch("/{number}", response_model=TicketDetail)
def update_ticket(number: int, body: TicketPatch, request: Request, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    t = _get(db, ctx, number)
    tech = ctx.at_least(Role.technician)
    own = t.requester_id == ctx.user.id and ctx.role != Role.viewer
    changes: dict[str, str] = {}
    if body.title is not None or body.description is not None:
        if not (tech or own):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't edit this ticket.")
        if body.title is not None and body.title != t.title:
            changes["title"] = body.title
            t.title = body.title.strip()
        if body.description is not None and body.description != t.description:
            changes["description"] = "updated"
            t.description = body.description
    work_fields = [body.priority, body.status, body.assignee_id, body.asset_id]
    if any(v is not None for v in work_fields) or body.unassign:
        if not tech:
            # Requesters may close or reopen their own ticket, nothing else.
            if own and body.status in (TicketStatus.closed, TicketStatus.open) and not any(v is not None for v in [body.priority, body.assignee_id, body.asset_id]):
                pass
            else:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Only technicians can change priority, status or assignment.")
        if body.priority and body.priority != t.priority:
            changes["priority"] = f"{t.priority.value} → {body.priority.value}"
            t.priority = body.priority
        if body.status and body.status != t.status:
            changes["status"] = f"{t.status.value} → {body.status.value}"
            t.status = body.status
            if body.status in (TicketStatus.resolved, TicketStatus.closed):
                t.resolved_at = t.resolved_at or datetime.now(timezone.utc)
            else:
                t.resolved_at = None
        if body.unassign and t.assignee_id:
            changes["assignee"] = "unassigned"
            t.assignee_id = None
        elif body.assignee_id and body.assignee_id != t.assignee_id:
            _check_member(db, ctx, body.assignee_id)
            changes["assignee"] = str(body.assignee_id)
            t.assignee_id = body.assignee_id
        if body.asset_id and body.asset_id != t.asset_id:
            _check_asset(db, ctx, body.asset_id)
            changes["asset"] = str(body.asset_id)
            t.asset_id = body.asset_id
    if changes:
        record(db, "ticket.updated", f"IT-{t.number}", user=ctx.user, org_id=ctx.org.id, detail=changes, request=request)
        link = f"/tickets/{t.number}"
        if "assignee" in changes and t.assignee_id:
            notify(db, ctx.org.id, [t.assignee_id], "ticket.assigned", f"IT-{t.number} assigned to you: {t.title}", f"Assigned by {ctx.user.name}.", link, exclude=ctx.user.id, email=True)
        if "status" in changes and t.status in (TicketStatus.resolved, TicketStatus.closed):
            notify(db, ctx.org.id, [t.requester_id], "ticket.resolved", f"IT-{t.number} was {t.status.value}: {t.title}", f"By {ctx.user.name}. Reopen it if the problem isn't fixed.", link, exclude=ctx.user.id, email=True)
        db.commit()
        db.refresh(t)
    return get_ticket(number, ctx, db)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    internal: bool = False


@router.post("/{number}/comments", response_model=TicketDetail, status_code=201)
def add_comment(number: int, body: CommentIn, request: Request, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    if ctx.role == Role.viewer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers can't comment.")
    t = _get(db, ctx, number)
    if body.internal and not ctx.at_least(Role.technician):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only technicians can add internal notes.")
    db.add(TicketComment(ticket_id=t.id, author_id=ctx.user.id, body=body.body, internal=body.internal))
    t.updated_at = datetime.now(timezone.utc)
    record(db, "ticket.commented", f"IT-{t.number}", user=ctx.user, org_id=ctx.org.id, detail={"internal": body.internal}, request=request)
    link = f"/tickets/{t.number}"
    preview = body.body[:300]
    if body.internal:
        notify(db, ctx.org.id, [t.assignee_id], "ticket.note", f"Internal note on IT-{t.number}", f"{ctx.user.name}: {preview}", link, exclude=ctx.user.id)
    elif ctx.user.id == t.requester_id:
        to = [t.assignee_id] if t.assignee_id else members_with_role(db, ctx.org.id, Role.technician)
        notify(db, ctx.org.id, to, "ticket.reply", f"{ctx.user.name} replied on IT-{t.number}", preview, link, exclude=ctx.user.id)
    else:
        notify(db, ctx.org.id, [t.requester_id], "ticket.reply", f"New reply on your ticket IT-{t.number}", f"{ctx.user.name}: {preview}", link, exclude=ctx.user.id, email=True)
    db.commit()
    db.refresh(t)
    return get_ticket(number, ctx, db)
