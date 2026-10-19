import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import rag
from app.ai.provider import AIError, complete, provider_name
from app.audit import record
from app.config import get_settings
from app.db import get_db
from app.deps import OrgContext, get_org_ctx
from app.models import ChatMessage, Conversation
from app.schemas import Ok, iso

router = APIRouter(prefix="/chat", tags=["chat"])

HISTORY_TURNS = 10


class Citation(BaseModel):
    n: int
    document_id: str
    filename: str
    page: int | None
    excerpt: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[Citation]
    model: str
    created_at: str


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


def _msg(m: ChatMessage) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, citations=[Citation(**c) for c in (m.citations or [])], model=m.model, created_at=iso(m.created_at))


def _conv(c: Conversation) -> ConversationOut:
    return ConversationOut(id=c.id, title=c.title, created_at=iso(c.created_at), updated_at=iso(c.updated_at))


def _get(db: Session, ctx: OrgContext, cid: uuid.UUID) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == cid, Conversation.org_id == ctx.org.id, Conversation.user_id == ctx.user.id))
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return c


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Conversation).where(Conversation.org_id == ctx.org.id, Conversation.user_id == ctx.user.id).order_by(Conversation.updated_at.desc()).limit(100)
    )
    return [_conv(c) for c in rows]


class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


@router.post("/conversations", response_model=ConversationDetail, status_code=201)
def create_conversation(body: ConversationIn, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    c = Conversation(org_id=ctx.org.id, user_id=ctx.user.id, title=body.title.strip())
    db.add(c)
    db.commit()
    db.refresh(c)
    return ConversationDetail(**_conv(c).model_dump(), messages=[])


@router.get("/conversations/{cid}", response_model=ConversationDetail)
def get_conversation(cid: uuid.UUID, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    c = _get(db, ctx, cid)
    return ConversationDetail(**_conv(c).model_dump(), messages=[_msg(m) for m in c.messages])


@router.patch("/conversations/{cid}", response_model=ConversationOut)
def rename_conversation(cid: uuid.UUID, body: ConversationIn, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    c = _get(db, ctx, cid)
    c.title = body.title.strip()
    db.commit()
    return _conv(c)


@router.delete("/conversations/{cid}", response_model=Ok)
def delete_conversation(cid: uuid.UUID, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    db.delete(_get(db, ctx, cid))
    db.commit()
    return Ok()


def build_system_prompt(org_name: str, memory: list, hits: list[rag.Hit]) -> str:
    parts = [
        f"You are the {get_settings().app_name} assistant for {org_name}. Answer questions about the organization's systems, "
        "policies and IT work using the company knowledge below.",
        "Rules: Base answers on the sources when they cover the question and cite them inline as [1], [2]. "
        "If the sources don't cover it, say so plainly, then give general guidance clearly labeled as general. "
        "Never invent internal hostnames, IPs, contacts or policies. Be concise and practical.",
    ]
    if memory:
        parts.append("Organization facts (always true for this organization):\n" + "\n".join(f"- {m.title}: {m.content}" for m in memory))
    if hits:
        src = []
        for i, h in enumerate(hits, 1):
            loc = f", page {h.page}" if h.page else ""
            src.append(f"[{i}] {h.filename}{loc}\n{h.content}")
        parts.append("Sources:\n\n" + "\n\n".join(src))
    else:
        parts.append("Sources: none matched this question.")
    return "\n\n".join(parts)


class SendIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class SendOut(BaseModel):
    conversation: ConversationOut
    user_message: MessageOut
    assistant_message: MessageOut


@router.post("/conversations/{cid}/messages", response_model=SendOut)
def send_message(cid: uuid.UUID, body: SendIn, request: Request, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    c = _get(db, ctx, cid)
    question = body.content.strip()
    hits = rag.search(db, ctx.org.id, question, limit=6)
    memory = rag.org_memory(db, ctx.org.id)
    citations = [
        {"n": i, "document_id": str(h.document_id), "filename": h.filename, "page": h.page, "excerpt": h.content[:400]} for i, h in enumerate(hits, 1)
    ]

    if provider_name() in ("openai", "anthropic"):
        history = [{"role": m.role, "content": m.content} for m in c.messages[-HISTORY_TURNS * 2 :]]
        history.append({"role": "user", "content": question})
        try:
            result = complete(build_system_prompt(ctx.org.name, memory, hits), history)
        except AIError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
        answer, model, tin, tout = result.text or "(The model returned an empty answer.)", result.model, result.tokens_in, result.tokens_out
        used = {int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)}
        if used:
            citations = [x for x in citations if x["n"] in used]
        else:
            citations = []
    else:
        model, tin, tout = "search-only", 0, 0
        if hits:
            lines = [f"[{x['n']}] {x['filename']}{', p.' + str(x['page']) if x['page'] else ''}: {hits[x['n'] - 1].content[:500]}" for x in citations[:3]]
            answer = "No AI model is configured, so here are the most relevant passages from your documents:\n\n" + "\n\n".join(lines)
            citations = citations[:3]
        else:
            answer = "No AI model is configured, and no documents matched. Upload documents, or set AI_PROVIDER in .env to get generated answers."

    um = ChatMessage(conversation_id=c.id, role="user", content=question)
    db.add(um)
    db.flush()
    am = ChatMessage(conversation_id=c.id, role="assistant", content=answer, citations=citations, model=model, tokens_in=tin, tokens_out=tout)
    db.add(am)
    if c.title == "New conversation":
        c.title = (question[:60] + "…") if len(question) > 60 else question
    c.updated_at = datetime.now(timezone.utc)
    record(db, "chat.message", str(c.id), user=ctx.user, org_id=ctx.org.id, detail={"model": model, "sources": len(citations), "tokens": tin + tout}, request=request)
    db.commit()
    db.refresh(um)
    db.refresh(am)
    return SendOut(conversation=_conv(c), user_message=_msg(um), assistant_message=_msg(am))

