from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.core import Organization, OrganizationMember, Ticket, User
from app.tenancy import current_organization, slugify


def make_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_slugify_is_stable_and_url_safe():
    assert slugify('Acme Medical & IT!') == 'acme-medical-it'


def test_current_organization_requires_membership_and_selects_member_org():
    db = make_db()
    org_a = Organization(name='A', slug='a')
    org_b = Organization(name='B', slug='b')
    user = User(email='u@example.com', full_name='U', password_hash='x', current_organization_id=None)
    db.add_all([org_a, org_b, user]); db.flush()
    db.add(OrganizationMember(organization_id=org_b.id, user_id=user.id, role='member')); db.commit()
    assert current_organization(db, user).id == org_b.id
    assert user.current_organization_id == org_b.id


def test_tenant_ticket_queries_do_not_cross_organizations():
    db = make_db()
    org_a = Organization(name='A', slug='a')
    org_b = Organization(name='B', slug='b')
    db.add_all([org_a, org_b]); db.flush()
    db.add_all([
        Ticket(organization_id=org_a.id, title='A ticket'),
        Ticket(organization_id=org_b.id, title='B ticket'),
    ]); db.commit()
    rows = db.query(Ticket).filter(Ticket.organization_id == org_a.id).all()
    assert [row.title for row in rows] == ['A ticket']
