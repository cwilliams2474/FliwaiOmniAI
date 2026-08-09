import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from sqlalchemy.orm import Session

from app.time_utils import utcnow
from app.audit import audit
from app.auth.security import get_current_user
from app.codex_service import run_codex_task
from app.database.session import get_db
from app.codex_utils import safe_relative_path
from app.models.core import CodeFile, CodeProject, CodeTask, User
from app.schemas.core import CodeFileUpsert, CodeProjectCreate, CodeTaskApplyResponse, CodeTaskCreate
from app.usage import record_usage

router = APIRouter(prefix='/codex', tags=['codex'])


def _project(db: Session, user: User, project_id: int) -> CodeProject:
    record = db.query(CodeProject).filter(CodeProject.id == project_id, CodeProject.user_id == user.id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Code project not found')
    return record


def _safe_path(value: str) -> str:
    try:
        return safe_relative_path(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/projects')
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(CodeProject).filter(CodeProject.user_id == current_user.id).order_by(CodeProject.updated_at.desc()).all()
    return [{'id': r.id, 'name': r.name, 'description': r.description, 'created_at': r.created_at, 'updated_at': r.updated_at} for r in rows]


@router.post('/projects')
def create_project(payload: CodeProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = CodeProject(user_id=current_user.id, name=payload.name.strip(), description=payload.description.strip())
    db.add(record); db.flush(); audit(db, current_user, 'codex.project.create', 'code_project', record.id, record.name); db.commit(); db.refresh(record)
    return {'id': record.id, 'name': record.name, 'description': record.description, 'created_at': record.created_at, 'updated_at': record.updated_at}


@router.get('/projects/{project_id}/files')
def list_files(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    rows = db.query(CodeFile).filter(CodeFile.project_id == project_id).order_by(CodeFile.path.asc()).all()
    return [{'id': r.id, 'path': r.path, 'language': r.language, 'content': r.content, 'updated_at': r.updated_at} for r in rows]


@router.put('/projects/{project_id}/files')
def upsert_file(project_id: int, payload: CodeFileUpsert, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, project_id)
    path = _safe_path(payload.path)
    record = db.query(CodeFile).filter(CodeFile.project_id == project_id, CodeFile.path == path).first()
    if record is None:
        record = CodeFile(project_id=project_id, path=path)
        db.add(record)
    record.language = payload.language.strip() or 'text'; record.content = payload.content
    project.updated_at = utcnow(); audit(db, current_user, 'codex.file.save', 'code_project', project_id, path); db.commit(); db.refresh(record)
    return {'id': record.id, 'path': record.path, 'language': record.language, 'content': record.content, 'updated_at': record.updated_at}


@router.delete('/projects/{project_id}/files/{file_id}')
def delete_file(project_id: int, file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    record = db.query(CodeFile).filter(CodeFile.id == file_id, CodeFile.project_id == project_id).first()
    if record is None: raise HTTPException(status_code=404, detail='Code file not found')
    path = record.path; db.delete(record); audit(db, current_user, 'codex.file.delete', 'code_project', project_id, path); db.commit()
    return {'deleted': True}


@router.post('/projects/{project_id}/tasks')
def create_task(project_id: int, payload: CodeTaskCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    files = db.query(CodeFile).filter(CodeFile.project_id == project_id).order_by(CodeFile.path.asc()).all()
    task = CodeTask(project_id=project_id, user_id=current_user.id, mode=payload.mode, instruction=payload.instruction, status='running')
    db.add(task); db.flush()
    try:
        result, model = run_codex_task(payload.mode, payload.instruction, [{'path': f.path, 'language': f.language, 'content': f.content} for f in files])
    except OpenAIError as exc:
        task.status = 'failed'; task.result_json = json.dumps({'summary':'Provider error','answer':'The coding model could not complete the request.','files':[],'test_plan':[],'risks':[]}); db.commit()
        raise HTTPException(status_code=502, detail='The coding model could not complete the request.') from exc
    task.status = 'completed'; task.model = model; task.result_json = json.dumps(result); audit(db, current_user, 'codex.task.run', 'code_task', task.id, f'{payload.mode}: {payload.instruction[:300]}'); record_usage(db, current_user, 'codex', payload.mode, 1, f'model={model}'); db.commit(); db.refresh(task)
    return {'id': task.id, 'project_id': task.project_id, 'mode': task.mode, 'instruction': task.instruction, 'status': task.status, 'model': task.model, 'result': result, 'created_at': task.created_at, 'applied_at': task.applied_at}


@router.get('/projects/{project_id}/tasks')
def list_tasks(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    rows = db.query(CodeTask).filter(CodeTask.project_id == project_id, CodeTask.user_id == current_user.id).order_by(CodeTask.created_at.desc()).limit(50).all()
    return [{'id': r.id, 'mode': r.mode, 'instruction': r.instruction, 'status': r.status, 'model': r.model, 'result': json.loads(r.result_json or '{}'), 'created_at': r.created_at, 'applied_at': r.applied_at} for r in rows]


@router.post('/projects/{project_id}/tasks/{task_id}/apply', response_model=CodeTaskApplyResponse)
def apply_task(project_id: int, task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, project_id)
    task = db.query(CodeTask).filter(CodeTask.id == task_id, CodeTask.project_id == project_id, CodeTask.user_id == current_user.id).first()
    if task is None: raise HTTPException(status_code=404, detail='Codex task not found')
    if task.applied_at is not None: raise HTTPException(status_code=409, detail='This task has already been applied')
    result = json.loads(task.result_json or '{}'); proposed = result.get('files') or []
    if not isinstance(proposed, list) or not proposed: raise HTTPException(status_code=400, detail='This task did not propose file changes')
    applied: list[str] = []
    for item in proposed[:30]:
        if not isinstance(item, dict): continue
        path = _safe_path(str(item.get('path','')))
        content = str(item.get('content',''))
        if len(content) > 200000: raise HTTPException(status_code=400, detail=f'Proposed file is too large: {path}')
        record = db.query(CodeFile).filter(CodeFile.project_id == project_id, CodeFile.path == path).first()
        if record is None:
            record = CodeFile(project_id=project_id, path=path); db.add(record)
        record.language = str(item.get('language') or 'text')[:80]; record.content = content; applied.append(path)
    task.applied_at = utcnow(); project.updated_at = utcnow(); audit(db, current_user, 'codex.task.apply', 'code_task', task.id, ', '.join(applied)); db.commit()
    return CodeTaskApplyResponse(task_id=task.id, applied_files=applied)
