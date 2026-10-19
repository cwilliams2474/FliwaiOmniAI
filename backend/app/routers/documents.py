import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import rag
from app.audit import record
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import OrgContext, get_org_ctx, require_role
from app.models import DocStatus, Document, Role
from app.schemas import Ok, UserBrief, iso

router = APIRouter(prefix="/documents", tags=["documents"])


class DocOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    error: str
    chunk_count: int
    uploaded_by: UserBrief | None
    created_at: str


def _out(d: Document) -> DocOut:
    return DocOut(
        id=d.id,
        filename=d.filename,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        sha256=d.sha256,
        status=d.status.value,
        error=d.error,
        chunk_count=d.chunk_count,
        uploaded_by=UserBrief.model_validate(d.uploaded_by) if d.uploaded_by else None,
        created_at=iso(d.created_at),
    )


def _get(db: Session, ctx: OrgContext, doc_id: uuid.UUID) -> Document:
    d = db.scalar(select(Document).where(Document.org_id == ctx.org.id, Document.id == doc_id))
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return d


def _path(d: Document) -> Path:
    return get_settings().upload_dir / d.storage_path


def _index_in_background(doc_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        d = db.get(Document, doc_id)
        if d:
            rag.index_document(db, d, _path(d).read_bytes())
    finally:
        db.close()


@router.get("", response_model=list[DocOut])
def list_documents(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return [_out(d) for d in db.scalars(select(Document).where(Document.org_id == ctx.org.id).order_by(Document.created_at.desc()))]


@router.post("", response_model=DocOut, status_code=201)
def upload_document(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ctx: OrgContext = Depends(require_role(Role.technician)),
    db: Session = Depends(get_db),
):
    s = get_settings()
    name = Path(file.filename or "upload").name[:250]
    ext = Path(name).suffix.lower()
    if ext not in rag.SUPPORTED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload PDF, Word (.docx), HTML, Markdown, CSV or text files.")
    limit = s.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Files can be up to {s.max_upload_mb} MB.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file is empty.")
    digest = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(Document).where(Document.org_id == ctx.org.id, Document.sha256 == digest))
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This file is already in the library as {dup.filename}.")
    doc_id = uuid.uuid4()
    rel = f"{ctx.org.id}/{doc_id}{ext}"
    dest = s.upload_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    d = Document(
        id=doc_id,
        org_id=ctx.org.id,
        filename=name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=digest,
        storage_path=rel,
        uploaded_by_id=ctx.user.id,
    )
    db.add(d)
    record(db, "document.uploaded", name, user=ctx.user, org_id=ctx.org.id, detail={"sha256": digest, "bytes": len(data)}, request=request)
    db.commit()
    db.refresh(d)
    background.add_task(_index_in_background, d.id)
    return _out(d)


class SearchHit(BaseModel):
    document_id: uuid.UUID
    filename: str
    page: int | None
    excerpt: str
    score: float


@router.get("/search", response_model=list[SearchHit])
def search_documents(q: str = Query(min_length=2, max_length=500), ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return [SearchHit(document_id=h.document_id, filename=h.filename, page=h.page, excerpt=h.content[:600], score=round(h.score, 4)) for h in rag.search(db, ctx.org.id, q, limit=10)]


@router.get("/{doc_id}", response_model=DocOut)
def get_document(doc_id: uuid.UUID, ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    return _out(_get(db, ctx, doc_id))


@router.get("/{doc_id}/download")
def download_document(doc_id: uuid.UUID, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    p = _path(d)
    if not p.exists():
        raise HTTPException(status.HTTP_410_GONE, "The stored file is missing. Restore it from backup or upload it again.")
    return FileResponse(p, filename=d.filename, media_type=d.content_type)


@router.post("/{doc_id}/reindex", response_model=DocOut)
def reindex_document(doc_id: uuid.UUID, request: Request, background: BackgroundTasks, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    d.status = DocStatus.processing
    record(db, "document.reindexed", d.filename, user=ctx.user, org_id=ctx.org.id, request=request)
    db.commit()
    background.add_task(_index_in_background, d.id)
    return _out(d)


@router.delete("/{doc_id}", response_model=Ok)
def delete_document(doc_id: uuid.UUID, request: Request, ctx: OrgContext = Depends(require_role(Role.technician)), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    if not ctx.at_least(Role.admin) and d.uploaded_by_id != ctx.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin or the person who uploaded it can delete this document.")
    p = _path(d)
    record(db, "document.deleted", d.filename, user=ctx.user, org_id=ctx.org.id, detail={"sha256": d.sha256}, request=request)
    db.delete(d)
    db.commit()
    p.unlink(missing_ok=True)
    return Ok()


@router.get("/stats/summary")
def doc_stats(ctx: OrgContext = Depends(get_org_ctx), db: Session = Depends(get_db)):
    rows = db.execute(select(Document.status, func.count(Document.id)).where(Document.org_id == ctx.org.id).group_by(Document.status)).all()
    return {s.value: n for s, n in rows}
