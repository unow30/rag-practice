import json
import os
import pickle
import shutil
from datetime import datetime, timezone
from typing import List

import numpy as np
from langchain.schema import Document
from sqlalchemy.orm import Session

from backend.models.document import Chunk, ContentType, Document as DocModel, DocumentStatus
from backend.services.bm25_indexer import build_bm25_index, delete_bm25_index
from backend.services.chunker import split_documents
from backend.services.embedder import get_model as get_embedding_model
from backend.services.extractor import get_extractor

DATA_DIR = os.getenv("DATA_DIR", "./data")
INDEXES_DIR = os.path.join(DATA_DIR, "indexes")

_progress: dict[str, int] = {}


def get_progress(doc_id: str) -> int:
    return _progress.get(doc_id, 0)


def _content_type_enum(ct_str: str) -> ContentType:
    try:
        return ContentType(ct_str)
    except ValueError:
        return ContentType.TEXT


def process_document(doc_id: str, db: Session) -> None:
    """PDF 추출 → 청킹 → 임베딩 → FAISS 인덱싱 전체 파이프라인"""
    import faiss

    doc_record = db.query(DocModel).filter(DocModel.id == doc_id).first()
    if not doc_record:
        return

    try:
        _progress[doc_id] = 0

        # 1. 추출
        doc_record.status = DocumentStatus.EXTRACTING
        db.commit()
        _progress[doc_id] = 5

        extractor = get_extractor()
        raw_docs = extractor.extract(doc_record.file_path, doc_id)
        _progress[doc_id] = 20

        # 2. 청킹
        doc_record.status = DocumentStatus.CHUNKING
        db.commit()
        _progress[doc_id] = 25

        chunks: List[Document] = split_documents(raw_docs)
        doc_record.page_count = max(
            (c.metadata.get("page", 0) for c in chunks), default=0
        )
        doc_record.chunk_count = len(chunks)
        db.commit()
        _progress[doc_id] = 35

        # 3. 임베딩
        doc_record.status = DocumentStatus.EMBEDDING
        db.commit()

        texts = [c.page_content for c in chunks]
        total = len(texts)
        all_vectors: list = []
        batch_size = 32
        emb_model = get_embedding_model()
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            output = emb_model.encode(batch, batch_size=batch_size, max_length=512)
            all_vectors.extend(output["dense_vecs"].tolist())
            done = min(i + batch_size, total)
            _progress[doc_id] = 35 + int(done / total * 50)

        vectors = all_vectors
        dim = len(vectors[0])
        np_vectors = np.array(vectors, dtype="float32")

        # 4. FAISS 인덱스 생성 및 저장
        index_dir = os.path.join(INDEXES_DIR, doc_id)
        os.makedirs(index_dir, exist_ok=True)

        faiss_index = faiss.IndexFlatIP(dim)
        faiss_index.add(np_vectors)

        faiss.write_index(faiss_index, os.path.join(index_dir, "index.faiss"))
        _progress[doc_id] = 88

        # chunk_id 매핑 저장
        chunk_records = []
        id_map = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            meta = chunk.metadata
            raw_annot = meta.get("annotations")
            annotation_types_json = json.dumps(raw_annot, ensure_ascii=False) if raw_annot else None
            cr = Chunk(
                document_id=doc_id,
                chunk_index=meta.get("chunk_index", i),
                content=chunk.page_content,
                content_type=_content_type_enum(meta.get("content_type", "TEXT")),
                page_number=meta.get("page", 1),
                section_title=meta.get("section"),
                version=meta.get("version"),
                token_count=len(chunk.page_content.split()),
                faiss_index_id=i,
                annotation_types=annotation_types_json,
                memo_content=meta.get("memo_content"),
            )
            db.add(cr)
            db.flush()
            id_map.append(cr.id)
            chunk_records.append(cr)

        with open(os.path.join(index_dir, "index.pkl"), "wb") as f:
            pickle.dump(id_map, f)

        # BM25 인덱스 생성
        build_bm25_index(doc_id, texts)
        _progress[doc_id] = 95

        doc_record.index_path = index_dir
        doc_record.status = DocumentStatus.READY
        doc_record.processed_at = datetime.now(timezone.utc)
        db.commit()
        _progress[doc_id] = 100

    except Exception as e:
        db.rollback()
        doc_record = db.query(DocModel).filter(DocModel.id == doc_id).first()
        if doc_record:
            doc_record.status = DocumentStatus.FAILED
            doc_record.error_message = str(e)
            db.commit()
        _progress.pop(doc_id, None)


def reprocess_document(doc_id: str, db: Session) -> None:
    """기존 청크·인덱스를 삭제하고 처리 파이프라인을 재실행한다."""
    doc_record = db.query(DocModel).filter(DocModel.id == doc_id).first()
    if not doc_record:
        return

    _progress[doc_id] = 0
    db.query(Chunk).filter(Chunk.document_id == doc_id).delete()
    db.commit()

    if doc_record.index_path and os.path.exists(doc_record.index_path):
        shutil.rmtree(doc_record.index_path, ignore_errors=True)

    delete_bm25_index(doc_id)

    doc_record.index_path = None
    db.commit()

    process_document(doc_id, db)
