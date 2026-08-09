import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.time_utils import utcnow
from app.audit import audit
from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import User, Workflow, WorkflowRun
from app.schemas.core import WorkflowCreate, WorkflowRunRequest, WorkflowScheduleCreate, WorkflowUpdate
from app.workflows import execute_workflow
from app.tenancy import current_organization

router = APIRouter(prefix='/workflows', tags=['workflows'])


def _view(workflow: Workflow) -> dict:
    return {'id': workflow.id, 'name': workflow.name, 'description': workflow.description, 'steps': json.loads(workflow.steps_json), 'enabled': workflow.enabled, 'created_at': workflow.created_at, 'updated_at': workflow.updated_at}


@router.get('')
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    return [_view(item) for item in db.query(Workflow).filter(Workflow.organization_id == org.id).order_by(Workflow.updated_at.desc()).all()]


@router.post('', status_code=201)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    workflow = Workflow(organization_id=org.id, name=payload.name.strip(), description=payload.description.strip(), steps_json=json.dumps([step.model_dump() for step in payload.steps]), created_by=user.id)
    db.add(workflow); db.flush(); audit(db, user, 'workflow.create', 'workflow', workflow.id, workflow.name); db.commit(); db.refresh(workflow)
    return _view(workflow)


@router.patch('/{workflow_id}')
def update_workflow(workflow_id: int, payload: WorkflowUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.organization_id == org.id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    if payload.name is not None: workflow.name = payload.name.strip()
    if payload.description is not None: workflow.description = payload.description.strip()
    if payload.steps is not None: workflow.steps_json = json.dumps([step.model_dump() for step in payload.steps])
    if payload.enabled is not None: workflow.enabled = payload.enabled
    audit(db, user, 'workflow.update', 'workflow', workflow.id, workflow.name); db.commit(); db.refresh(workflow)
    return _view(workflow)


@router.post('/{workflow_id}/run')
def run_workflow(workflow_id: int, payload: WorkflowRunRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.organization_id == org.id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail='Workflow not found')
    if not workflow.enabled:
        raise HTTPException(status_code=409, detail='Workflow is disabled')
    run = execute_workflow(db, workflow, user, payload.input_text)
    audit(db, user, 'workflow.run', 'workflow', workflow.id, f'run={run.id} status={run.status}'); db.commit()
    return {'id': run.id, 'workflow_id': run.workflow_id, 'status': run.status, 'input_text': run.input_text, 'outputs': json.loads(run.output_json), 'error': run.error, 'created_at': run.created_at, 'completed_at': run.completed_at}


@router.get('/runs/recent')
def recent_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    runs = db.query(WorkflowRun).filter(WorkflowRun.user_id == user.id).order_by(WorkflowRun.created_at.desc()).limit(25).all()
    return [{'id': r.id, 'workflow_id': r.workflow_id, 'status': r.status, 'input_text': r.input_text, 'outputs': json.loads(r.output_json), 'error': r.error, 'created_at': r.created_at, 'completed_at': r.completed_at} for r in runs]


@router.get('/{workflow_id}/schedules')
def list_schedules(workflow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.core import WorkflowSchedule
    org = current_organization(db, user)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.organization_id == org.id).first()
    if not workflow: raise HTTPException(status_code=404, detail='Workflow not found')
    rows = db.query(WorkflowSchedule).filter(WorkflowSchedule.workflow_id == workflow_id, WorkflowSchedule.user_id == user.id).all()
    return [{'id': r.id, 'interval_minutes': r.interval_minutes, 'input_text': r.input_text, 'enabled': r.enabled, 'next_run_at': r.next_run_at, 'last_run_at': r.last_run_at} for r in rows]


@router.post('/{workflow_id}/schedules', status_code=201)
def create_schedule(workflow_id: int, payload: WorkflowScheduleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import datetime, timedelta
    from app.models.core import WorkflowSchedule
    org = current_organization(db, user)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.organization_id == org.id).first()
    if not workflow: raise HTTPException(status_code=404, detail='Workflow not found')
    row = WorkflowSchedule(workflow_id=workflow.id, user_id=user.id, interval_minutes=payload.interval_minutes, input_text=payload.input_text, next_run_at=utcnow() + timedelta(minutes=payload.interval_minutes))
    db.add(row); db.flush(); audit(db, user, 'workflow.schedule_create', 'workflow', workflow.id, f'interval={payload.interval_minutes}'); db.commit(); db.refresh(row)
    return {'id': row.id, 'interval_minutes': row.interval_minutes, 'input_text': row.input_text, 'enabled': row.enabled, 'next_run_at': row.next_run_at}
