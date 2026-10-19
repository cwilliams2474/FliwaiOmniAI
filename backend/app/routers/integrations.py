import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import integrations as ig
from app.audit import record
from app.db import get_db
from app.deps import OrgContext, require_role
from app.models import Integration, Role
from app.schemas import Ok, iso

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationOut(BaseModel):
    id: uuid.UUID
    kind: str
    kind_label: str
    name: str
    config: dict
    secret_hint: str
    enabled: bool
    last_used_at: str | None
    last_ok: bool | None
    last_error: str


def _out(i: Integration) -> IntegrationOut:
    return IntegrationOut(
        id=i.id, kind=i.kind, kind_label=ig.KINDS[i.kind]["label"], name=i.name, config=i.config or {}, secret_hint=i.secret_hint,
        enabled=i.enabled, last_used_at=iso(i.last_used_at), last_ok=i.last_ok, last_error=i.last_error,
    )


def _get(db: Session, ctx: OrgContext, iid: uuid.UUID) -> Integration:
    i = db.scalar(select(Integration).where(Integration.org_id == ctx.org.id, Integration.id == iid))
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not found.")
    return i


@router.get("/kinds")
def kinds(ctx: OrgContext = Depends(require_role(Role.technician))):
    return ig.KINDS


@router.get("", response_model=list[IntegrationOut])
def list_integrations(ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    return [_out(i) for i in db.scalars(select(Integration).where(Integration.org_id == ctx.org.id).order_by(Integration.name))]


class IntegrationIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(default="", max_length=2000, description="Webhook URL. Leave blank on edit to keep the stored one.")
    auth_header_name: str = Field(default="", max_length=100)
    auth_header_value: str = Field(default="", max_length=2000)
    enabled: bool = True


def _secrets(body: IntegrationIn, existing: dict | None) -> tuple[dict, str]:
    secrets = dict(existing or {})
    if body.url:
        url = ig.validate_url(body.url)
        secrets["webhook_url" if body.kind in ("slack", "teams") else "url"] = url
    if body.kind == "webhook" and body.auth_header_value:
        secrets["auth_header_value"] = body.auth_header_value
    url = secrets.get("webhook_url") or secrets.get("url")
    if not url:
        raise ig.IntegrationError("Enter the webhook URL.")
    return secrets, ig.hint_for(url)


@router.post("", response_model=IntegrationOut, status_code=201)
def create_integration(body: IntegrationIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    if body.kind not in ig.KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Kind must be one of: {', '.join(ig.KINDS)}.")
    if db.scalar(select(Integration.id).where(Integration.org_id == ctx.org.id, Integration.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, f"An integration named {body.name} already exists.")
    try:
        secrets, hint = _secrets(body, None)
    except ig.IntegrationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    i = Integration(
        org_id=ctx.org.id, kind=body.kind, name=body.name.strip(), enabled=body.enabled, secret_enc=ig.seal(secrets), secret_hint=hint,
        config={"auth_header_name": body.auth_header_name} if body.kind == "webhook" and body.auth_header_name else {},
    )
    db.add(i)
    record(db, "integration.created", f"{i.kind}: {i.name}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    db.refresh(i)
    return _out(i)


@router.put("/{iid}", response_model=IntegrationOut)
def update_integration(iid: uuid.UUID, body: IntegrationIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    i = _get(db, ctx, iid)
    if body.kind != i.kind:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The kind of an integration can't change. Create a new one instead.")
    try:
        existing = ig.unseal(i)
    except ig.IntegrationError:
        existing = None  # key changed; the new values must be entered again
    try:
        secrets, hint = _secrets(body, existing)
    except ig.IntegrationError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    i.name, i.enabled, i.secret_enc, i.secret_hint = body.name.strip(), body.enabled, ig.seal(secrets), hint
    if i.kind == "webhook":
        i.config = {"auth_header_name": body.auth_header_name} if body.auth_header_name else {}
    record(db, "integration.updated", f"{i.kind}: {i.name}", user=ctx.user, org_id=ctx.org.id, detail={"secret_changed": bool(body.url or body.auth_header_value)}, request=request)
    db.commit()
    return _out(i)


@router.delete("/{iid}", response_model=Ok)
def delete_integration(iid: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    i = _get(db, ctx, iid)
    record(db, "integration.deleted", f"{i.kind}: {i.name}", user=ctx.user, org_id=ctx.org.id, request=request)
    db.delete(i)
    db.commit()
    return Ok()


@router.post("/{iid}/test")
def test_integration(iid: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    i = _get(db, ctx, iid)
    try:
        ig.send(i, f"Test message from {ctx.org.name} OmniAI, sent by {ctx.user.name}.", ctx.org.name)
        ok, msg = True, f"{i.name} received the test message."
    except ig.IntegrationError as e:
        ok, msg = False, str(e)
    record(db, "integration.tested", i.name, user=ctx.user, org_id=ctx.org.id, detail={"ok": ok}, request=request)
    db.commit()
    return {"ok": ok, "message": msg}
