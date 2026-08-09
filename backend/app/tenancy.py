import re
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.core import Organization, OrganizationMember, Subscription, User


def slugify(name: str) -> str:
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'organization'
    return base[:140]


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    suffix = 2
    while db.query(Organization.id).filter(Organization.slug == slug).first():
        slug = f'{base[:130]}-{suffix}'
        suffix += 1
    return slug


def memberships(db: Session, user: User):
    return db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).all()


def current_organization(db: Session, user: User) -> Organization:
    if user.current_organization_id is not None:
        member = db.query(OrganizationMember).filter(
            OrganizationMember.user_id == user.id,
            OrganizationMember.organization_id == user.current_organization_id,
        ).first()
        if member:
            org = db.query(Organization).filter(Organization.id == member.organization_id).first()
            if org:
                return org
    member = db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).order_by(OrganizationMember.id.asc()).first()
    if not member:
        raise HTTPException(status_code=409, detail='User is not assigned to an organization')
    user.current_organization_id = member.organization_id
    db.commit(); db.refresh(user)
    org = db.query(Organization).filter(Organization.id == member.organization_id).first()
    if not org:
        raise HTTPException(status_code=409, detail='Organization is unavailable')
    return org


def current_membership(db: Session, user: User) -> OrganizationMember:
    org = current_organization(db, user)
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.organization_id == org.id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail='Organization access denied')
    return member


def require_org_admin(db: Session, user: User) -> tuple[Organization, OrganizationMember]:
    org = current_organization(db, user)
    member = db.query(OrganizationMember).filter(
        OrganizationMember.user_id == user.id,
        OrganizationMember.organization_id == org.id,
    ).first()
    if not member or (member.role not in {'owner', 'admin'} and not user.is_admin):
        raise HTTPException(status_code=403, detail='Organization administrator access required')
    return org, member


def ensure_subscription(db: Session, organization_id: int) -> Subscription:
    row = db.query(Subscription).filter(Subscription.organization_id == organization_id).first()
    if row is None:
        row = Subscription(organization_id=organization_id, plan='starter', status='active', seats=5)
        db.add(row); db.flush()
    return row
