"""Bounded execution of agent and workflow runs.

A run is a fixed, numbered list of steps decided up front (by the agent's AI plan or by the
workflow definition). Steps run one at a time, in order. A step that needs approval pauses the
run until an admin approves or rejects it. A failed or rejected step stops the run and every
later step is marked skipped. Nothing is ever retried automatically.
"""

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AIError, complete, provider_name
from app.audit import record
from app.automation.tools import TOOLS, RunContext, ToolError, validate_args
from app.db import SessionLocal
from app.models import (
    Agent,
    ApprovalMode,
    Organization,
    Role,
    Run,
    RunStatus,
    RunStep,
    StepStatus,
    User,
    Workflow,
)
from app.notify import members_with_role, notify

log = logging.getLogger("omniai.automation")

MAX_STEPS = 10
TEMPLATE = re.compile(r"\{\{\s*(step\s+(\d+)|date)\s*\}\}")


class PlanError(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def needs_approval(mode: ApprovalMode, tool_name: str) -> bool:
    if mode == ApprovalMode.all:
        return True
    if mode == ApprovalMode.none:
        return False
    return TOOLS[tool_name].write


def check_steps(steps: list[dict], allowed: list[str] | None = None) -> list[dict]:
    """Validate a list of {"tool", "args", "why"?}. Returns cleaned steps or raises PlanError."""
    if not isinstance(steps, list) or not steps:
        raise PlanError("A plan needs at least one step.")
    if len(steps) > MAX_STEPS:
        raise PlanError(f"Plans are limited to {MAX_STEPS} steps.")
    out = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or s.get("tool") not in TOOLS:
            raise PlanError(f"Step {i}: unknown tool '{s.get('tool') if isinstance(s, dict) else s}'.")
        if allowed is not None and s["tool"] not in allowed:
            raise PlanError(f"Step {i}: this agent isn't allowed to use {s['tool']}.")
        for ref in TEMPLATE.finditer(json.dumps(s.get("args", {}))):
            if ref.group(2) and not (1 <= int(ref.group(2)) < i):
                raise PlanError(f"Step {i}: {{{{step {ref.group(2)}}}}} must refer to an earlier step.")
        # Validate shapes now. Template text in a number/boolean argument is resolved at run time,
        # so a placeholder value stands in for it here.
        tool = TOOLS[s["tool"]]
        probe = {}
        for k, v in (s.get("args") or {}).items():
            p = tool.params.get(k)
            if isinstance(v, str) and TEMPLATE.search(v) and p and p.type != "string":
                v = 1 if p.type == "integer" else True
            probe[k] = v
        try:
            validate_args(tool, probe)
        except ToolError as e:
            raise PlanError(f"Step {i}: {e}")
        out.append({"tool": s["tool"], "args": s.get("args") or {}, "why": str(s.get("why", ""))[:500]})
    return out


# ---------------- planning (agents) ----------------
def plan_agent(db: Session, org: Organization, agent: Agent, goal: str) -> list[dict]:
    if provider_name() not in ("openai", "anthropic"):
        raise PlanError("Agents plan their steps with an AI model, and none is configured. Set AI_PROVIDER in .env, or use a workflow with fixed steps.")
    tools = [TOOLS[t].spec() for t in agent.tools if t in TOOLS]
    if not tools:
        raise PlanError("This agent has no tools enabled.")
    system = (
        f"You plan bounded IT operations runs for {org.name}. You can only use these tools:\n"
        f"{json.dumps(tools, indent=1)}\n\n"
        f"Agent instructions: {agent.instructions or 'none'}\n\n"
        f"Reply with JSON only, no prose: {{\"steps\": [{{\"tool\": \"...\", \"args\": {{...}}, \"why\": \"one short sentence\"}}]}}.\n"
        f"Use at most {min(agent.max_steps, MAX_STEPS)} steps. You can't see results while planning, so a later step can use an earlier "
        "step's result text by writing {{step N}} inside a string argument. Prefer reading before writing. If the goal can't be done with "
        "these tools, return {\"steps\": [], \"reason\": \"...\"}."
    )
    try:
        out = complete(system, [{"role": "user", "content": goal}])
    except AIError as e:
        raise PlanError(str(e))
    text = out.text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0) if m else text)
    except (json.JSONDecodeError, AttributeError):
        raise PlanError("The model didn't return a valid plan. Try rephrasing the goal.")
    steps = data.get("steps") if isinstance(data, dict) else None
    if not steps:
        raise PlanError(f"The agent couldn't plan this: {data.get('reason', 'no steps returned') if isinstance(data, dict) else 'no steps returned'}.")
    if len(steps) > agent.max_steps:
        raise PlanError(f"The plan had {len(steps)} steps; this agent is limited to {agent.max_steps}.")
    return check_steps(steps, allowed=agent.tools)


# ---------------- creating runs ----------------
def create_run(
    db: Session,
    org_id: uuid.UUID,
    *,
    steps: list[dict],
    mode: ApprovalMode,
    source_name: str,
    goal: str = "",
    agent: Agent | None = None,
    workflow: Workflow | None = None,
    started_by: User | None = None,
    trigger: str = "manual",
    commit: bool = True,
) -> Run:
    org = db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    org.run_seq += 1
    run = Run(
        org_id=org.id, number=org.run_seq, agent_id=agent.id if agent else None, workflow_id=workflow.id if workflow else None,
        source_name=source_name, goal=goal, trigger=trigger, approval_mode=mode, status=RunStatus.running,
        started_by_id=started_by.id if started_by else None,
    )
    db.add(run)
    db.flush()
    for i, s in enumerate(steps, 1):
        db.add(RunStep(run_id=run.id, ordinal=i, tool=s["tool"], args=s["args"], why=s.get("why", ""), requires_approval=needs_approval(mode, s["tool"])))
    record(db, "run.started", f"Run #{run.number} {source_name}", user=started_by, actor=None if started_by else f"scheduler:{source_name}", org_id=org.id,
           detail={"steps": len(steps), "trigger": trigger, "approval_mode": mode.value})
    if commit:
        db.commit()
        db.refresh(run)
    else:
        db.flush()
    return run


# ---------------- execution ----------------
def _render(value, results: dict[int, str]):
    if isinstance(value, str):
        def sub(m):
            if m.group(1) == "date":
                return date.today().isoformat()
            return results.get(int(m.group(2)), "")
        return TEMPLATE.sub(sub, value)
    if isinstance(value, dict):
        return {k: _render(v, results) for k, v in value.items()}
    return value


def _finish(db: Session, run: Run, status: RunStatus, error: str = "") -> None:
    run.status = status
    run.error = error[:2000]
    run.finished_at = now()
    for s in run.steps:
        if s.status in (StepStatus.pending, StepStatus.awaiting_approval, StepStatus.approved):
            s.status = StepStatus.skipped
    link = f"/runs/{run.number}"
    if status == RunStatus.failed:
        to = [run.started_by_id] if run.started_by_id else members_with_role(db, run.org_id, Role.admin)
        notify(db, run.org_id, to, "run.failed", f"Run #{run.number} {run.source_name} failed", error[:500], link, email=run.trigger == "schedule")
    elif status == RunStatus.completed and run.started_by_id and any(s.requires_approval for s in run.steps):
        notify(db, run.org_id, [run.started_by_id], "run.completed", f"Run #{run.number} {run.source_name} finished", "All steps succeeded.", link)


def execute(run_id: uuid.UUID) -> None:
    """Advance a run as far as it can go. Safe to call more than once; a row lock serializes callers."""
    db = SessionLocal()
    try:
        while True:
            db.expire_all()  # always decide from the committed state
            run = db.scalar(select(Run).where(Run.id == run_id).with_for_update().execution_options(populate_existing=True))
            if not run or run.status != RunStatus.running:
                db.commit()
                return
            step = next((s for s in run.steps if s.status not in (StepStatus.succeeded,)), None)
            if step is None:
                _finish(db, run, RunStatus.completed)
                record(db, "run.completed", f"Run #{run.number} {run.source_name}", actor="automation", org_id=run.org_id)
                db.commit()
                return
            if step.status in (StepStatus.failed, StepStatus.rejected, StepStatus.skipped, StepStatus.running):
                # Shouldn't happen for a running run; stop rather than guess.
                _finish(db, run, RunStatus.failed, f"Step {step.ordinal} is {step.status.value}; the run can't continue.")
                db.commit()
                return
            if step.status == StepStatus.pending and step.requires_approval:
                step.status = StepStatus.awaiting_approval
                run.status = RunStatus.awaiting_approval
                notify(db, run.org_id, members_with_role(db, run.org_id, Role.admin), "run.approval",
                       f"Approval needed: run #{run.number} {run.source_name}, step {step.ordinal}",
                       f"{TOOLS[step.tool].description} {json.dumps(step.args)[:300]}", f"/runs/{run.number}", email=True)
                db.commit()
                return

            # pending (no approval needed) or approved: run it, holding the lock.
            results = {s.ordinal: (s.result or {}).get("summary", "") for s in run.steps if s.status == StepStatus.succeeded}
            step.status = StepStatus.running
            step.started_at = now()
            org = db.get(Organization, run.org_id)
            actor = db.get(User, run.started_by_id) if run.started_by_id else None
            tool = TOOLS[step.tool]
            try:
                args = validate_args(tool, _render(step.args, results))
                result = tool.fn(RunContext(db=db, org=org, run=run, actor=actor), args)
                step.result = result
                step.status = StepStatus.succeeded
                step.finished_at = now()
                db.commit()
            except ToolError as e:
                db.rollback()
                _fail_step(db, run_id, step.id, str(e))
                return
            except Exception as e:  # noqa: BLE001
                log.exception("Run %s step %s crashed", run_id, step.ordinal)
                db.rollback()
                _fail_step(db, run_id, step.id, f"Unexpected error in {step.tool}: {e.__class__.__name__}. See the backend log.")
                return
    finally:
        db.close()


def _fail_step(db: Session, run_id: uuid.UUID, step_id: uuid.UUID, message: str) -> None:
    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update().execution_options(populate_existing=True))
    step = db.get(RunStep, step_id)
    step.status = StepStatus.failed
    step.error = message[:2000]
    step.finished_at = now()
    _finish(db, run, RunStatus.failed, f"Step {step.ordinal} ({step.tool}) failed: {message}")
    record(db, "run.failed", f"Run #{run.number} {run.source_name}", actor="automation", org_id=run.org_id, detail={"step": step.ordinal, "error": message[:300]})
    db.commit()


# ---------------- decisions ----------------
class DecisionError(Exception):
    pass


def _awaiting(db: Session, run: Run, ordinal: int) -> RunStep:
    step = next((s for s in run.steps if s.ordinal == ordinal), None)
    if not step:
        raise DecisionError(f"Run #{run.number} has no step {ordinal}.")
    if step.status != StepStatus.awaiting_approval or run.status != RunStatus.awaiting_approval:
        raise DecisionError(f"Step {ordinal} isn't waiting for a decision (it is {step.status.value.replace('_', ' ')}).")
    return step


def _lock(db: Session, run: Run) -> None:
    db.expire_all()
    db.refresh(run, with_for_update=True)


def approve(db: Session, run: Run, ordinal: int, user: User, note: str = "") -> None:
    _lock(db, run)
    step = _awaiting(db, run, ordinal)
    step.status = StepStatus.approved
    step.decided_by_id, step.decided_at, step.decision_note = user.id, now(), note[:1000]
    run.status = RunStatus.running
    record(db, "run.step_approved", f"Run #{run.number} step {ordinal} ({step.tool})", user=user, org_id=run.org_id, detail={"note": note[:200]})
    db.commit()


def reject(db: Session, run: Run, ordinal: int, user: User, note: str = "") -> None:
    _lock(db, run)
    step = _awaiting(db, run, ordinal)
    step.status = StepStatus.rejected
    step.decided_by_id, step.decided_at, step.decision_note = user.id, now(), note[:1000]
    run.status = RunStatus.rejected
    run.finished_at = now()
    run.error = f"Step {ordinal} ({step.tool}) was rejected by {user.name}" + (f": {note}" if note else ".")
    for s in run.steps:
        if s.status in (StepStatus.pending, StepStatus.awaiting_approval):
            s.status = StepStatus.skipped
    record(db, "run.step_rejected", f"Run #{run.number} step {ordinal} ({step.tool})", user=user, org_id=run.org_id, detail={"note": note[:200]})
    notify(db, run.org_id, [run.started_by_id], "run.rejected", f"Run #{run.number} {run.source_name} was stopped", run.error, f"/runs/{run.number}", exclude=user.id)
    db.commit()


def cancel(db: Session, run: Run, user: User) -> None:
    _lock(db, run)
    if run.status not in (RunStatus.running, RunStatus.awaiting_approval):
        raise DecisionError(f"Run #{run.number} already ended ({run.status.value}).")
    run.status = RunStatus.cancelled
    run.finished_at = now()
    run.error = f"Cancelled by {user.name}."
    for s in run.steps:
        if s.status in (StepStatus.pending, StepStatus.awaiting_approval, StepStatus.approved):
            s.status = StepStatus.skipped
    record(db, "run.cancelled", f"Run #{run.number} {run.source_name}", user=user, org_id=run.org_id)
    db.commit()
