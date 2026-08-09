import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import get_current_user, require_admin
from app.crypto_utils import encrypt_secret
from app.database.session import get_db
from app.integrations import execute_integration_action, public_connection, test_connection
from app.models.core import IntegrationConnection, User
from app.schemas.core import IntegrationActionRequest, IntegrationCreate, IntegrationUpdate
from app.tenancy import current_organization, require_org_admin

router = APIRouter(prefix='/integrations', tags=['integrations'])


@router.get('')
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    rows = db.query(IntegrationConnection).filter(IntegrationConnection.organization_id == org.id).order_by(IntegrationConnection.provider.asc(), IntegrationConnection.name.asc()).all()
    return [public_connection(row) for row in rows]


@router.post('', status_code=201)
def create_connection(payload: IntegrationCreate, db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, admin)
    row = IntegrationConnection(
        organization_id=org.id,
        provider=payload.provider,
        name=payload.name.strip(),
        config_json=json.dumps(payload.config),
        secret_encrypted=encrypt_secret(payload.secret),
        created_by=admin.id,
    )
    db.add(row); db.flush(); audit(db, admin, 'integration.create', 'integration', row.id, row.provider); db.commit(); db.refresh(row)
    return public_connection(row)


@router.patch('/{connection_id}')
def update_connection(connection_id: int, payload: IntegrationUpdate, db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, admin)
    row = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id, IntegrationConnection.organization_id == org.id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Integration not found')
    if payload.name is not None: row.name = payload.name.strip()
    if payload.config is not None: row.config_json = json.dumps(payload.config)
    if payload.secret is not None: row.secret_encrypted = encrypt_secret(payload.secret)
    if payload.enabled is not None: row.enabled = payload.enabled
    audit(db, admin, 'integration.update', 'integration', row.id, row.provider); db.commit(); db.refresh(row)
    return public_connection(row)


@router.post('/{connection_id}/test')
def test_integration(connection_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_user)):
    org, _ = require_org_admin(db, admin)
    row = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id, IntegrationConnection.organization_id == org.id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Integration not found')
    try:
        result = test_connection(row)
    except (ValueError, httpx.HTTPError) as exc:
        audit(db, admin, 'integration.test_failed', 'integration', row.id, str(exc)); db.commit()
        raise HTTPException(status_code=400, detail=f'Connection test failed: {exc}') from exc
    audit(db, admin, 'integration.test', 'integration', row.id, row.provider); db.commit()
    return result


@router.post('/{connection_id}/action')
def run_action(connection_id: int, payload: IntegrationActionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    row = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id, IntegrationConnection.organization_id == org.id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Integration not found')
    try:
        result = execute_integration_action(row, payload.action, payload.params)
    except (ValueError, httpx.HTTPError) as exc:
        audit(db, user, 'integration.action_failed', 'integration', row.id, f'{payload.action}: {exc}'); db.commit()
        raise HTTPException(status_code=400, detail=f'Integration action failed: {exc}') from exc
    audit(db, user, 'integration.action', 'integration', row.id, payload.action); db.commit()
    return result
