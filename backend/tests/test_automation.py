from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.ai.provider import Completion
from app.automation import scheduler
from app.db import SessionLocal
from app.models import Workflow
from tests.conftest import add_member

DIGEST = {
    "name": "P1 digest",
    "steps": [
        {"tool": "tickets.search", "args": {"priority": "P1"}},
        {"tool": "tickets.comment", "args": {"number": 1001, "body": "Open P1s right now:\n{{step 1}}", "internal": True}},
        {"tool": "notify.team", "args": {"title": "P1 digest {{date}}", "body": "{{step 1}}"}},
    ],
    "approval_mode": "writes",
}


def _ticket(api, title="Core switch down", prio="P1"):
    return api.post("/api/tickets", json={"title": title, "priority": prio}).json()


def test_workflow_pauses_for_approval_then_completes(owner):
    _ticket(owner)
    wf = owner.post("/api/workflows", json=DIGEST)
    assert wf.status_code == 201, wf.text
    tech = add_member(owner, "tech@example.com", "technician")
    run = tech.post(f"/api/workflows/{wf.json()['id']}/run").json()
    n = run["number"]

    r = tech.get(f"/api/runs/{n}").json()
    assert r["status"] == "awaiting_approval" and r["waiting_step"] == 2
    assert [s["status"] for s in r["steps"]] == ["succeeded", "awaiting_approval", "pending"]
    assert "IT-1001" in r["steps"][0]["result_summary"]

    # Technicians can't approve; admins get a notification and can.
    assert tech.post(f"/api/runs/{n}/steps/2/approve", json={}).status_code == 403
    assert any(x["kind"] == "run.approval" for x in owner.get("/api/notifications").json()["items"])
    assert owner.post(f"/api/runs/{n}/steps/2/approve", json={"note": "ok"}).status_code == 200
    r = owner.get(f"/api/runs/{n}").json()
    assert r["waiting_step"] == 3
    assert owner.post(f"/api/runs/{n}/steps/3/approve", json={}).status_code == 200
    r = owner.get(f"/api/runs/{n}").json()
    assert r["status"] == "completed", r
    assert r["steps"][1]["decided_by"]["email"] == "owner@example.com"

    # The note used the first step's result, and approving twice is refused.
    notes = owner.get("/api/tickets/1001").json()["comments"]
    assert "Open P1s right now" in notes[0]["body"] and "Core switch down" in notes[0]["body"]
    assert owner.post(f"/api/runs/{n}/steps/3/approve", json={}).status_code == 409
    actions = [a["action"] for a in owner.get("/api/orgs/current/audit").json()["items"]]
    assert {"run.started", "run.step_approved", "run.completed"} <= set(actions)


def test_reject_stops_the_run(owner):
    _ticket(owner)
    wf = owner.post("/api/workflows", json=DIGEST).json()
    n = owner.post(f"/api/workflows/{wf['id']}/run").json()["number"]
    r = owner.post(f"/api/runs/{n}/steps/2/reject", json={"note": "not today"}).json()
    assert r["status"] == "rejected"
    assert [s["status"] for s in r["steps"]] == ["succeeded", "rejected", "skipped"]
    assert owner.get("/api/tickets/1001").json()["comments"] == []


def test_failed_step_stops_the_run(owner):
    wf = owner.post("/api/workflows", json={"name": "bad", "approval_mode": "none", "steps": [
        {"tool": "tickets.get", "args": {"number": 9999}},
        {"tool": "notify.team", "args": {"title": "x", "body": "y"}},
    ]}).json()
    n = owner.post(f"/api/workflows/{wf['id']}/run").json()["number"]
    r = owner.get(f"/api/runs/{n}").json()
    assert r["status"] == "failed" and "IT-9999" in r["error"]
    assert [s["status"] for s in r["steps"]] == ["failed", "skipped"]


def test_cancel(owner):
    _ticket(owner)
    wf = owner.post("/api/workflows", json=DIGEST).json()
    n = owner.post(f"/api/workflows/{wf['id']}/run").json()["number"]
    assert owner.post(f"/api/runs/{n}/cancel").json()["status"] == "cancelled"
    assert owner.post(f"/api/runs/{n}/cancel").status_code == 409


def test_workflow_validation(owner):
    bad = [
        {"name": "a", "steps": [{"tool": "shell.exec", "args": {}}]},
        {"name": "b", "steps": [{"tool": "tickets.get", "args": {}}]},
        {"name": "c", "steps": [{"tool": "notify.team", "args": {"title": "x", "body": "{{step 2}}"}}]},
        {"name": "d", "steps": [{"tool": "memory.list", "args": {}}], "schedule": "61 * * * *"},
        {"name": "e", "steps": [{"tool": "memory.list", "args": {"surprise": 1}}]},
        {"name": "f", "steps": []},
    ]
    for body in bad:
        assert owner.post("/api/workflows", json=body).status_code == 422, body
    ok = owner.post("/api/workflows", json={"name": "g", "steps": [{"tool": "memory.list", "args": {}}], "schedule": "0 7 * * 1-5"}).json()
    assert ok["schedule_text"] == "Weekdays at 07:00" and ok["next_run_at"]


def test_agent_plans_with_model(owner, monkeypatch):
    _ticket(owner)
    agent = owner.post("/api/agents", json={"name": "Triage", "tools": ["tickets.search", "tickets.comment"], "approval_mode": "writes", "max_steps": 3}).json()

    def planner(system, messages):
        assert "tickets.search" in system and "integration.send" not in system
        return Completion(text='Here is the plan: {"steps": [{"tool": "tickets.search", "args": {"priority": "P1"}, "why": "find P1s"}, '
                               '{"tool": "tickets.comment", "args": {"number": 1001, "body": "Seen: {{step 1}}"}, "why": "note it"}]}', model="fake")

    monkeypatch.setattr("app.automation.runtime.provider_name", lambda: "openai")
    monkeypatch.setattr("app.automation.runtime.complete", planner)
    r = owner.post(f"/api/agents/{agent['id']}/runs", json={"goal": "Note the open P1s on IT-1001"})
    assert r.status_code == 201, r.text
    detail = owner.get(f"/api/runs/{r.json()['number']}").json()
    assert detail["kind"] == "agent" and detail["waiting_step"] == 2 and detail["steps"][0]["why"] == "find P1s"

    # A plan that reaches for a tool the agent wasn't given is refused before anything runs.
    monkeypatch.setattr("app.automation.runtime.complete", lambda s, m: Completion(text='{"steps": [{"tool": "integration.send", "args": {"integration": "x", "text": "y"}}]}', model="fake"))
    r = owner.post(f"/api/agents/{agent['id']}/runs", json={"goal": "Post to slack"})
    assert r.status_code == 422 and "isn't allowed" in r.json()["detail"]


def test_agent_needs_a_model(owner):
    agent = owner.post("/api/agents", json={"name": "A", "tools": ["memory.list"]}).json()
    r = owner.post(f"/api/agents/{agent['id']}/runs", json={"goal": "What do we know?"})
    assert r.status_code == 422 and "AI model" in r.json()["detail"]


def test_scheduler_tick(owner):
    wf = owner.post("/api/workflows", json={**DIGEST, "name": "sched", "schedule": "* * * * *"}).json()
    _ticket(owner)
    db = SessionLocal()
    db.execute(update(Workflow).values(next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    db.commit()
    db.close()
    assert len(scheduler.tick()) == 1
    runs = owner.get("/api/runs").json()["items"]
    assert runs[0]["trigger"] == "schedule" and runs[0]["status"] == "awaiting_approval"
    # Next tick while that run still waits: skipped, not piled up.
    db = SessionLocal()
    db.execute(update(Workflow).values(next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    db.commit()
    db.close()
    assert scheduler.tick() == []
    assert owner.get(f"/api/workflows").json()[0]["last_run_at"]
    _ = wf


def test_member_cannot_use_automation(owner):
    m = add_member(owner, "staff@example.com", "member")
    assert m.get("/api/runs").status_code == 403
    assert m.get("/api/automation/tools").status_code == 403
