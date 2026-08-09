import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.security import get_current_user, require_admin
from app.database.session import get_db
from app.models.core import Agent, AgentRun, AgentRunStep, User
from app.schemas.core import AgentCreate, AgentRunApproval, AgentRunCreate, AgentToolPermissionCreate, AgentUpdate, IntegrationActionRequest

router = APIRouter(prefix='/agents', tags=['agents'])


def _run_view(db: Session, run: AgentRun) -> dict:
    steps = db.query(AgentRunStep).filter(AgentRunStep.run_id == run.id).order_by(AgentRunStep.position.asc()).all()
    import json
    return {
        'id': run.id, 'organization_id': run.organization_id, 'agent_id': run.agent_id, 'user_id': run.user_id,
        'objective': run.objective, 'status': run.status, 'summary': run.summary, 'error': run.error,
        'created_at': run.created_at, 'updated_at': run.updated_at, 'completed_at': run.completed_at,
        'steps': [
            {
                'id': step.id, 'position': step.position, 'type': step.step_type, 'title': step.title,
                'status': step.status, 'requires_approval': step.requires_approval,
                'approved_at': step.approved_at, 'result': json.loads(step.result_json or '{}'),
                'error': step.error, 'completed_at': step.completed_at,
            } for step in steps
        ],
    }


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


@router.post('/{agent_id}/runs', status_code=201)
def start_agent_run(agent_id: int, payload: AgentRunCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.agent_runtime import create_run
    from app.tenancy import current_organization
    org = current_organization(db, user)
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.enabled.is_(True)).first()
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')
    run = create_run(db, agent, user, org.id, payload.objective.strip())
    audit(db, user, 'agent.run.create', 'agent_run', run.id, f'agent={agent.id} objective={payload.objective[:300]}')
    db.commit(); db.refresh(run)
    return _run_view(db, run)


@router.get('/runs/recent')
def recent_agent_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.tenancy import current_organization
    org = current_organization(db, user)
    rows = db.query(AgentRun).filter(AgentRun.organization_id == org.id).order_by(AgentRun.created_at.desc()).limit(50).all()
    return [_run_view(db, row) for row in rows]


@router.get('/runs/{run_id}')
def get_agent_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.tenancy import current_organization
    org = current_organization(db, user)
    run = db.query(AgentRun).filter(AgentRun.id == run_id, AgentRun.organization_id == org.id).first()
    if not run:
        raise HTTPException(status_code=404, detail='Agent run not found')
    return _run_view(db, run)


@router.post('/runs/{run_id}/steps/{step_id}/approval')
def approve_agent_step(run_id: int, step_id: int, payload: AgentRunApproval, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.agent_runtime import continue_run
    from app.tenancy import current_organization
    from app.time_utils import utcnow
    org = current_organization(db, user)
    run = db.query(AgentRun).filter(AgentRun.id == run_id, AgentRun.organization_id == org.id).first()
    if not run:
        raise HTTPException(status_code=404, detail='Agent run not found')
    step = db.query(AgentRunStep).filter(AgentRunStep.id == step_id, AgentRunStep.run_id == run.id).first()
    if not step or not step.requires_approval or step.status != 'waiting_approval':
        raise HTTPException(status_code=409, detail='Step is not waiting for approval')
    if not payload.approve:
        step.status = 'rejected'; step.approved_by = user.id; step.approved_at = utcnow()
        run.status = 'cancelled'; run.summary = 'Run stopped because an approval was rejected.'; run.completed_at = utcnow()
        audit(db, user, 'agent.run.reject', 'agent_run_step', step.id, f'run={run.id}')
        db.commit(); db.refresh(run)
        return _run_view(db, run)
    step.approved_by = user.id; step.approved_at = utcnow(); step.status = 'pending'
    agent = db.query(Agent).filter(Agent.id == run.agent_id).first()
    if not agent:
        raise HTTPException(status_code=409, detail='Agent is no longer available')
    audit(db, user, 'agent.run.approve', 'agent_run_step', step.id, f'run={run.id}')
    continue_run(db, run, agent, user)
    db.commit(); db.refresh(run)
    return _run_view(db, run)
