from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import Asset, Document, PortalRequest, Ticket, User
from app.schemas.core import PortalRequestCreate
from app.tenancy import current_organization

router = APIRouter(prefix='/portal', tags=['portal'])


@router.get('/summary')
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    return {
        'organization': {'id': org.id, 'name': org.name, 'slug': org.slug},
        'open_tickets': db.query(Ticket).filter(Ticket.organization_id == org.id, Ticket.status.in_(['open','in_progress'])).count(),
        'assets': db.query(Asset).filter(Asset.organization_id == org.id).count(),
        'documents': db.query(Document).filter(Document.organization_id == org.id).count(),
        'my_requests': db.query(PortalRequest).filter(PortalRequest.organization_id == org.id, PortalRequest.user_id == user.id).count(),
    }


@router.get('/requests')
def list_requests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    rows = db.query(PortalRequest).filter(PortalRequest.organization_id == org.id, PortalRequest.user_id == user.id).order_by(PortalRequest.created_at.desc()).all()
    return [{'id': r.id, 'subject': r.subject, 'description': r.description, 'status': r.status, 'created_at': r.created_at, 'updated_at': r.updated_at} for r in rows]


@router.post('/requests', status_code=201)
def create_request(payload: PortalRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    request = PortalRequest(organization_id=org.id, user_id=user.id, subject=payload.subject.strip(), description=payload.description.strip())
    ticket = Ticket(organization_id=org.id, title=f'Portal: {payload.subject.strip()}', description=payload.description.strip(), priority='normal')
    db.add(request); db.add(ticket); db.commit(); db.refresh(request)
    return {'id': request.id, 'subject': request.subject, 'status': request.status, 'ticket_id': ticket.id, 'created_at': request.created_at}
