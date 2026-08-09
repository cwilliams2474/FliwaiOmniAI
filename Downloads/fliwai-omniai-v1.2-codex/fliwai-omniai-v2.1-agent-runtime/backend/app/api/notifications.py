from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import Notification, User
from app.schemas.core import NotificationUpdate

router = APIRouter(prefix='/notifications', tags=['notifications'])


@router.get('')
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.created_at.desc()).limit(100).all()
    return [{'id': r.id, 'title': r.title, 'body': r.body, 'level': r.level, 'is_read': r.is_read, 'created_at': r.created_at} for r in rows]


@router.patch('/{notification_id}')
def update_notification(notification_id: int, payload: NotificationUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Notification not found')
    row.is_read = payload.is_read; db.commit(); db.refresh(row)
    return {'id': row.id, 'is_read': row.is_read}
