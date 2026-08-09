import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth.security import require_admin
from app.config import settings
from app.database.session import get_db
from app.models.core import IntegrationConnection, Organization, Subscription, Ticket, User, WorkflowSchedule
from app.observability import request_metrics

router = APIRouter(prefix='/monitoring', tags=['monitoring'])
STARTED_AT = time.time()


@router.get('/metrics')
def metrics(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    runtime = request_metrics.snapshot()
    return {
        'uptime_seconds': int(time.time() - STARTED_AT),
        'requests_total': runtime['requests_total'],
        'http_errors_total': runtime['errors_total'],
        'average_latency_ms': runtime['average_latency_ms'],
        'organizations': db.query(Organization).count(),
        'users': db.query(User).count(),
        'active_users': db.query(User).filter(User.is_active.is_(True)).count(),
        'open_tickets': db.query(Ticket).filter(Ticket.status.in_(['open','in_progress'])).count(),
        'enabled_integrations': db.query(IntegrationConnection).filter(IntegrationConnection.enabled.is_(True)).count(),
        'enabled_schedules': db.query(WorkflowSchedule).filter(WorkflowSchedule.enabled.is_(True)).count(),
        'active_subscriptions': db.query(Subscription).filter(Subscription.status.in_(['trialing','active'])).count(),
    }


@router.get('/prometheus', response_class=Response)
def prometheus(request: Request):
    """Minimal Prometheus scrape endpoint protected by a dedicated header token in production."""
    if settings.environment.lower() == 'production':
        if not settings.metrics_token:
            raise HTTPException(status_code=503, detail='Metrics export is not configured')
        supplied = request.headers.get('X-Metrics-Token', '')
        authorization = request.headers.get('Authorization', '')
        if not supplied and authorization.startswith('Bearer '):
            supplied = authorization[7:]
        if not supplied or not hmac.compare_digest(supplied, settings.metrics_token):
            raise HTTPException(status_code=401, detail='Invalid metrics token')
    return Response(request_metrics.prometheus(), media_type='text/plain; version=0.0.4')
