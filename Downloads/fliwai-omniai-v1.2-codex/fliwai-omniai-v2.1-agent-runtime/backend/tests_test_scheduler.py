from datetime import datetime, timedelta

from app.time_utils import utcnow
from app.models.core import WorkflowSchedule


def test_schedule_model_interval_contract():
    now = utcnow()
    row = WorkflowSchedule(workflow_id=1, user_id=1, interval_minutes=30, input_text='hello', next_run_at=now + timedelta(minutes=30))
    assert row.interval_minutes == 30
    assert row.next_run_at > now
