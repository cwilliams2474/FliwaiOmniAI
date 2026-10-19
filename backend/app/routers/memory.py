import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_db
from app.deps import OrgContext, get_org_ctx, require_role
from app.models import MemoryEntry, Role
from app.schemas import Ok, iso

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryOut(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    created_at: str
    updated_at: str


class MemoryIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)


def _out(m: MemoryEntry) -> MemoryOut:
    return MemoryOut(id=m.id, title=m.title, content=m.content, created_at=iso(m.created_at), updated_at=iso(m.updated_at))


def _get(db: Session, ctx: OrgContext, mid: uuid.UUID) -> MemoryEntry:
    m = db.scalar(select(MemoryEntry).where(MemoryEntry.org_id == ctx.org.id, MemoryEntry.id == mid))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory entry not found.")
    return m


@router.get("", response_model=list[MemoryOut])
def list_memory(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return [_out(m) for m in db.scalars(select(MemoryEntry).where(MemoryEntry.org_id == ctx.org.id).order_by(MemoryEntry.title))]


@router.post("", response_model=MemoryOut, status_code=201)
def create_memory(body: MemoryIn, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    m = MemoryEntry(org_id=ctx.org.id, title=body.title.strip(), content=body.content.strip(), created_by_id=ctx.user.id)
    db.add(m)
    record(db, "memory.created", m.title, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.put("/{mid}", response_model=MemoryOut)
def update_memory(mid: uuid.UUID, body: MemoryIn, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    m = _get(db, ctx, mid)
    m.title, m.content = body.title.strip(), body.content.strip()
    record(db, "memory.updated", m.title, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    db.refresh(m)
    return _out(m)


@router.delete("/{mid}", response_model=Ok)
def delete_memory(mid: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    m = _get(db, ctx, mid)
    record(db, "memory.deleted", m.title, user=ctx.user, org_id=ctx.org.id, request=request)
    db.delete(m)
    db.commit()
    return Ok()
