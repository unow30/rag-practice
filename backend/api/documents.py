import hashlib
import os
import shutil
import threading
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.document import Document, DocumentStatus
from backend.services.bm25_indexer import delete_bm25_index

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_DOCUMENT_COUNT = 20
_processing_semaphore = threading.Semaphore(1)  # 동시 처리 1개로 제한 (모델 동시 로드 방지)
ALLOWED_MIME_TYPES = {"application/pdf"}
DATA_DIR = os.getenv("DATA_DIR", "./data")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")


def _compute_sha256(file_path: str) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _validate_pdf(file: UploadFile, size: int):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILE_TYPE", "message": "PDF 파일만 업로드 가능합니다."},
        )
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_FILE_TYPE", "message": "PDF 파일만 업로드 가능합니다."},
        )
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"파일 크기가 50MB를 초과합니다: {file.filename}",
            },
        )


@router.post("", status_code=202)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail={"error": "NO_FILES", "message": "파일을 선택해 주세요."})
    if len(files) > 5:
        raise HTTPException(
            status_code=400,
            detail={"error": "TOO_MANY_FILES", "message": "한 번에 최대 5개 파일을 업로드할 수 있습니다."},
        )

    current_count = db.query(Document).count()
    if current_count + len(files) > MAX_DOCUMENT_COUNT:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "DOCUMENT_LIMIT_EXCEEDED",
                "message": f"최대 문서 수({MAX_DOCUMENT_COUNT}개)에 도달했습니다. 기존 문서를 삭제 후 업로드해 주세요.",
            },
        )

    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    created_docs = []
    duplicate_docs = []

    for file in files:
        content = await file.read()
        size = len(content)

        _validate_pdf(file, size)

        file_hash = hashlib.sha256(content).hexdigest()
        existing = db.query(Document).filter(Document.file_hash == file_hash).first()
        if existing:
            duplicate_docs.append({
                "id": existing.id,
                "name": file.filename,
                "message": f"이미 업로드된 문서입니다: {file.filename}",
            })
            continue

        import uuid
        doc_id = str(uuid.uuid4())
        safe_name = os.path.basename(file.filename)
        dest_path = os.path.join(DOCUMENTS_DIR, f"{doc_id}_{safe_name}")

        with open(dest_path, "wb") as f:
            f.write(content)

        doc = Document(
            id=doc_id,
            name=safe_name,
            file_path=dest_path,
            file_hash=file_hash,
            size_bytes=size,
            status=DocumentStatus.PENDING,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        background_tasks.add_task(_process_document_background, doc_id)
        created_docs.append(doc.to_dict())

    return {"documents": created_docs, "duplicates": duplicate_docs}


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return {
        "documents": [d.to_dict() for d in docs],
        "total": len(docs),
        "limit": MAX_DOCUMENT_COUNT,
    }


@router.get("/{doc_id}/status")
def get_document_status(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."},
        )
    return {
        "id": doc.id,
        "status": doc.status.value,
        "progress_message": _status_message(doc.status),
        "error_message": doc.error_message,
    }


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."},
        )

    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    if doc.index_path and os.path.exists(doc.index_path):
        shutil.rmtree(doc.index_path, ignore_errors=True)

    delete_bm25_index(doc.id)

    db.delete(doc)
    db.commit()


def _status_message(status: DocumentStatus) -> str:
    messages = {
        DocumentStatus.PENDING: "처리 대기 중...",
        DocumentStatus.EXTRACTING: "텍스트 추출 중...",
        DocumentStatus.CHUNKING: "문서 분할 중...",
        DocumentStatus.EMBEDDING: "임베딩 및 인덱싱 중...",
        DocumentStatus.READY: "질의 가능 상태입니다.",
        DocumentStatus.FAILED: "처리에 실패했습니다.",
    }
    return messages.get(status, "알 수 없는 상태")


def _process_document_background(doc_id: str):
    """추출 → 청킹 → 임베딩 → FAISS 인덱싱 전체 파이프라인 (백그라운드 실행)"""
    from backend.models.database import SessionLocal
    from backend.services.indexer import process_document
    db = SessionLocal()
    try:
        with _processing_semaphore:
            process_document(doc_id, db)
    finally:
        db.close()
