from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.migrations import LATEST_SCHEMA_VERSION, current_schema_version
from app.database.session import get_db

router = APIRouter(prefix='/health', tags=['health'])


@router.get('/live')
def live():
    return {'status': 'ok'}


@router.get('/ready')
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        schema_version = current_schema_version()
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Database is not ready') from exc
    if schema_version < LATEST_SCHEMA_VERSION:
        raise HTTPException(status_code=503, detail=f'Database schema is behind ({schema_version}/{LATEST_SCHEMA_VERSION})')
    return {'status': 'ready', 'database': 'connected', 'schema_version': schema_version}


@router.get('/deep')
def deep(db: Session = Depends(get_db)):
    """Operational probe that verifies DB access and writable upload storage."""
    try:
        db.execute(text('SELECT 1'))
        upload = Path(settings.upload_dir)
        upload.mkdir(parents=True, exist_ok=True)
        probe = upload / '.health-write-probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Deep health check failed') from exc
    return {'status': 'healthy', 'database': 'connected', 'uploads': 'writable', 'schema_version': current_schema_version()}
