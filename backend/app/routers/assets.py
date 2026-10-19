import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_db
from app.deps import OrgContext, get_org_ctx, require_role
from app.models import Asset, AssetStatus, Membership, Role, Ticket, TicketStatus
from app.schemas import Ok, UserBrief, iso

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetOut(BaseModel):
    id: uuid.UUID
    tag: str
    name: str
    asset_type: str
    os: str
    assigned_to: UserBrief | None
    location: str
    status: str
    serial_number: str
    purchase_date: date | None
    warranty_end: date | None
    warranty_expiring: bool
    notes: str
    open_tickets: int = 0
    created_at: str
    updated_at: str


class AssetPage(BaseModel):
    total: int
    items: list[AssetOut]


def _out(a: Asset, open_tickets: int = 0) -> AssetOut:
    soon = date.today() + timedelta(days=60)
    return AssetOut(
        id=a.id,
        tag=a.tag,
        name=a.name,
        asset_type=a.asset_type,
        os=a.os,
        assigned_to=UserBrief.model_validate(a.assigned_to) if a.assigned_to else None,
        location=a.location,
        status=a.status.value,
        serial_number=a.serial_number,
        purchase_date=a.purchase_date,
        warranty_end=a.warranty_end,
        warranty_expiring=bool(a.warranty_end and a.warranty_end <= soon),
        notes=a.notes,
        open_tickets=open_tickets,
        created_at=iso(a.created_at),
        updated_at=iso(a.updated_at),
    )


def _get(db: Session, ctx: OrgContext, asset_id: uuid.UUID) -> Asset:
    a = db.scalar(select(Asset).where(Asset.org_id == ctx.org.id, Asset.id == asset_id))
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found.")
    return a


@router.get("", response_model=AssetPage)
def list_assets(
    ctx: OrgContext = Depends(require_role(Role.viewer)),
    db: Session = Depends(get_db),
    q: str = "",
    asset_type: str | None = None,
    status_: AssetStatus | None = Query(default=None, alias="status"),
    expiring: bool = False,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    if ctx.role == Role.member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Asset records are visible to IT staff only.")
    stmt = select(Asset).where(Asset.org_id == ctx.org.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Asset.tag.ilike(like), Asset.name.ilike(like), Asset.serial_number.ilike(like), Asset.location.ilike(like)))
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if status_:
        stmt = stmt.where(Asset.status == status_)
    if expiring:
        stmt = stmt.where(Asset.warranty_end.is_not(None), Asset.warranty_end <= date.today() + timedelta(days=60))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(stmt.order_by(Asset.tag).limit(limit).offset(offset)))
    counts = dict(
        db.execute(
            select(Ticket.asset_id, func.count(Ticket.id))
            .where(Ticket.asset_id.in_([a.id for a in rows]), Ticket.status.in_([TicketStatus.open, TicketStatus.in_progress, TicketStatus.waiting]))
            .group_by(Ticket.asset_id)
        ).all()
    ) if rows else {}
    return AssetPage(total=total, items=[_out(a, counts.get(a.id, 0)) for a in rows])


class AssetIn(BaseModel):
    tag: str = Field(default="", max_length=60)
    name: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(min_length=1, max_length=60)
    os: str = Field(default="", max_length=100)
    assigned_to_id: uuid.UUID | None = None
    location: str = Field(default="", max_length=200)
    status: AssetStatus = AssetStatus.in_stock
    serial_number: str = Field(default="", max_length=120)
    purchase_date: date | None = None
    warranty_end: date | None = None
    notes: str = Field(default="", max_length=10000)


def _check_assignee(db: Session, ctx: OrgContext, uid: uuid.UUID | None):
    if uid and not db.scalar(select(Membership.id).where(Membership.org_id == ctx.org.id, Membership.user_id == uid)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assign assets only to members of this organization.")


def _next_tag(db: Session, ctx: OrgContext, asset_type: str) -> str:
    prefix = "".join(c for c in asset_type.upper() if c.isalnum())[:3] or "AST"
    n = (db.scalar(select(func.count(Asset.id)).where(Asset.org_id == ctx.org.id)) or 0) + 1
    while True:
        tag = f"{prefix}-{n:04d}"
        if not db.scalar(select(Asset.id).where(Asset.org_id == ctx.org.id, Asset.tag == tag)):
            return tag
        n += 1


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    _check_assignee(db, ctx, body.assigned_to_id)
    tag = body.tag.strip() or _next_tag(db, ctx, body.asset_type)
    if db.scalar(select(Asset.id).where(Asset.org_id == ctx.org.id, Asset.tag == tag)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Asset tag {tag} is already used.")
    a = Asset(org_id=ctx.org.id, **body.model_dump(exclude={"tag"}), tag=tag)
    db.add(a)
    record(db, "asset.created", f"{tag} {a.name}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    db.refresh(a)
    return _out(a)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: uuid.UUID, ctx: OrgContext = Depends(require_role(Role.viewer)), db: Session = Depends(get_db)):
    if ctx.role == Role.member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Asset records are visible to IT staff only.")
    return _out(_get(db, ctx, asset_id))


class AssetPatch(BaseModel):
    tag: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_type: str | None = Field(default=None, min_length=1, max_length=60)
    os: str | None = None
    assigned_to_id: uuid.UUID | None = None
    unassign: bool = False
    location: str | None = None
    status: AssetStatus | None = None
    serial_number: str | None = None
    purchase_date: date | None = None
    warranty_end: date | None = None
    notes: str | None = None


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: uuid.UUID, body: AssetPatch, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    a = _get(db, ctx, asset_id)
    data = body.model_dump(exclude_unset=True, exclude={"unassign"})
    if "tag" in data and data["tag"] != a.tag:
        if db.scalar(select(Asset.id).where(Asset.org_id == ctx.org.id, Asset.tag == data["tag"])):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Asset tag {data['tag']} is already used.")
    if data.get("assigned_to_id"):
        _check_assignee(db, ctx, data["assigned_to_id"])
    changes = {}
    for k, v in data.items():
        if getattr(a, k) != v:
            changes[k] = str(v)
            setattr(a, k, v)
    if body.unassign and a.assigned_to_id:
        a.assigned_to_id = None
        changes["assigned_to_id"] = "none"
    if changes:
        record(db, "asset.updated", a.tag, user=ctx.user, org_id=ctx.org.id, detail=changes, request=request)
        db.commit()
        db.refresh(a)
    return _out(a)


@router.delete("/{asset_id}", response_model=Ok)
def delete_asset(asset_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    a = _get(db, ctx, asset_id)
    record(db, "asset.deleted", f"{a.tag} {a.name}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.delete(a)
    db.commit()
    return Ok()
