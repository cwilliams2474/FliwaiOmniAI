import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import OrgContext, get_org_ctx
from app.models import Notification
from app.schemas import Ok, iso

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str
    read: bool
    created_at: str


class NotificationPage(BaseModel):
    unread: int
    items: list[NotificationOut]


def _mine(ctx: OrgContext):
    return (Notification.org_id == ctx.org.id, Notification.user_id == ctx.user.id)


@router.get("", response_model=NotificationPage)
def list_notifications(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db), unread_only: bool = False, limit: int = Query(30, le=100)):
    stmt = select(Notification).where(*_mine(ctx))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit))
    unread = db.scalar(select(func.count(Notification.id)).where(*_mine(ctx), Notification.read_at.is_(None))) or 0
    return NotificationPage(
        unread=unread,
        items=[NotificationOut(id=n.id, kind=n.kind, title=n.title, body=n.body, link=n.link, read=n.read_at is not None, created_at=iso(n.created_at)) for n in rows],
    )


@router.get("/count")
def unread_count(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return {"unread": db.scalar(select(func.count(Notification.id)).where(*_mine(ctx), Notification.read_at.is_(None))) or 0}


@router.post("/{nid}/read", response_model=Ok)
def mark_read(nid: uuid.UUID, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == nid, *_mine(ctx)))
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found.")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return Ok()


@router.post("/read-all", response_model=Ok)
def mark_all_read(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(*_mine(ctx), Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return Ok()
