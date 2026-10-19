import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ROLE_RANK, AuthSession, Membership, Organization, Role, User
from app.security import decode_token

COOKIE_NAME = "omni_session"


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _token_from(request: Request) -> str | None:
    tok = request.cookies.get(COOKIE_NAME)
    if tok:
        return tok
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    tok = _token_from(request)
    data = decode_token(tok, "session") if tok else None
    if not data:
        raise unauthorized
    try:
        sid = uuid.UUID(data["sid"])
    except (KeyError, ValueError):
        raise unauthorized
    sess = db.get(AuthSession, sid)
    now = datetime.now(timezone.utc)
    if not sess or sess.revoked_at or sess.expires_at < now:
        raise unauthorized
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise unauthorized
    if now - sess.last_seen_at > timedelta(minutes=1):
        sess.last_seen_at = now
        db.commit()
    request.state.session_id = sess.id
    return user


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: Role

    def at_least(self, role: Role) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


def get_org_ctx(
    x_org_id: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    if not x_org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an organization first (X-Org-Id header missing).")
    try:
        org_id = uuid.UUID(x_org_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Org-Id is not a valid organization id.")
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id))
    if not m:
        # Same response whether the org exists or not, so ids can't be probed.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")
    return OrgContext(user=user, org=m.org, role=m.role)


def require_role(minimum: Role):
    def dep(ctx: OrgContext = Depends(get_org_ctx)) -> OrgContext:
        if not ctx.at_least(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This needs the {minimum.value} role or higher.")
        return ctx

    return dep
