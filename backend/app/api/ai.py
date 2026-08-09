from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from sqlalchemy.orm import Session

from app.ai.service import get_ai_response
from app.auth.security import get_current_user
from app.database.session import get_db
from app.models.core import Chat, Message, User
from app.schemas.core import AIChatRequest, AIChatResponse, ChatDetail, ChatSummary
from app.usage import record_usage

router = APIRouter(prefix='/ai', tags=['ai'])


def _owned_chat(db: Session, user: User, chat_id: int) -> Chat:
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if chat is None:
        raise HTTPException(status_code=404, detail='Chat not found')
    return chat


@router.post('/chat', response_model=AIChatResponse)
def chat(
    payload: AIChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat_record = _owned_chat(db, current_user, payload.chat_id) if payload.chat_id else Chat(
        user_id=current_user.id,
        title=payload.message.strip()[:80],
    )
    if chat_record.id is None:
        db.add(chat_record)
        db.flush()

    db.add(Message(chat_id=chat_record.id, role='user', content=payload.message))
    try:
        response, model = get_ai_response(payload.message, payload.tool)
    except OpenAIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail='The AI provider could not complete the request.') from exc

    db.add(Message(chat_id=chat_record.id, role='assistant', content=response))
    record_usage(db, current_user, 'ai', 'chat', 1, f'model={model} tool={payload.tool}')
    db.commit()
    return AIChatResponse(response=response, model=model, chat_id=chat_record.id)


@router.get('/chats', response_model=list[ChatSummary])
def list_chats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Chat)
        .filter(Chat.user_id == current_user.id)
        .order_by(Chat.created_at.desc())
        .all()
    )


@router.get('/chats/{chat_id}', response_model=ChatDetail)
def get_chat(chat_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _owned_chat(db, current_user, chat_id)
