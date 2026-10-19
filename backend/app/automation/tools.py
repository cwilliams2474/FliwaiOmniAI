"""The fixed set of actions agents and workflows may take.

Every tool works only inside the run's organization. Tools marked write=True change data or send
something outside OmniAI; with approval mode "writes" each of those steps waits for an admin.
Each tool returns a dict that always contains "summary": a short text later steps can use via
{{step N}} in their arguments.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import integrations as ig
from app import rag
from app.ai.provider import AIError, complete, provider_name
from app.audit import record
from app.models import (
    Asset,
    Integration,
    Organization,
    Priority,
    Role,
    Run,
    Ticket,
    TicketComment,
    TicketStatus,
    User,
)
from app.notify import members_with_role, notify


class ToolError(Exception):
    """Expected failure with a message worth showing on the run page."""


@dataclass
class RunContext:
    db: Session
    org: Organization
    run: Run
    actor: User | None  # who started the run; None for scheduled runs

    @property
    def actor_label(self) -> str:
        return f"automation:{self.run.source_name}" + (f" (started by {self.actor.email})" if self.actor else " (scheduled)")


@dataclass
class Param:
    type: str  # string | integer | boolean
    description: str
    required: bool = False
    enum: list[str] | None = None
    max_length: int = 4000


@dataclass
class Tool:
    name: str
    description: str
    write: bool
    params: dict[str, Param]
    fn: Callable[[RunContext, dict], dict]
    needs_ai: bool = False
    extra: dict = field(default_factory=dict)

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "write": self.write,
            "needs_ai": self.needs_ai,
            "params": {k: {"type": p.type, "description": p.description, "required": p.required, "enum": p.enum} for k, p in self.params.items()},
        }


def validate_args(tool: Tool, args: dict) -> dict:
    if not isinstance(args, dict):
        raise ToolError(f"{tool.name}: arguments must be an object.")
    unknown = set(args) - set(tool.params)
    if unknown:
        raise ToolError(f"{tool.name}: unknown argument(s) {', '.join(sorted(unknown))}.")
    clean: dict = {}
    for name, p in tool.params.items():
        v = args.get(name)
        if v is None or v == "":
            if p.required:
                raise ToolError(f"{tool.name}: '{name}' is required.")
            continue
        if p.type == "integer":
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise ToolError(f"{tool.name}: '{name}' must be a whole number.")
        elif p.type == "boolean":
            if isinstance(v, str):
                v = v.strip().lower() in ("1", "true", "yes", "on")
            v = bool(v)
        else:
            v = str(v)[: p.max_length]
        if p.enum and v not in p.enum:
            raise ToolError(f"{tool.name}: '{name}' must be one of {', '.join(p.enum)}.")
        clean[name] = v
    return clean


# ---------------- helpers ----------------
def _ticket(ctx: RunContext, number: int) -> Ticket:
    t = ctx.db.scalar(select(Ticket).where(Ticket.org_id == ctx.org.id, Ticket.number == number))
    if not t:
        raise ToolError(f"Ticket IT-{number} doesn't exist in {ctx.org.name}.")
    return t


def _line(t: Ticket) -> str:
    who = t.assignee.name if t.assignee else "unassigned"
    return f"IT-{t.number} [{t.priority.value}, {t.status.value.replace('_', ' ')}, {who}] {t.title}"


STATUS_GROUPS = {
    "active": [TicketStatus.open, TicketStatus.in_progress, TicketStatus.waiting],
    "open": [TicketStatus.open],
    "in_progress": [TicketStatus.in_progress],
    "waiting": [TicketStatus.waiting],
    "resolved": [TicketStatus.resolved, TicketStatus.closed],
}


# ---------------- read tools ----------------
def tickets_search(ctx: RunContext, a: dict) -> dict:
    stmt = select(Ticket).where(Ticket.org_id == ctx.org.id, Ticket.status.in_(STATUS_GROUPS[a.get("status", "active")]))
    if a.get("priority"):
        stmt = stmt.where(Ticket.priority == Priority(a["priority"]))
    if a.get("unassigned"):
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    if a.get("q"):
        like = f"%{a['q']}%"
        stmt = stmt.where(or_(Ticket.title.ilike(like), Ticket.description.ilike(like)))
    if a.get("older_than_days"):
        stmt = stmt.where(Ticket.updated_at < datetime.now(timezone.utc) - timedelta(days=a["older_than_days"]))
    rows = list(ctx.db.scalars(stmt.order_by(Ticket.priority, Ticket.created_at).limit(min(a.get("limit", 25), 50))))
    lines = [_line(t) for t in rows]
    return {"count": len(rows), "tickets": [{"number": t.number, "title": t.title, "priority": t.priority.value, "status": t.status.value} for t in rows],
            "summary": f"{len(rows)} ticket(s):\n" + "\n".join(lines) if rows else "No tickets match."}


def tickets_get(ctx: RunContext, a: dict) -> dict:
    t = _ticket(ctx, a["number"])
    public = [c for c in t.comments if not c.internal][-5:]
    convo = "\n".join(f"- {c.author.name if c.author else 'someone'}: {c.body[:300]}" for c in public)
    summary = f"{_line(t)}\nRequester: {t.requester.name if t.requester else 'unknown'}\n{t.description[:1500]}" + (f"\nRecent replies:\n{convo}" if convo else "")
    return {"number": t.number, "status": t.status.value, "priority": t.priority.value, "summary": summary}


def assets_search(ctx: RunContext, a: dict) -> dict:
    stmt = select(Asset).where(Asset.org_id == ctx.org.id)
    if a.get("q"):
        like = f"%{a['q']}%"
        stmt = stmt.where(or_(Asset.name.ilike(like), Asset.tag.ilike(like), Asset.location.ilike(like), Asset.os.ilike(like)))
    if a.get("warranty_within_days"):
        stmt = stmt.where(Asset.warranty_end.is_not(None), Asset.warranty_end <= date.today() + timedelta(days=a["warranty_within_days"]))
    rows = list(ctx.db.scalars(stmt.order_by(Asset.warranty_end.nulls_last(), Asset.tag).limit(50)))
    lines = [f"{x.tag} {x.name} ({x.asset_type}, {x.status.value.replace('_', ' ')}, warranty {x.warranty_end or 'n/a'})" for x in rows]
    return {"count": len(rows), "summary": f"{len(rows)} asset(s):\n" + "\n".join(lines) if rows else "No assets match."}


def knowledge_search(ctx: RunContext, a: dict) -> dict:
    hits = rag.search(ctx.db, ctx.org.id, a["q"], limit=4)
    parts = [f"[{h.filename}{', p.' + str(h.page) if h.page else ''}] {h.content[:700]}" for h in hits]
    return {"count": len(hits), "sources": [h.filename for h in hits], "summary": "\n\n".join(parts) if parts else "No matching documents."}


def memory_list(ctx: RunContext, a: dict) -> dict:
    items = rag.org_memory(ctx.db, ctx.org.id)
    return {"count": len(items), "summary": "\n".join(f"- {m.title}: {m.content}" for m in items) or "No memory entries."}


def ai_summarize(ctx: RunContext, a: dict) -> dict:
    if provider_name() not in ("openai", "anthropic"):
        raise ToolError("ai.summarize needs an AI model. Set AI_PROVIDER in .env.")
    system = f"You write short, factual operational summaries for {ctx.org.name}'s IT team. Use only the text provided. No preamble."
    try:
        out = complete(system, [{"role": "user", "content": f"{a['instruction']}\n\n---\n{a['text']}"}])
    except AIError as e:
        raise ToolError(str(e))
    return {"summary": out.text, "model": out.model, "tokens": out.tokens_in + out.tokens_out}


# ---------------- write tools ----------------
def tickets_create(ctx: RunContext, a: dict) -> dict:
    org = ctx.db.scalar(select(Organization).where(Organization.id == ctx.org.id).with_for_update())
    org.ticket_seq += 1
    t = Ticket(org_id=org.id, number=org.ticket_seq, title=a["title"][:300], description=a.get("description", ""),
               priority=Priority(a.get("priority", "P3")), requester_id=ctx.actor.id if ctx.actor else None)
    ctx.db.add(t)
    ctx.db.flush()
    record(ctx.db, "ticket.created", f"IT-{t.number} {t.title}", actor=ctx.actor_label, org_id=org.id, detail={"run": ctx.run.number})
    notify(ctx.db, org.id, members_with_role(ctx.db, org.id, Role.technician), "ticket.new", f"New {t.priority.value} ticket IT-{t.number}: {t.title}",
           f"Created by automation '{ctx.run.source_name}'.", f"/tickets/{t.number}")
    return {"number": t.number, "summary": f"Created IT-{t.number}: {t.title}"}


def tickets_comment(ctx: RunContext, a: dict) -> dict:
    t = _ticket(ctx, a["number"])
    internal = a.get("internal", True)
    ctx.db.add(TicketComment(ticket_id=t.id, author_id=ctx.actor.id if ctx.actor else None, body=f"{a['body']}\n\n— automation: {ctx.run.source_name}", internal=internal))
    record(ctx.db, "ticket.commented", f"IT-{t.number}", actor=ctx.actor_label, org_id=ctx.org.id, detail={"internal": internal, "run": ctx.run.number})
    if not internal:
        notify(ctx.db, ctx.org.id, [t.requester_id], "ticket.reply", f"New reply on your ticket IT-{t.number}", a["body"][:300], f"/tickets/{t.number}", email=True)
    return {"number": t.number, "summary": f"Added {'internal note' if internal else 'reply'} to IT-{t.number}"}


def tickets_update(ctx: RunContext, a: dict) -> dict:
    t = _ticket(ctx, a["number"])
    changes = []
    if a.get("status") and a["status"] != t.status.value:
        changes.append(f"status {t.status.value} → {a['status']}")
        t.status = TicketStatus(a["status"])
    if a.get("priority") and a["priority"] != t.priority.value:
        changes.append(f"priority {t.priority.value} → {a['priority']}")
        t.priority = Priority(a["priority"])
    if not changes:
        return {"number": t.number, "summary": f"IT-{t.number} already had those values; nothing changed."}
    record(ctx.db, "ticket.updated", f"IT-{t.number}", actor=ctx.actor_label, org_id=ctx.org.id, detail={"changes": changes, "run": ctx.run.number})
    return {"number": t.number, "summary": f"IT-{t.number}: " + ", ".join(changes)}


def notify_team(ctx: RunContext, a: dict) -> dict:
    role = Role(a.get("min_role", "technician"))
    n = notify(ctx.db, ctx.org.id, members_with_role(ctx.db, ctx.org.id, role), "automation.message", a["title"], a["body"], f"/runs/{ctx.run.number}")
    return {"recipients": n, "summary": f"Notified {n} {role.value}+ member(s): {a['title']}"}


def integration_send(ctx: RunContext, a: dict) -> dict:
    integ = ctx.db.scalar(select(Integration).where(Integration.org_id == ctx.org.id, Integration.name == a["integration"]))
    if not integ:
        names = ", ".join(ctx.db.scalars(select(Integration.name).where(Integration.org_id == ctx.org.id))) or "none set up"
        raise ToolError(f"No integration named '{a['integration']}'. Available: {names}.")
    try:
        ig.send(integ, a["text"], ctx.org.name)
    except ig.IntegrationError as e:
        raise ToolError(str(e))
    record(ctx.db, "integration.sent", integ.name, actor=ctx.actor_label, org_id=ctx.org.id, detail={"run": ctx.run.number, "chars": len(a["text"])})
    return {"summary": f"Sent {len(a['text'])} characters to {integ.name} ({integ.kind})"}


_P = Param
PRIORITIES = ["P1", "P2", "P3", "P4"]
TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("tickets.search", "Find tickets in this organization.", False, {
            "status": _P("string", "Which tickets: active (default), open, in_progress, waiting or resolved", enum=list(STATUS_GROUPS)),
            "priority": _P("string", "Only this priority", enum=PRIORITIES),
            "unassigned": _P("boolean", "Only tickets with no assignee"),
            "q": _P("string", "Words in the title or description", max_length=200),
            "older_than_days": _P("integer", "Only tickets not updated for this many days"),
            "limit": _P("integer", "Maximum tickets to return (up to 50, default 25)"),
        }, tickets_search),
        Tool("tickets.get", "Read one ticket with its recent public replies.", False, {"number": _P("integer", "Ticket number, e.g. 1042 for IT-1042", required=True)}, tickets_get),
        Tool("assets.search", "Find assets by text or by warranty end date.", False, {
            "q": _P("string", "Words in name, tag, location or OS", max_length=200),
            "warranty_within_days": _P("integer", "Only assets whose warranty ends within this many days"),
        }, assets_search),
        Tool("knowledge.search", "Search the organization's documents for relevant passages.", False, {"q": _P("string", "What to look for", required=True, max_length=400)}, knowledge_search),
        Tool("memory.list", "Read the organization's memory entries.", False, {}, memory_list),
        Tool("ai.summarize", "Have the AI model summarize or rewrite text, such as earlier step results.", False, {
            "text": _P("string", "Text to work on; may include {{step 1}}", required=True, max_length=20000),
            "instruction": _P("string", "What to produce, e.g. 'A 5-line digest for the team'", required=True, max_length=1000),
        }, ai_summarize, needs_ai=True),
        Tool("tickets.create", "Create a new ticket.", True, {
            "title": _P("string", "Ticket title", required=True, max_length=300),
            "description": _P("string", "Details", max_length=10000),
            "priority": _P("string", "Priority (default P3)", enum=PRIORITIES),
        }, tickets_create),
        Tool("tickets.comment", "Add a note or reply to a ticket.", True, {
            "number": _P("integer", "Ticket number", required=True),
            "body": _P("string", "Text of the note", required=True, max_length=10000),
            "internal": _P("boolean", "Internal note hidden from the requester (default true)"),
        }, tickets_comment),
        Tool("tickets.update", "Change a ticket's status or priority.", True, {
            "number": _P("integer", "Ticket number", required=True),
            "status": _P("string", "New status", enum=[s.value for s in TicketStatus]),
            "priority": _P("string", "New priority", enum=PRIORITIES),
        }, tickets_update),
        Tool("notify.team", "Send an in-app notification to members of this organization.", True, {
            "title": _P("string", "Notification title", required=True, max_length=300),
            "body": _P("string", "Message; may include {{step 1}}", required=True, max_length=4000),
            "min_role": _P("string", "Who receives it (default technician and above)", enum=["member", "technician", "admin", "owner"]),
        }, notify_team),
        Tool("integration.send", "Post a message to a connected Slack, Teams or webhook integration.", True, {
            "integration": _P("string", "Integration name as shown on the Integrations page", required=True, max_length=100),
            "text": _P("string", "Message; may include {{step 1}}", required=True, max_length=12000),
        }, integration_send),
    ]
}


def tool_specs() -> list[dict]:
    return [t.spec() for t in TOOLS.values()]

