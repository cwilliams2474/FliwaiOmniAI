import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import get_current_user, require_admin
from app.database.session import get_db
from app.models.core import Agent, User
from app.schemas.core import AgentCreate, AgentToolPermissionCreate, AgentUpdate, IntegrationActionRequest

router = APIRouter(prefix='/agents', tags=['agents'])


def _slug(name: str) -> str:
    value = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return value[:110] or 'agent'


@router.get('')
def list_agents(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return db.query(Agent).filter(Agent.enabled.is_(True)).order_by(Agent.is_system.desc(), Agent.name.asc()).all()


@router.post('', status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    base = _slug(payload.name); slug = base; suffix = 2
    while db.query(Agent.id).filter(Agent.slug == slug).first():
        slug = f'{base}-{suffix}'; suffix += 1
    agent = Agent(name=payload.name.strip(), slug=slug, description=payload.description.strip(), system_prompt=payload.system_prompt.strip(), created_by=admin.id)
    db.add(agent); db.flush(); audit(db, admin, 'agent.create', 'agent', agent.id, agent.name); db.commit(); db.refresh(agent)
    return agent


@router.patch('/{agent_id}')
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')
    if agent.is_system and payload.system_prompt is not None:
        raise HTTPException(status_code=400, detail='System agent prompts are managed by the application')
    for field in ('name', 'description', 'system_prompt', 'enabled'):
        value = getattr(payload, field)
        if value is not None:
            setattr(agent, field, value.strip() if isinstance(value, str) else value)
    audit(db, admin, 'agent.update', 'agent', agent.id, agent.name); db.commit(); db.refresh(agent)
    return agent


@router.get('/{agent_id}/tool-permissions')
def list_tool_permissions(agent_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    from app.models.core import AgentToolPermission, IntegrationConnection
    rows = db.query(AgentToolPermission).filter(AgentToolPermission.agent_id == agent_id).all()
    result = []
    for row in rows:
        conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == row.connection_id).first()
        result.append({'id': row.id, 'connection_id': row.connection_id, 'connection_name': conn.name if conn else '', 'provider': conn.provider if conn else '', 'action': row.action})
    return result


@router.post('/{agent_id}/tool-permissions', status_code=201)
def add_tool_permission(agent_id: int, payload: AgentToolPermissionCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from app.integrations import PROVIDERS
    from app.models.core import AgentToolPermission, IntegrationConnection
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == payload.connection_id).first()
    if not agent or not conn: raise HTTPException(status_code=404, detail='Agent or integration not found')
    if payload.action not in PROVIDERS.get(conn.provider, {}).get('actions', []): raise HTTPException(status_code=400, detail='Action is not supported by this integration')
    existing = db.query(AgentToolPermission).filter(AgentToolPermission.agent_id == agent_id, AgentToolPermission.connection_id == conn.id, AgentToolPermission.action == payload.action).first()
    if existing: return {'id': existing.id, 'connection_id': existing.connection_id, 'action': existing.action}
    row = AgentToolPermission(agent_id=agent_id, connection_id=conn.id, action=payload.action, created_by=admin.id)
    db.add(row); db.flush(); audit(db, admin, 'agent.tool_permission_add', 'agent', agent_id, f'{conn.provider}:{payload.action}'); db.commit(); db.refresh(row)
    return {'id': row.id, 'connection_id': row.connection_id, 'action': row.action}


@router.delete('/{agent_id}/tool-permissions/{permission_id}', status_code=204)
def remove_tool_permission(agent_id: int, permission_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    from app.models.core import AgentToolPermission
    row = db.query(AgentToolPermission).filter(AgentToolPermission.id == permission_id, AgentToolPermission.agent_id == agent_id).first()
    if not row: raise HTTPException(status_code=404, detail='Permission not found')
    db.delete(row); audit(db, admin, 'agent.tool_permission_remove', 'agent', agent_id, str(permission_id)); db.commit()


@router.post('/{agent_id}/integration-action')
def run_agent_integration_action(agent_id: int, payload: IntegrationActionRequest, connection_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.integrations import execute_integration_action
    from app.models.core import AgentToolPermission, IntegrationConnection
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.enabled.is_(True)).first()
    if not agent: raise HTTPException(status_code=404, detail='Agent not found')
    permission = db.query(AgentToolPermission).filter(AgentToolPermission.agent_id == agent_id, AgentToolPermission.connection_id == connection_id, AgentToolPermission.action == payload.action).first()
    if not permission: raise HTTPException(status_code=403, detail='Agent is not permitted to use this integration action')
    conn = db.query(IntegrationConnection).filter(IntegrationConnection.id == connection_id).first()
    if not conn: raise HTTPException(status_code=404, detail='Integration not found')
    try: result = execute_integration_action(conn, payload.action, payload.params)
    except Exception as exc: raise HTTPException(status_code=400, detail=f'Agent tool action failed: {exc}') from exc
    audit(db, user, 'agent.integration_action', 'agent', agent_id, f'{conn.provider}:{payload.action}'); db.commit()
    return result
