import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from openai import OpenAIError
from sqlalchemy.orm import Session

from app.ai.service import get_ai_response
from app.auth.security import get_current_user
from app.config import settings
from app.database.session import get_db
from app.documents import chunk_text, extract_text, score_chunk
from app.models.core import Document, DocumentChunk, User
from app.schemas.core import DocumentAskRequest, DocumentAskResponse
from app.tenancy import current_organization

router = APIRouter(prefix='/documents', tags=['documents'])
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.csv', '.xlsx', '.png', '.jpg', '.jpeg'}
TEXT_EXTENSIONS = {'.pdf', '.docx', '.txt', '.csv'}
MAX_FILE_SIZE = 20 * 1024 * 1024


@router.post('/upload', status_code=201)
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    original_name = Path(file.filename or 'upload').name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail='Unsupported file type')

    os.makedirs(settings.upload_dir, exist_ok=True)
    stored_name = f'{uuid4().hex}{extension}'
    path = Path(settings.upload_dir) / stored_name
    with path.open('wb') as buffer:
        shutil.copyfileobj(file.file, buffer)
    if path.stat().st_size > MAX_FILE_SIZE:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail='File exceeds the 20 MB limit')

    doc = Document(organization_id=org.id, filename=original_name, path=str(path), content_type=file.content_type or '')
    db.add(doc)
    db.flush()

    indexed_chunks = 0
    if extension in TEXT_EXTENSIONS:
        try:
            text = extract_text(path, extension)
            chunks = chunk_text(text)
            for index, content in enumerate(chunks):
                db.add(DocumentChunk(document_id=doc.id, chunk_index=index, content=content))
            indexed_chunks = len(chunks)
        except Exception as exc:
            db.rollback()
            path.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=f'Could not extract text from document: {exc}') from exc

    db.commit()
    db.refresh(doc)
    return {'id': doc.id, 'filename': doc.filename, 'content_type': doc.content_type, 'indexed_chunks': indexed_chunks}


@router.get('')
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    documents = db.query(Document).filter(Document.organization_id == org.id).order_by(Document.created_at.desc()).all()
    return [
        {
            'id': doc.id,
            'filename': doc.filename,
            'content_type': doc.content_type,
            'created_at': doc.created_at,
            'indexed_chunks': db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count(),
        }
        for doc in documents
    ]


@router.post('/ask', response_model=DocumentAskResponse)
def ask_documents(payload: DocumentAskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = current_organization(db, user)
    query = db.query(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id).filter(Document.organization_id == org.id)
    if payload.document_id is not None:
        query = query.filter(DocumentChunk.document_id == payload.document_id)
    rows = query.all()
    if not rows:
        raise HTTPException(status_code=404, detail='No indexed document text is available')

    ranked = sorted(rows, key=lambda row: score_chunk(payload.question, row[0].content), reverse=True)
    selected = [row for row in ranked if score_chunk(payload.question, row[0].content) > 0][:5]
    if not selected:
        selected = ranked[:3]

    context_parts = []
    sources = []
    for chunk, document in selected:
        context_parts.append(f'[{document.filename} chunk {chunk.chunk_index}] {chunk.content}')
        sources.append({'document_id': document.id, 'filename': document.filename, 'chunk_index': chunk.chunk_index})

    prompt = (
        'Answer the question using only the document context below. If the context does not contain enough information, '
        'say that clearly. Cite source filenames in brackets when you use them.\n\n'
        f'QUESTION: {payload.question}\n\nCONTEXT:\n' + '\n\n'.join(context_parts)
    )
    try:
        answer, model = get_ai_response(prompt, 'general')
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail='The AI provider could not complete the document question.') from exc
    return DocumentAskResponse(answer=answer, model=model, sources=sources)
