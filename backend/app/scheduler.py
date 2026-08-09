import threading
from datetime import datetime, timedelta

from app.time_utils import utcnow
from app.database.session import SessionLocal
from app.models.core import Notification, User, Workflow, WorkflowSchedule
from app.workflows import execute_workflow

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_due_schedules_once(now: datetime | None = None) -> int:
    current = now or utcnow()
    db = SessionLocal()
    executed = 0
    try:
        schedules = db.query(WorkflowSchedule).filter(WorkflowSchedule.enabled.is_(True), WorkflowSchedule.next_run_at <= current).all()
        for schedule in schedules:
            workflow = db.query(Workflow).filter(Workflow.id == schedule.workflow_id, Workflow.enabled.is_(True)).first()
            user = db.query(User).filter(User.id == schedule.user_id, User.is_active.is_(True)).first()
            schedule.last_run_at = current
            schedule.next_run_at = current + timedelta(minutes=max(5, schedule.interval_minutes))
            if not workflow or not user:
                continue
            run = execute_workflow(db, workflow, user, schedule.input_text)
            db.add(Notification(user_id=user.id, title=f'Workflow {workflow.name}: {run.status}', body=f'Scheduled run #{run.id} finished with status {run.status}.', level='success' if run.status == 'completed' else 'error'))
            db.commit(); executed += 1
        return executed
    finally:
        db.close()


def _loop() -> None:
    while not _stop.wait(30):
        try:
            run_due_schedules_once()
        except Exception:
            # Background scheduling must never crash the API process.
            continue


def start_scheduler() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear(); _thread = threading.Thread(target=_loop, name='omniai-scheduler', daemon=True); _thread.start()


def stop_scheduler() -> None:
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)
