from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import MemoryEntry, User
from app.schemas.core import MemoryCreate, MemoryUpdate

router = APIRouter(prefix='/memory', tags=['memory'])


@router.get('')
def list_memory(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(MemoryEntry).filter(MemoryEntry.user_id == user.id).order_by(MemoryEntry.updated_at.desc()).all()


@router.post('', status_code=201)
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = MemoryEntry(user_id=user.id, category=payload.category.strip() or 'general', key=payload.key.strip(), value=payload.value.strip())
    db.add(entry)
    db.flush()
    audit(db, user, 'memory.create', 'memory', entry.id, entry.key)
    db.commit(); db.refresh(entry)
    return entry


@router.patch('/{entry_id}')
def update_memory(entry_id: int, payload: MemoryUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.query(MemoryEntry).filter(MemoryEntry.id == entry_id, MemoryEntry.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Memory entry not found')
    for field in ('category', 'key', 'value'):
        value = getattr(payload, field)
        if value is not None:
            setattr(entry, field, value.strip())
    audit(db, user, 'memory.update', 'memory', entry.id, entry.key)
    db.commit(); db.refresh(entry)
    return entry


@router.delete('/{entry_id}', status_code=204)
def delete_memory(entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.query(MemoryEntry).filter(MemoryEntry.id == entry_id, MemoryEntry.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail='Memory entry not found')
    audit(db, user, 'memory.delete', 'memory', entry.id, entry.key)
    db.delete(entry); db.commit()
