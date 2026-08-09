from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import User
from app.schemas.core import SubscriptionUpdate, CheckoutCreate
from app.tenancy import current_organization, ensure_subscription, require_org_admin

router = APIRouter(prefix='/billing', tags=['billing'])


def _view(row):
    return {'id': row.id, 'organization_id': row.organization_id, 'plan': row.plan, 'status': row.status, 'seats': row.seats, 'external_customer_id': row.external_customer_id, 'external_subscription_id': row.external_subscription_id, 'current_period_end': row.current_period_end, 'updated_at': row.updated_at}


@router.get('/current')
def current_subscription(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user); row = ensure_subscription(db, org.id); db.commit(); db.refresh(row)
    return _view(row)


@router.patch('/current')
def update_subscription(payload: SubscriptionUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, user); row = ensure_subscription(db, org.id)
    for key, value in payload.model_dump(exclude_none=True).items(): setattr(row, key, value)
    audit(db, user, 'billing.subscription_update', 'organization', org.id, str(payload.model_dump(exclude_none=True)))
    db.commit(); db.refresh(row); return _view(row)

@router.post('/checkout')
def create_checkout(payload: CheckoutCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import httpx
    from fastapi import HTTPException
    from app.config import settings
    org, _ = require_org_admin(db, user)
    if not settings.stripe_secret_key: raise HTTPException(503, 'Stripe is not configured')
    price = {'starter':settings.stripe_price_starter,'professional':settings.stripe_price_professional,'enterprise':settings.stripe_price_enterprise}.get(payload.plan,'')
    if not price: raise HTTPException(503, f'Stripe price is not configured for {payload.plan}')
    data=[('mode','subscription'),('success_url',f'{settings.app_base_url}/dashboard?billing=success'),('cancel_url',f'{settings.app_base_url}/dashboard?billing=cancel'),('line_items[0][price]',price),('line_items[0][quantity]',str(payload.seats)),('metadata[organization_id]',str(org.id)),('subscription_data[metadata][organization_id]',str(org.id))]
    response=httpx.post('https://api.stripe.com/v1/checkout/sessions',data=data,auth=(settings.stripe_secret_key,''),timeout=20)
    if response.status_code >= 400: raise HTTPException(502,'Stripe checkout could not be created')
    body=response.json(); audit(db,user,'billing.checkout','organization',org.id,payload.plan); db.commit()
    return {'checkout_url':body.get('url'),'session_id':body.get('id')}
