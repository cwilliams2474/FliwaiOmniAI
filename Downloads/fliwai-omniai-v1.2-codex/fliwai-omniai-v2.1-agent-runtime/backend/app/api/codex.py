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
from app.codex_utils import safe_relative_path, unified_content_diff
from app.models.core import CodeFile, CodeProject, CodeRevision, CodeTask, User
from app.schemas.core import CodeFileUpsert, CodeProjectCreate, CodeTaskApplyResponse, CodeTaskCreate
from app.usage import record_usage

router = APIRouter(prefix='/codex', tags=['codex'])


def _project(db: Session, user: User, project_id: int) -> CodeProject:
    record = db.query(CodeProject).filter(CodeProject.id == project_id, CodeProject.user_id == user.id).first()
    if record is None:
        raise HTTPException(status_code=404, detail='Code project not found')
    return record




def _with_diffs(db: Session, project_id: int, result: dict) -> dict:
    proposed = result.get('files') if isinstance(result.get('files'), list) else []
    diffs = []
    for item in proposed[:30]:
        if not isinstance(item, dict):
            continue
        try:
            path = safe_relative_path(str(item.get('path', '')))
        except ValueError:
            continue
        current = db.query(CodeFile).filter(CodeFile.project_id == project_id, CodeFile.path == path).first()
        old = current.content if current else ''
        new = str(item.get('content', ''))
        diff = unified_content_diff(path, old, new)
        diffs.append({'path': path, 'diff': diff[:120000], 'is_new': current is None})
    result['diffs'] = diffs
    return result

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
    result = _with_diffs(db, project_id, result)
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
        previous_content = record.content if record is not None else ''
        previous_language = record.language if record is not None else str(item.get('language') or 'text')[:80]
        db.add(CodeRevision(project_id=project_id, task_id=task.id, user_id=current_user.id, path=path, language=previous_language, previous_content=previous_content, new_content=content))
        if record is None:
            record = CodeFile(project_id=project_id, path=path); db.add(record)
        record.language = str(item.get('language') or 'text')[:80]; record.content = content; applied.append(path)
    task.applied_at = utcnow(); project.updated_at = utcnow(); audit(db, current_user, 'codex.task.apply', 'code_task', task.id, ', '.join(applied)); db.commit()
    return CodeTaskApplyResponse(task_id=task.id, applied_files=applied)


@router.get('/projects/{project_id}/revisions')
def list_revisions(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _project(db, current_user, project_id)
    rows = db.query(CodeRevision).filter(CodeRevision.project_id == project_id, CodeRevision.user_id == current_user.id).order_by(CodeRevision.created_at.desc()).limit(100).all()
    return [
        {'id': row.id, 'task_id': row.task_id, 'path': row.path, 'language': row.language, 'created_at': row.created_at, 'rolled_back_at': row.rolled_back_at}
        for row in rows
    ]


@router.post('/projects/{project_id}/revisions/{revision_id}/rollback')
def rollback_revision(project_id: int, revision_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = _project(db, current_user, project_id)
    revision = db.query(CodeRevision).filter(CodeRevision.id == revision_id, CodeRevision.project_id == project_id, CodeRevision.user_id == current_user.id).first()
    if not revision:
        raise HTTPException(status_code=404, detail='Revision not found')
    if revision.rolled_back_at is not None:
        raise HTTPException(status_code=409, detail='Revision has already been rolled back')
    record = db.query(CodeFile).filter(CodeFile.project_id == project_id, CodeFile.path == revision.path).first()
    current_content = record.content if record else ''
    if current_content != revision.new_content:
        raise HTTPException(status_code=409, detail='File changed after this revision; rollback would overwrite newer work')
    if revision.previous_content == '' and record is not None and revision.new_content != '':
        db.delete(record)
    else:
        if record is None:
            record = CodeFile(project_id=project_id, path=revision.path)
            db.add(record)
        record.language = revision.language
        record.content = revision.previous_content
    revision.rolled_back_at = utcnow(); project.updated_at = utcnow()
    audit(db, current_user, 'codex.revision.rollback', 'code_revision', revision.id, revision.path)
    db.commit()
    return {'rolled_back': True, 'revision_id': revision.id, 'path': revision.path}
