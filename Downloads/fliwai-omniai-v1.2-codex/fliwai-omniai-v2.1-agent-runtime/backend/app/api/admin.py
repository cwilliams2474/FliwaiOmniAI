from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.time_utils import utcnow
from app.audit import audit
from app.auth.security import require_admin
from app.config import settings
from app.database.session import get_db
from app.models.core import AppSetting, AuditLog, UsageEvent, User
from app.schemas.core import AdminUserUpdate, AppSettingsUpdate, UserResponse

router = APIRouter(prefix='/admin', tags=['admin'])


@router.get('/users', response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch('/users/{user_id}', response_model=UserResponse)
def update_user_role(user_id: int, payload: AdminUserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    if user.id == admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail='You cannot remove your own administrator access')
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail='You cannot disable your own account')
    if payload.is_admin is not None:
        user.is_admin = payload.is_admin
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            user.token_version += 1
    audit(db, admin, 'admin.user_update', 'user', user.id, f'admin={user.is_admin} active={user.is_active}'); db.commit(); db.refresh(user)
    return user


@router.get('/audit')
def audit_log(limit: int = 100, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)).all()
    return [{'id': r.id, 'user_id': r.user_id, 'action': r.action, 'entity_type': r.entity_type, 'entity_id': r.entity_id, 'detail': r.detail, 'created_at': r.created_at} for r in rows]


@router.get('/usage')
def usage(days: int = 30, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    since = utcnow() - timedelta(days=min(max(days, 1), 365))
    rows = db.query(UsageEvent).filter(UsageEvent.created_at >= since).all()
    by_category = Counter(r.category for r in rows)
    by_action = Counter(r.action for r in rows)
    return {'period_days': days, 'events': len(rows), 'units': sum(r.units for r in rows), 'by_category': dict(by_category), 'top_actions': dict(by_action.most_common(12))}


@router.get('/settings')
def get_settings(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    stored = {r.key: r.value for r in db.query(AppSetting).all()}
    return {
        'organization_name': stored.get('organization_name', 'FLIWAI'),
        'default_ai_model': stored.get('default_ai_model', settings.openai_model),
        'default_code_model': stored.get('default_code_model', settings.openai_code_model),
        'environment': settings.environment,
        'rate_limit_per_minute': settings.rate_limit_per_minute,
    }


@router.patch('/settings')
def update_settings(payload: AppSettingsUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    for key, value in payload.model_dump(exclude_none=True).items():
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row is None:
            row = AppSetting(key=key, value=value, updated_by=admin.id); db.add(row)
        else:
            row.value = value; row.updated_by = admin.id
    audit(db, admin, 'admin.settings_update', 'settings', '', ','.join(payload.model_dump(exclude_none=True).keys())); db.commit()
    return get_settings(db, admin)


@router.get('/system')
def system_status(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return {
        'version': '2.1.0',
        'environment': settings.environment,
        'database': 'connected',
        'openai_configured': bool(settings.openai_api_key),
        'users': db.query(User).count(),
        'active_users': db.query(User).filter(User.is_active.is_(True)).count(),
    }
