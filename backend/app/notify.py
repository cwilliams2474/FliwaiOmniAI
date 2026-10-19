"""In-app notifications, with optional email for the ones people shouldn't miss."""

import threading
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.mailer import send_mail
from app.models import ROLE_RANK, Membership, Notification, Role, User


def notify(
    db: Session,
    org_id: uuid.UUID,
    user_ids: Iterable[uuid.UUID | None],
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    *,
    exclude: uuid.UUID | None = None,
    email: bool = False,
) -> int:
    """Queue notifications (committed with the caller's transaction). Returns how many were created."""
    ids = {u for u in user_ids if u and u != exclude}
    if not ids:
        return 0
    for uid in ids:
        db.add(Notification(org_id=org_id, user_id=uid, kind=kind, title=title[:300], body=body[:4000], link=link[:300]))
    if email and get_settings().smtp_host:
        emails = list(db.scalars(select(User.email).where(User.id.in_(ids), User.is_active.is_(True))))
        url = get_settings().public_url.rstrip("/") + link
        text = f"{body}\n\nOpen in {get_settings().app_name}: {url}" if body else f"Open in {get_settings().app_name}: {url}"
        # Send after the response so a slow mail server never holds up the request.
        threading.Thread(target=lambda: [send_mail(e, title, text) for e in emails], daemon=True).start()
    return len(ids)


def members_with_role(db: Session, org_id: uuid.UUID, minimum: Role) -> list[uuid.UUID]:
    rows = db.execute(select(Membership.user_id, Membership.role).where(Membership.org_id == org_id)).all()
    return [uid for uid, role in rows if ROLE_RANK[role] >= ROLE_RANK[minimum]]
