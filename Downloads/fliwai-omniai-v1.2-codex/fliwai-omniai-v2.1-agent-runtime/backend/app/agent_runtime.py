import json
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.integrations import execute_integration_action
from app.models.core import (
    Agent, AgentRun, AgentRunStep, AgentToolPermission, IntegrationConnection,
    MemoryEntry, Notification, Ticket, User,
)
from app.time_utils import utcnow

ALLOWED_STEP_TYPES = {'ai_prompt', 'create_ticket', 'memory_write', 'notify', 'integration_action'}


def _json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith('```json') and cleaned.endswith('```'):
        cleaned = cleaned[7:-3].strip()
    elif cleaned.startswith('```') and cleaned.endswith('```'):
        cleaned = cleaned[3:-3].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _permitted_tools(db: Session, agent: Agent, organization_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(AgentToolPermission, IntegrationConnection)
        .join(IntegrationConnection, IntegrationConnection.id == AgentToolPermission.connection_id)
        .filter(
            AgentToolPermission.agent_id == agent.id,
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.enabled.is_(True),
        )
        .all()
    )
    return [
        {'connection_id': conn.id, 'connection_name': conn.name, 'provider': conn.provider, 'action': permission.action}
        for permission, conn in rows
    ]


def plan_agent_run(db: Session, agent: Agent, organization_id: int, objective: str) -> list[dict[str, Any]]:
    tools = _permitted_tools(db, agent, organization_id)
    if not settings.openai_api_key:
        return [{'type': 'ai_prompt', 'title': 'Analyze objective', 'config': {'prompt': objective}, 'requires_approval': False}]

    system = f'''You are the planning engine for the FLIWAI OmniAI agent "{agent.name}".
Agent instructions: {agent.system_prompt}
Create the smallest safe plan needed to achieve the objective.
Allowed step types: ai_prompt, create_ticket, memory_write, notify, integration_action.
External integration_action steps MUST use only a connection_id/action pair from the supplied permitted tools and MUST set requires_approval=true.
Do not invent credentials, connections, commands, or hidden capabilities.
Return ONLY JSON: {{"steps":[{{"type":"ai_prompt","title":"...","config":{{}},"requires_approval":false}}]}}.
Maximum 8 steps.'''
    prompt = f'Objective: {objective}\nPermitted external tools: {json.dumps(tools)}'
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key, timeout=60.0, max_retries=2)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}],
    )
    data = _json_object(response.choices[0].message.content or '{}')
    steps = data.get('steps') if isinstance(data.get('steps'), list) else []
    allowed_pairs = {(item['connection_id'], item['action']) for item in tools}
    normalized: list[dict[str, Any]] = []
    for raw in steps[:8]:
        if not isinstance(raw, dict):
            continue
        step_type = str(raw.get('type', ''))
        if step_type not in ALLOWED_STEP_TYPES:
            continue
        config = raw.get('config') if isinstance(raw.get('config'), dict) else {}
        requires_approval = bool(raw.get('requires_approval', False))
        if step_type == 'integration_action':
            try:
                pair = (int(config.get('connection_id', 0)), str(config.get('action', '')))
            except (TypeError, ValueError):
                continue
            if pair not in allowed_pairs:
                continue
            requires_approval = True
        normalized.append({
            'type': step_type,
            'title': str(raw.get('title') or step_type.replace('_', ' ').title())[:255],
            'config': config,
            'requires_approval': requires_approval,
        })
    return normalized or [{'type': 'ai_prompt', 'title': 'Analyze objective', 'config': {'prompt': objective}, 'requires_approval': False}]


def create_run(db: Session, agent: Agent, user: User, organization_id: int, objective: str) -> AgentRun:
    plan = plan_agent_run(db, agent, organization_id, objective)
    run = AgentRun(
        organization_id=organization_id,
        agent_id=agent.id,
        user_id=user.id,
        objective=objective,
        status='running',
        plan_json=json.dumps(plan),
    )
    db.add(run)
    db.flush()
    for position, item in enumerate(plan, start=1):
        db.add(AgentRunStep(
            run_id=run.id,
            position=position,
            step_type=item['type'],
            title=item['title'],
            config_json=json.dumps(item['config']),
            requires_approval=item['requires_approval'],
        ))
    db.flush()
    continue_run(db, run, agent, user)
    return run


def _render(value: Any, objective: str, context: str) -> Any:
    if isinstance(value, str):
        return value.replace('{objective}', objective).replace('{context}', context)
    if isinstance(value, dict):
        return {key: _render(item, objective, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, objective, context) for item in value]
    return value


def _execute_step(db: Session, run: AgentRun, step: AgentRunStep, agent: Agent, user: User, context: str) -> tuple[dict[str, Any], str]:
    config = _render(json.loads(step.config_json or '{}'), run.objective, context)
    if step.step_type == 'ai_prompt':
        prompt = str(config.get('prompt') or run.objective)
        from app.ai.service import get_ai_response_with_system
        answer, model = get_ai_response_with_system(prompt, agent.system_prompt)
        return {'answer': answer, 'model': model}, answer
    if step.step_type == 'create_ticket':
        ticket = Ticket(
            organization_id=run.organization_id,
            title=str(config.get('title') or f'Agent: {run.objective}')[:255],
            description=str(config.get('description') or context or run.objective)[:10000],
            priority=str(config.get('priority') or 'normal')[:50],
        )
        db.add(ticket); db.flush()
        return {'ticket_id': ticket.id, 'title': ticket.title}, context
    if step.step_type == 'memory_write':
        entry = MemoryEntry(
            user_id=user.id,
            category=str(config.get('category') or 'agent')[:80],
            key=str(config.get('key') or agent.name)[:160],
            value=str(config.get('value') or context or run.objective)[:12000],
        )
        db.add(entry); db.flush()
        return {'memory_id': entry.id, 'key': entry.key}, context
    if step.step_type == 'notify':
        note = Notification(
            user_id=user.id,
            title=str(config.get('title') or f'{agent.name} update')[:255],
            body=str(config.get('body') or context or run.objective)[:12000],
            level=str(config.get('level') or 'info')[:30],
        )
        db.add(note); db.flush()
        return {'notification_id': note.id}, context
    if step.step_type == 'integration_action':
        connection_id = int(config.get('connection_id', 0)); action = str(config.get('action', ''))
        permission = db.query(AgentToolPermission).filter(
            AgentToolPermission.agent_id == agent.id,
            AgentToolPermission.connection_id == connection_id,
            AgentToolPermission.action == action,
        ).first()
        connection = db.query(IntegrationConnection).filter(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == run.organization_id,
            IntegrationConnection.enabled.is_(True),
        ).first()
        if not permission or not connection:
            raise ValueError('Agent integration permission is no longer valid')
        result = execute_integration_action(connection, action, config.get('params') or {})
        return {'connection_id': connection_id, 'action': action, 'result': result}, json.dumps(result)
    raise ValueError(f'Unsupported agent step type: {step.step_type}')


def continue_run(db: Session, run: AgentRun, agent: Agent, user: User) -> AgentRun:
    steps = db.query(AgentRunStep).filter(AgentRunStep.run_id == run.id).order_by(AgentRunStep.position.asc()).all()
    context = ''
    for existing in steps:
        if existing.status == 'completed':
            try:
                prior = json.loads(existing.result_json or '{}')
                context = str(prior.get('answer') or prior.get('result') or context)
            except json.JSONDecodeError:
                pass
            continue
        if existing.status == 'rejected':
            run.status = 'cancelled'; run.completed_at = utcnow(); run.summary = 'Run stopped because an approval was rejected.'
            db.commit(); db.refresh(run); return run
        if existing.requires_approval and existing.approved_at is None:
            existing.status = 'waiting_approval'; run.status = 'waiting_approval'
            db.commit(); db.refresh(run); return run
        existing.status = 'running'; db.flush()
        try:
            result, context = _execute_step(db, run, existing, agent, user, context)
            existing.result_json = json.dumps(result); existing.status = 'completed'; existing.completed_at = utcnow()
        except Exception as exc:
            existing.status = 'failed'; existing.error = str(exc)[:12000]; existing.completed_at = utcnow()
            run.status = 'failed'; run.error = existing.error; run.completed_at = utcnow()
            db.commit(); db.refresh(run); return run
    run.status = 'completed'; run.summary = context[:12000] if context else 'Agent run completed.'; run.completed_at = utcnow()
    db.commit(); db.refresh(run); return run
