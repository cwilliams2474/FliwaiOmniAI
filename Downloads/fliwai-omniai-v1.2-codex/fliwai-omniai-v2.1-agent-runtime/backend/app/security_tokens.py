import hashlib, secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.time_utils import utcnow
from app.models.core import SecurityToken


def create_security_token(db: Session, purpose: str, *, user_id=None, organization_id=None, email='', role='member', minutes=60):
    raw = secrets.token_urlsafe(32)
    row = SecurityToken(user_id=user_id, organization_id=organization_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose=purpose, email=email.lower(), role=role, expires_at=utcnow() + timedelta(minutes=minutes))
    db.add(row); db.flush()
    return raw, row


def consume_security_token(db: Session, raw: str, purpose: str):
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = db.query(SecurityToken).filter(SecurityToken.token_hash == digest, SecurityToken.purpose == purpose).first()
    if not row or row.used_at is not None or row.expires_at < utcnow():
        return None
    row.used_at = utcnow()
    return row
