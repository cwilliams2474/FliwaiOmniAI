from sqlalchemy.orm import Session

from app.models.core import UsageEvent, User


def record_usage(db: Session, user: User | None, category: str, action: str, units: int = 1, detail: str = '') -> None:
    db.add(UsageEvent(
        user_id=user.id if user else None,
        category=category[:80],
        action=action[:120],
        units=max(0, int(units)),
        detail=detail[:4000],
    ))
