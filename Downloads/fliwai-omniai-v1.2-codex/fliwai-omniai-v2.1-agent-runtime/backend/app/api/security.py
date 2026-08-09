from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.audit import audit
from app.auth.security import get_current_user, hash_password
from app.database.session import get_db
from app.email_service import send_email
from app.mfa import generate_secret, provisioning_uri, verify_totp, protect_secret, reveal_secret
from app.models.core import User
from app.schemas.core import MFAConfirmRequest, PasswordResetConfirm, PasswordResetRequest
from app.security_tokens import consume_security_token, create_security_token
from app.config import settings

router = APIRouter(prefix='/security', tags=['security'])

@router.post('/mfa/setup')
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = generate_secret(); user.mfa_secret = protect_secret(secret); user.mfa_enabled = False
    audit(db,user,'security.mfa_setup','user',user.id,'MFA enrollment started'); db.commit()
    return {'secret': secret, 'provisioning_uri': provisioning_uri(secret,user.email)}

@router.post('/mfa/confirm')
def mfa_confirm(payload: MFAConfirmRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_secret or not verify_totp(reveal_secret(user.mfa_secret),payload.code): raise HTTPException(400,'Invalid authenticator code')
    user.mfa_enabled=True; user.token_version += 1; audit(db,user,'security.mfa_enable','user',user.id,'MFA enabled'); db.commit()
    return {'status':'enabled'}

@router.delete('/mfa')
def mfa_disable(payload: MFAConfirmRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or not verify_totp(reveal_secret(user.mfa_secret),payload.code): raise HTTPException(400,'Invalid authenticator code')
    user.mfa_enabled=False; user.mfa_secret=''; user.token_version += 1; audit(db,user,'security.mfa_disable','user',user.id,'MFA disabled'); db.commit()
    return {'status':'disabled'}

@router.post('/password-reset/request')
def reset_request(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    user=db.query(User).filter(User.email==payload.email.lower()).first()
    if user:
        raw,_=create_security_token(db,'password_reset',user_id=user.id,email=user.email,minutes=30); db.commit()
        link=f'{settings.app_base_url}/login?reset_token={raw}'
        send_email(user.email,'Reset your OmniAI password',f'Use this link within 30 minutes:\n{link}')
    return {'status':'accepted'}

@router.post('/password-reset/confirm')
def reset_confirm(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    row=consume_security_token(db,payload.token,'password_reset')
    if not row or not row.user_id: raise HTTPException(400,'Reset link is invalid or expired')
    user=db.query(User).filter(User.id==row.user_id).first()
    if not user: raise HTTPException(400,'Reset link is invalid')
    user.password_hash=hash_password(payload.new_password); user.token_version += 1
    audit(db,user,'security.password_reset','user',user.id,'Password reset completed'); db.commit()
    return {'status':'password_reset'}
