from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import Ticket, User
from app.schemas.core import TicketCreate, TicketUpdate
from app.tenancy import current_organization

router = APIRouter(prefix='/tickets', tags=['tickets'])


@router.post('', status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    ticket = Ticket(organization_id=org.id, title=payload.title, description=payload.description, priority=payload.priority)
    db.add(ticket); db.commit(); db.refresh(ticket); return ticket


@router.get('')
def list_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    return db.query(Ticket).filter(Ticket.organization_id == org.id).order_by(Ticket.created_at.desc()).all()


@router.patch('/{ticket_id}')
def update_ticket(ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.organization_id == org.id).first()
    if ticket is None: raise HTTPException(status_code=404, detail='Ticket not found')
    if payload.status is not None: ticket.status = payload.status
    if payload.priority is not None: ticket.priority = payload.priority
    db.commit(); db.refresh(ticket); return ticket
