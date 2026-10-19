import os
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.ai.provider import provider_name
from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["health"])
STARTED = time.time()


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    checks: dict[str, dict] = {}
    t = time.perf_counter()
    try:
        db.execute(text("select 1"))
        rev = db.execute(text("select version_num from alembic_version")).scalar()
        checks["database"] = {"ok": True, "ms": round((time.perf_counter() - t) * 1000, 1), "migration": rev}
    except Exception as e:  # noqa: BLE001
        checks["database"] = {"ok": False, "error": e.__class__.__name__}
    up = s.upload_dir
    checks["uploads"] = {"ok": up.exists() and os.access(up, os.W_OK)}
    checks["ai_provider"] = {"ok": True, "provider": provider_name(), "model": s.ai_model if provider_name() != "none" else None}
    checks["smtp"] = {"ok": True, "configured": bool(s.smtp_host)}
    checks["scheduler"] = {"ok": True, "enabled": s.scheduler_enabled, "timezone": s.scheduler_timezone}
    ok = checks["database"]["ok"] and checks["uploads"]["ok"]
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "version": __version__, "uptime_seconds": int(time.time() - STARTED), "checks": checks}
