"""Agents, workflows and their runs.

Who can do what:
  technician+  start agent runs and workflow runs, view runs
  admin+       create/edit agents, workflows and integrations; approve or reject steps
  starter      can cancel their own run (admins can cancel any)
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cron
from app.audit import record
from app.automation import runtime
from app.automation.scheduler import compute_next
from app.automation.tools import TOOLS, tool_specs
from app.db import get_db
from app.deps import OrgContext, require_role
from app.models import Agent, ApprovalMode, Role, Run, RunStatus, Workflow
from app.schemas import Ok, UserBrief, iso

router = APIRouter(tags=["automation"])


@router.get("/automation/tools")
def list_tools(ctx: OrgContext = Depends(require_role(Role.technician))):
    return tool_specs()


# ============================== agents ==============================
class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=8000)
    tools: list[str] = Field(default_factory=list)
    approval_mode: ApprovalMode = ApprovalMode.writes
    max_steps: int = Field(default=6, ge=1, le=runtime.MAX_STEPS)
    enabled: bool = True


class AgentOut(AgentIn):
    id: uuid.UUID
    created_at: str


def _agent_out(a: Agent) -> AgentOut:
    return AgentOut(id=a.id, name=a.name, description=a.description, instructions=a.instructions, tools=a.tools or [], approval_mode=a.approval_mode,
                    max_steps=a.max_steps, enabled=a.enabled, created_at=iso(a.created_at))


def _check_tools(names: list[str]) -> list[str]:
    bad = [t for t in names if t not in TOOLS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown tool(s): {', '.join(bad)}.")
    if not names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick at least one tool.")
    return list(dict.fromkeys(names))


def _get_agent(db: Session, ctx: OrgContext, aid: uuid.UUID) -> Agent:
    a = db.scalar(select(Agent).where(Agent.org_id == ctx.org.id, Agent.id == aid))
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found.")
    return a


@router.get("/agents", response_model=list[AgentOut])
def list_agents(ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    return [_agent_out(a) for a in db.scalars(select(Agent).where(Agent.org_id == ctx.org.id).order_by(Agent.name))]


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_agent(body: AgentIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    if db.scalar(select(Agent.id).where(Agent.org_id == ctx.org.id, Agent.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, f"An agent named {body.name} already exists.")
    a = Agent(org_id=ctx.org.id, created_by_id=ctx.user.id, **{**body.model_dump(), "name": body.name.strip(), "tools": _check_tools(body.tools)})
    db.add(a)
    record(db, "agent.created", a.name, user=ctx.user, org_id=ctx.org.id, detail={"tools": a.tools, "approval_mode": a.approval_mode.value}, request=request)
    db.commit()
    db.refresh(a)
    return _agent_out(a)


@router.put("/agents/{aid}", response_model=AgentOut)
def update_agent(aid: uuid.UUID, body: AgentIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    a = _get_agent(db, ctx, aid)
    for k, v in {**body.model_dump(), "name": body.name.strip(), "tools": _check_tools(body.tools)}.items():
        setattr(a, k, v)
    record(db, "agent.updated", a.name, user=ctx.user, org_id=ctx.org.id, detail={"tools": a.tools, "approval_mode": a.approval_mode.value}, request=request)
    db.commit()
    return _agent_out(a)


@router.delete("/agents/{aid}", response_model=Ok)
def delete_agent(aid: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    a = _get_agent(db, ctx, aid)
    record(db, "agent.deleted", a.name, user=ctx.user, org_id=ctx.org.id, request=request)
    db.delete(a)
    db.commit()
    return Ok()


class GoalIn(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)


# ============================== runs ==============================
class StepOut(BaseModel):
    ordinal: int
    tool: str
    write: bool
    args: dict
    why: str
    requires_approval: bool
    status: str
    result_summary: str
    error: str
    decided_by: UserBrief | None
    decided_at: str | None
    decision_note: str
    started_at: str | None
    finished_at: str | None


class RunOut(BaseModel):
    id: uuid.UUID
    number: int
    source_name: str
    kind: str
    goal: str
    trigger: str
    approval_mode: str
    status: str
    error: str
    started_by: UserBrief | None
    created_at: str
    finished_at: str | None
    step_count: int
    waiting_step: int | None


class RunDetail(RunOut):
    steps: list[StepOut]


def _run_out(r: Run) -> dict:
    waiting = next((s.ordinal for s in r.steps if s.status.value == "awaiting_approval"), None)
    return dict(
        id=r.id, number=r.number, source_name=r.source_name, kind="agent" if r.agent_id else "workflow" if r.workflow_id else "deleted",
        goal=r.goal, trigger=r.trigger, approval_mode=r.approval_mode.value, status=r.status.value, error=r.error,
        started_by=UserBrief.model_validate(r.started_by) if r.started_by else None, created_at=iso(r.created_at), finished_at=iso(r.finished_at),
        step_count=len(r.steps), waiting_step=waiting,
    )


def _run_detail(r: Run) -> RunDetail:
    steps = [
        StepOut(
            ordinal=s.ordinal, tool=s.tool, write=TOOLS[s.tool].write if s.tool in TOOLS else True, args=s.args or {}, why=s.why,
            requires_approval=s.requires_approval, status=s.status.value, result_summary=(s.result or {}).get("summary", "")[:6000], error=s.error,
            decided_by=UserBrief.model_validate(s.decided_by) if s.decided_by else None, decided_at=iso(s.decided_at), decision_note=s.decision_note,
            started_at=iso(s.started_at), finished_at=iso(s.finished_at),
        )
        for s in r.steps
    ]
    return RunDetail(**_run_out(r), steps=steps)


def _get_run(db: Session, ctx: OrgContext, number: int) -> Run:
    r = db.scalar(select(Run).where(Run.org_id == ctx.org.id, Run.number == number))
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run #{number} not found.")
    return r


@router.post("/agents/{aid}/runs", response_model=RunDetail, status_code=201)
def start_agent_run(aid: uuid.UUID, body: GoalIn, background: BackgroundTasks, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    a = _get_agent(db, ctx, aid)
    if not a.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{a.name} is turned off.")
    try:
        steps = runtime.plan_agent(db, ctx.org, a, body.goal.strip())
    except runtime.PlanError as e:
        record(db, "run.plan_failed", a.name, user=ctx.user, org_id=ctx.org.id, detail={"error": str(e)[:300]}, commit=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    r = runtime.create_run(db, ctx.org.id, steps=steps, mode=a.approval_mode, source_name=a.name, goal=body.goal.strip(), agent=a, started_by=ctx.user)
    background.add_task(runtime.execute, r.id)
    return _run_detail(r)


@router.get("/runs")
def list_runs(
    ctx: OrgContext = Depends(require_role(Role.technician)),
    db: Session = Depends(get_db),
    status_: list[RunStatus] = Query(default=[], alias="status"),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    stmt = select(Run).where(Run.org_id == ctx.org.id)
    if status_:
        stmt = stmt.where(Run.status.in_(status_))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Run.number.desc()).limit(limit).offset(offset))
    return {"total": total, "items": [RunOut(**_run_out(r)) for r in rows]}


@router.get("/runs/{number}", response_model=RunDetail)
def get_run(number: int, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    return _run_detail(_get_run(db, ctx, number))


class DecisionIn(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.post("/runs/{number}/steps/{ordinal}/approve", response_model=RunDetail)
def approve_step(number: int, ordinal: int, body: DecisionIn, background: BackgroundTasks, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    r = _get_run(db, ctx, number)
    try:
        runtime.approve(db, r, ordinal, ctx.user, body.note)
    except runtime.DecisionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    background.add_task(runtime.execute, r.id)
    return _run_detail(r)


@router.post("/runs/{number}/steps/{ordinal}/reject", response_model=RunDetail)
def reject_step(number: int, ordinal: int, body: DecisionIn, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    r = _get_run(db, ctx, number)
    try:
        runtime.reject(db, r, ordinal, ctx.user, body.note)
    except runtime.DecisionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return _run_detail(r)


@router.post("/runs/{number}/cancel", response_model=RunDetail)
def cancel_run(number: int, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    r = _get_run(db, ctx, number)
    if r.started_by_id != ctx.user.id and not ctx.at_least(Role.admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the person who started this run, or an admin, can cancel it.")
    try:
        runtime.cancel(db, r, ctx.user)
    except runtime.DecisionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return _run_detail(r)


# ============================== workflows ==============================
class WorkflowStepIn(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    why: str = ""


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    steps: list[WorkflowStepIn]
    schedule: str = Field(default="", max_length=100)
    approval_mode: ApprovalMode = ApprovalMode.writes
    enabled: bool = True


class WorkflowOut(WorkflowIn):
    id: uuid.UUID
    schedule_text: str
    next_run_at: str | None
    last_run_at: str | None


def _wf_out(w: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=w.id, name=w.name, description=w.description, steps=[WorkflowStepIn(**s) for s in (w.steps or [])], schedule=w.schedule,
        approval_mode=w.approval_mode, enabled=w.enabled, schedule_text=cron.describe(w.schedule) if w.schedule else "Manual only",
        next_run_at=iso(w.next_run_at), last_run_at=iso(w.last_run_at),
    )


def _validated(body: WorkflowIn) -> tuple[list[dict], str]:
    try:
        steps = runtime.check_steps([s.model_dump() for s in body.steps])
    except runtime.PlanError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    sched = " ".join(body.schedule.split())
    if sched:
        try:
            compute_next(sched)
        except cron.CronError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Schedule: {e}")
    return steps, sched


def _get_wf(db: Session, ctx: OrgContext, wid: uuid.UUID) -> Workflow:
    w = db.scalar(select(Workflow).where(Workflow.org_id == ctx.org.id, Workflow.id == wid))
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found.")
    return w


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    return [_wf_out(w) for w in db.scalars(select(Workflow).where(Workflow.org_id == ctx.org.id).order_by(Workflow.name))]


@router.post("/workflows", response_model=WorkflowOut, status_code=201)
def create_workflow(body: WorkflowIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    steps, sched = _validated(body)
    if db.scalar(select(Workflow.id).where(Workflow.org_id == ctx.org.id, Workflow.name == body.name.strip())):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A workflow named {body.name} already exists.")
    w = Workflow(org_id=ctx.org.id, name=body.name.strip(), description=body.description, steps=steps, schedule=sched, approval_mode=body.approval_mode,
                 enabled=body.enabled, next_run_at=compute_next(sched) if sched and body.enabled else None, created_by_id=ctx.user.id)
    db.add(w)
    record(db, "workflow.created", w.name, user=ctx.user, org_id=ctx.org.id, detail={"schedule": sched, "steps": [s["tool"] for s in steps]}, request=request)
    db.commit()
    db.refresh(w)
    return _wf_out(w)


@router.put("/workflows/{wid}", response_model=WorkflowOut)
def update_workflow(wid: uuid.UUID, body: WorkflowIn, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    w = _get_wf(db, ctx, wid)
    steps, sched = _validated(body)
    w.name, w.description, w.steps, w.schedule, w.approval_mode, w.enabled = body.name.strip(), body.description, steps, sched, body.approval_mode, body.enabled
    w.next_run_at = compute_next(sched) if sched and body.enabled else None
    record(db, "workflow.updated", w.name, user=ctx.user, org_id=ctx.org.id, detail={"schedule": sched, "steps": [s["tool"] for s in steps], "enabled": w.enabled}, request=request)
    db.commit()
    return _wf_out(w)


@router.delete("/workflows/{wid}", response_model=Ok)
def delete_workflow(wid: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.admin)), db: Session = Depends(get_db)):
    w = _get_wf(db, ctx, wid)
    record(db, "workflow.deleted", w.name, user=ctx.user, org_id=ctx.org.id, request=request)
    db.delete(w)
    db.commit()
    return Ok()


@router.post("/workflows/{wid}/run", response_model=RunDetail, status_code=201)
def run_workflow(wid: uuid.UUID, background: BackgroundTasks, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    w = _get_wf(db, ctx, wid)
    r = runtime.create_run(db, ctx.org.id, steps=w.steps, mode=w.approval_mode, source_name=w.name, workflow=w, started_by=ctx.user)
    background.add_task(runtime.execute, r.id)
    return _run_detail(r)
