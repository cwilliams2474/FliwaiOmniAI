from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import create_access_token, get_current_user
from app.database.session import get_db
from app.models.core import Organization, OrganizationMember, User
from app.schemas.core import OrganizationCreate, OrganizationMemberAdd, OrganizationMemberUpdate, OrganizationOnboardingUpdate, OrganizationInviteCreate, OrganizationInviteAccept
from app.tenancy import current_organization, memberships, require_org_admin, unique_slug, ensure_subscription

router = APIRouter(prefix='/organizations', tags=['organizations'])


def _view(db: Session, org: Organization, user: User) -> dict:
    member = db.query(OrganizationMember).filter(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id).first()
    return {'id': org.id, 'name': org.name, 'slug': org.slug, 'onboarding_complete': org.onboarding_complete, 'role': member.role if member else None, 'is_current': user.current_organization_id == org.id}


@router.get('')
def list_organizations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = [m.organization_id for m in memberships(db, user)]
    if not ids: return []
    rows = db.query(Organization).filter(Organization.id.in_(ids)).order_by(Organization.name.asc()).all()
    return [_view(db, row, user) for row in rows]


@router.get('/current')
def get_current(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _view(db, current_organization(db, user), user)


@router.post('', status_code=201)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = Organization(name=payload.name.strip(), slug=unique_slug(db, payload.name.strip()))
    db.add(org); db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role='owner'))
    ensure_subscription(db, org.id)
    user.current_organization_id = org.id
    audit(db, user, 'organization.create', 'organization', org.id, org.name)
    db.commit(); db.refresh(org); db.refresh(user)
    return _view(db, org, user)


@router.post('/{organization_id}/switch')
def switch_organization(organization_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = db.query(OrganizationMember).filter(OrganizationMember.organization_id == organization_id, OrganizationMember.user_id == user.id).first()
    if not member: raise HTTPException(status_code=403, detail='You are not a member of that organization')
    user.current_organization_id = organization_id
    user.token_version += 1
    audit(db, user, 'organization.switch', 'organization', organization_id, 'Active organization changed')
    db.commit(); db.refresh(user)
    return {'status': 'switched', 'organization_id': organization_id, 'access_token': create_access_token(user), 'token_type': 'bearer'}


@router.patch('/current')
def update_onboarding(payload: OrganizationOnboardingUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, user)
    if payload.name is not None: org.name = payload.name.strip()
    if payload.onboarding_complete is not None: org.onboarding_complete = payload.onboarding_complete
    audit(db, user, 'organization.update', 'organization', org.id, 'Onboarding/settings updated')
    db.commit(); db.refresh(org)
    return _view(db, org, user)


@router.get('/current/members')
def list_members(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    rows = db.query(OrganizationMember, User).join(User, User.id == OrganizationMember.user_id).filter(OrganizationMember.organization_id == org.id).all()
    return [{'id': member.id, 'user_id': account.id, 'email': account.email, 'full_name': account.full_name, 'role': member.role, 'active': account.is_active} for member, account in rows]


@router.post('/current/members', status_code=201)
def add_member(payload: OrganizationMemberAdd, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, user)
    target = db.query(User).filter(User.email == payload.email.lower()).first()
    if not target: raise HTTPException(status_code=404, detail='User must register before being added to an organization')
    existing = db.query(OrganizationMember).filter(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == target.id).first()
    if existing: raise HTTPException(status_code=409, detail='User is already a member')
    member = OrganizationMember(organization_id=org.id, user_id=target.id, role=payload.role)
    db.add(member); audit(db, user, 'organization.member_add', 'organization', org.id, target.email); db.commit(); db.refresh(member)
    return {'id': member.id, 'user_id': target.id, 'email': target.email, 'role': member.role}


@router.patch('/current/members/{member_id}')
def update_member(member_id: int, payload: OrganizationMemberUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org, actor = require_org_admin(db, user)
    member = db.query(OrganizationMember).filter(OrganizationMember.id == member_id, OrganizationMember.organization_id == org.id).first()
    if not member: raise HTTPException(status_code=404, detail='Member not found')
    if member.user_id == user.id and actor.role == 'owner' and payload.role != 'owner':
        raise HTTPException(status_code=400, detail='The active owner cannot demote their own membership')
    member.role = payload.role
    audit(db, user, 'organization.member_update', 'organization', org.id, f'member={member.id} role={member.role}')
    db.commit(); db.refresh(member)
    return {'id': member.id, 'user_id': member.user_id, 'role': member.role}

@router.post('/current/invitations', status_code=201)
def invite_member(payload: OrganizationInviteCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.config import settings
    from app.email_service import send_email
    from app.security_tokens import create_security_token
    org, _ = require_org_admin(db, user)
    existing_user = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing_user and db.query(OrganizationMember).filter(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == existing_user.id).first():
        raise HTTPException(status_code=409, detail='User is already a member')
    raw, row = create_security_token(db, 'organization_invite', organization_id=org.id, email=payload.email, role=payload.role, minutes=10080)
    audit(db, user, 'organization.invite', 'organization', org.id, payload.email.lower()); db.commit()
    link = f'{settings.app_base_url}/login?invite_token={raw}'
    delivered = send_email(payload.email, f'Invitation to {org.name}', f'You have been invited to {org.name}. This link expires in 7 days:\n{link}')
    return {'id': row.id, 'email': payload.email.lower(), 'role': payload.role, 'expires_at': row.expires_at, 'email_delivered': delivered, 'invite_token': raw if settings.environment != 'production' else None}

@router.post('/invitations/accept', status_code=201)
def accept_invitation(payload: OrganizationInviteAccept, db: Session = Depends(get_db)):
    from app.auth.security import hash_password
    from app.security_tokens import consume_security_token
    row = consume_security_token(db, payload.token, 'organization_invite')
    if not row or not row.organization_id: raise HTTPException(status_code=400, detail='Invitation is invalid or expired')
    target = db.query(User).filter(User.email == row.email).first()
    if target is None:
        target = User(email=row.email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password)); db.add(target); db.flush()
    existing = db.query(OrganizationMember).filter(OrganizationMember.organization_id == row.organization_id, OrganizationMember.user_id == target.id).first()
    if not existing: db.add(OrganizationMember(organization_id=row.organization_id, user_id=target.id, role=row.role))
    target.current_organization_id = row.organization_id
    audit(db, target, 'organization.invite_accept', 'organization', row.organization_id, target.email); db.commit(); db.refresh(target)
    return {'status':'accepted','email':target.email,'organization_id':row.organization_id}
