import os
import pickle
from typing import List, Optional

import numpy as np
from langchain.schema import Document
from sqlalchemy.orm import Session

from backend.models.document import Chunk, Document as DocModel, DocumentStatus
from backend.services.embedder import embed_query

DATA_DIR = os.getenv("DATA_DIR", "./data")
INDEXES_DIR = os.path.join(DATA_DIR, "indexes")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "20"))


def _load_faiss_index(index_dir: str):
    import faiss
    index_path = os.path.join(index_dir, "index.faiss")
    if not os.path.exists(index_path):
        return None, []
    index = faiss.read_index(index_path)
    with open(os.path.join(index_dir, "index.pkl"), "rb") as f:
        id_map = pickle.load(f)
    return index, id_map


def retrieve(
    question: str,
    db: Session,
    document_ids: Optional[List[str]] = None,
    top_k: int = RETRIEVAL_TOP_K,
) -> List[Document]:
    """FAISS dense 검색으로 후보 청크를 반환한다."""
    import faiss

    # 검색 대상 문서 결정
    query = db.query(DocModel).filter(DocModel.status == DocumentStatus.READY)
    if document_ids:
        query = query.filter(DocModel.id.in_(document_ids))
    target_docs = query.all()

    if not target_docs:
        return []

    query_vec = np.array([embed_query(question)], dtype="float32")

    all_results: List[tuple] = []  # (score, chunk_id)

    for doc in target_docs:
        if not doc.index_path:
            continue
        faiss_index, id_map = _load_faiss_index(doc.index_path)
        if faiss_index is None or faiss_index.ntotal == 0:
            continue

        k = min(top_k, faiss_index.ntotal)
        scores, indices = faiss_index.search(query_vec, k)

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(id_map):
                continue
            all_results.append((float(score), id_map[idx]))

    # 전체 결과에서 상위 top_k 선택
    all_results.sort(key=lambda x: x[0], reverse=True)
    top_results = all_results[:top_k]

    if not top_results:
        return []

    chunk_ids = [r[1] for r in top_results]
    score_map = {r[1]: r[0] for r in top_results}

    chunks = (
        db.query(Chunk)
        .filter(Chunk.id.in_(chunk_ids))
        .all()
    )
    chunk_map = {c.id: c for c in chunks}

    langchain_docs: List[Document] = []
    for chunk_id in chunk_ids:
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue

        doc_record = db.query(DocModel).filter(DocModel.id == chunk.document_id).first()
        metadata = chunk.to_metadata()
        metadata["document_name"] = doc_record.name if doc_record else ""
        metadata["score"] = score_map.get(chunk_id, 0.0)

        langchain_docs.append(
            Document(page_content=chunk.content, metadata=metadata)
        )

    return langchain_docs
