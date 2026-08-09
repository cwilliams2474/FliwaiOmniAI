from sqlalchemy.orm import Session

from app.models.core import AuditLog, User


def audit(db: Session, user: User | None, action: str, entity_type: str = '', entity_id: object = '', detail: str = '') -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id != '' else '',
        detail=detail[:12000],
    ))
