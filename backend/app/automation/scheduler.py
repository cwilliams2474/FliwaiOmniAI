"""Runs scheduled workflows. One background thread per backend process; FOR UPDATE SKIP LOCKED
makes it safe if more than one process ever runs."""

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select

from app import cron
from app.automation import runtime
from app.config import get_settings
from app.db import SessionLocal
from app.models import Run, RunStatus, Workflow

log = logging.getLogger("omniai.scheduler")
_stop = threading.Event()
_thread: threading.Thread | None = None


def compute_next(schedule: str, after: datetime | None = None) -> datetime | None:
    if not schedule.strip():
        return None
    return cron.next_after(schedule, after or datetime.now(timezone.utc), get_settings().scheduler_timezone)


def tick(now: datetime | None = None) -> list:
    """Start every due workflow once. Returns the ids of runs started (for tests and logs)."""
    now = now or datetime.now(timezone.utc)
    started = []
    db = SessionLocal()
    try:
        due = list(
            db.scalars(
                select(Workflow)
                .where(Workflow.enabled.is_(True), Workflow.schedule != "", Workflow.next_run_at.is_not(None), Workflow.next_run_at <= now)
                .with_for_update(skip_locked=True)
                .limit(20)
            )
        )
        for wf in due:
            try:
                wf.next_run_at = compute_next(wf.schedule, now)
            except cron.CronError as e:
                log.warning("Workflow %s has a bad schedule (%s); disabling it.", wf.name, e)
                wf.enabled, wf.next_run_at = False, None
                continue
            busy = db.scalar(select(Run.id).where(Run.workflow_id == wf.id, Run.status.in_([RunStatus.running, RunStatus.awaiting_approval])).limit(1))
            if busy:
                log.info("Skipping %s: its previous run hasn't finished.", wf.name)
                continue
            wf.last_run_at = now
            run = runtime.create_run(db, wf.org_id, steps=wf.steps, mode=wf.approval_mode, source_name=wf.name, workflow=wf, trigger="schedule", commit=False)
            started.append(run.id)
        db.commit()
    finally:
        db.close()
    for rid in started:
        try:
            runtime.execute(rid)
        except Exception:  # noqa: BLE001
            log.exception("Scheduled run %s crashed", rid)
    return started


def _loop() -> None:
    interval = max(10, get_settings().scheduler_interval_seconds)
    log.info("Scheduler started (every %ss, time zone %s).", interval, get_settings().scheduler_timezone)
    while not _stop.wait(interval):
        try:
            tick()
        except Exception:  # noqa: BLE001
            log.exception("Scheduler tick failed")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="omniai-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
