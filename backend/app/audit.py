import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.deps import client_ip
from app.models import AuditLog, User


def record(
    db: Session,
    action: str,
    target: str = "",
    *,
    user: User | None = None,
    actor: str | None = None,
    org_id: uuid.UUID | None = None,
    detail: dict | None = None,
    request: Request | None = None,
    commit: bool = False,
) -> None:
    """Append an audit entry. Callers normally commit it together with the change it describes."""
    db.add(
        AuditLog(
            org_id=org_id,
            user_id=user.id if user else None,
            actor=actor or (user.email if user else "system"),
            action=action,
            target=target[:400],
            detail=detail or {},
            ip=client_ip(request) if request else None,
        )
    )
    if commit:
        db.commit()
