from datetime import datetime

from fastapi import APIRouter, Depends, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.crud import get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, page_params, paginate
from app.core.schemas import Message, ORMModel, Page, UserBrief
from app.database.session import get_db
from app.documents.models import Document
from app.services import storage
from app.users.models import User

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class DocumentOut(ORMModel):
    id: str
    name: str
    mime_type: str | None = None
    size_bytes: int
    entity_type: str | None = None
    entity_id: str | None = None
    created_at: datetime
    uploaded_by: UserBrief | None = None


@router.get("", response_model=Page[DocumentOut], dependencies=[Depends(require_perm("documents:read"))])
def list_documents(
    entity_type: str | None = None,
    entity_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Document).order_by(Document.created_at.desc())
    if entity_type:
        stmt = stmt.where(Document.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Document.entity_id == entity_id)
    if params.search:
        stmt = stmt.where(Document.name.ilike(f"%{params.search}%"))
    return paginate(db, stmt, params)


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    entity_type: str | None = None,
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("documents:write")),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("File exceeds the 25 MB upload limit", 413)
    key = storage.save_file(data, file.filename or "file", file.content_type)
    doc = Document(
        name=file.filename or "file",
        file_key=key,
        mime_type=file.content_type,
        size_bytes=len(data),
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by_id=user.id,
    )
    db.add(doc)
    db.flush()
    audit(db, user.id, "upload", "document", doc.id, {"name": doc.name})
    db.commit()
    return doc


@router.get("/{document_id}/download", dependencies=[Depends(require_perm("documents:read"))])
def download_document(document_id: str, db: Session = Depends(get_db)):
    doc = get_or_404(db, Document, document_id, "Document")
    data = storage.read_file(doc.file_key)
    return Response(
        content=data,
        media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.name}"'},
    )


@router.delete("/{document_id}", response_model=Message)
def delete_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("documents:delete"))):
    doc = get_or_404(db, Document, document_id, "Document")
    storage.delete_file(doc.file_key)
    name = doc.name
    db.delete(doc)
    audit(db, user.id, "delete", "document", document_id, {"name": name})
    db.commit()
    return {"detail": "Document deleted"}
