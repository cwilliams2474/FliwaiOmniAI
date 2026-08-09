from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import create_access_token, get_current_user, hash_password, verify_password
from app.config import settings
from app.database.session import get_db
from app.models.core import Organization, OrganizationMember, User
from app.schemas.core import LoginRequest, PasswordUpdate, ProfileUpdate, RegisterRequest, TokenResponse, UserResponse
from app.tenancy import ensure_subscription
from app.mfa import verify_totp, reveal_secret

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/register', response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail='Email already registered')
    is_first_user = db.query(User.id).first() is None
    user = User(email=email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password), is_admin=is_first_user or email in settings.admin_emails)
    db.add(user); db.flush()
    org = db.query(Organization).order_by(Organization.id.asc()).first()
    if org is None:
        org = Organization(name='FLIWAI', slug='fliwai'); db.add(org); db.flush()
    role = 'owner' if is_first_user else 'member'
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=role))
    ensure_subscription(db, org.id)
    user.current_organization_id = org.id
    audit(db, user, 'auth.register', 'user', user.id, email); db.commit(); db.refresh(user)
    return user


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Invalid email or password')
    if not user.is_active:
        raise HTTPException(status_code=403, detail='Account is disabled')
    if user.mfa_enabled and (not payload.mfa_code or not verify_totp(reveal_secret(user.mfa_secret), payload.mfa_code)):
        raise HTTPException(status_code=428, detail='MFA_REQUIRED')
    no_admin_exists = db.query(User.id).filter(User.is_admin.is_(True)).first() is None
    if (email in settings.admin_emails or no_admin_exists) and not user.is_admin:
        user.is_admin = True
    audit(db, user, 'auth.login', 'user', user.id, email); db.commit(); db.refresh(user)
    return TokenResponse(access_token=create_access_token(user), user=user)


@router.post('/logout')
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.token_version += 1
    audit(db, current_user, 'auth.logout', 'user', current_user.id, 'All active tokens invalidated')
    db.commit()
    return {'status': 'signed_out'}


@router.get('/me', response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch('/me', response_model=UserResponse)
def update_profile(payload: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.full_name = payload.full_name.strip()
    audit(db, current_user, 'profile.update', 'user', current_user.id, 'Profile updated'); db.commit(); db.refresh(current_user)
    return current_user


@router.post('/change-password')
def change_password(payload: PasswordUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail='Current password is incorrect')
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail='New password must be different')
    current_user.password_hash = hash_password(payload.new_password)
    current_user.token_version += 1
    audit(db, current_user, 'auth.password_change', 'user', current_user.id, 'Password changed; sessions invalidated'); db.commit()
    return {'status': 'password_changed'}

@router.get('/sso/status')
def sso_status():
    return {'configured': bool(settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret)}

@router.get('/sso/start')
def sso_start():
    import httpx
    from urllib.parse import urlencode
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret): raise HTTPException(503,'SSO is not configured')
    discovery=httpx.get(f'{settings.oidc_issuer}/.well-known/openid-configuration',timeout=10).json()
    state=jwt.encode({'purpose':'oidc','exp':datetime.now(timezone.utc)+timedelta(minutes=10)},settings.jwt_secret,algorithm='HS256')
    query=urlencode({'client_id':settings.oidc_client_id,'response_type':'code','scope':'openid email profile','redirect_uri':settings.oidc_redirect_uri,'state':state})
    return {'authorization_url':f"{discovery['authorization_endpoint']}?{query}"}

@router.get('/sso/callback')
def sso_callback(code: str, state: str, db: Session = Depends(get_db)):
    import httpx
    from jose import jwt, JWTError
    try:
        payload=jwt.decode(state,settings.jwt_secret,algorithms=['HS256'])
        if payload.get('purpose')!='oidc': raise ValueError()
    except (JWTError,ValueError): raise HTTPException(400,'Invalid SSO state')
    discovery=httpx.get(f'{settings.oidc_issuer}/.well-known/openid-configuration',timeout=10).json()
    token=httpx.post(discovery['token_endpoint'],data={'grant_type':'authorization_code','code':code,'redirect_uri':settings.oidc_redirect_uri,'client_id':settings.oidc_client_id,'client_secret':settings.oidc_client_secret},timeout=15)
    if token.status_code>=400: raise HTTPException(401,'SSO token exchange failed')
    access=token.json().get('access_token')
    info=httpx.get(discovery['userinfo_endpoint'],headers={'Authorization':f'Bearer {access}'},timeout=10)
    if info.status_code>=400: raise HTTPException(401,'SSO user lookup failed')
    profile=info.json(); email=str(profile.get('email','')).lower()
    if not email or profile.get('email_verified') is False: raise HTTPException(401,'Verified email is required')
    user=db.query(User).filter(User.email==email).first()
    if user is None:
        import secrets
        user=User(email=email,full_name=str(profile.get('name','')),password_hash=hash_password(secrets.token_urlsafe(32))); db.add(user); db.flush()
        org=db.query(Organization).order_by(Organization.id.asc()).first()
        if org is None: org=Organization(name='FLIWAI',slug='fliwai'); db.add(org); db.flush()
        db.add(OrganizationMember(organization_id=org.id,user_id=user.id,role='member')); user.current_organization_id=org.id; ensure_subscription(db,org.id)
    if not user.is_active: raise HTTPException(403,'Account is disabled')
    audit(db,user,'auth.sso_login','user',user.id,email); db.commit(); db.refresh(user)
    return TokenResponse(access_token=create_access_token(user),user=user)
