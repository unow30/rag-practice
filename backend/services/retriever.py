import json
import os
import pickle
from typing import List, Optional

import numpy as np
from langchain.schema import Document
from sqlalchemy.orm import Session

from backend.models.document import Chunk, Document as DocModel, DocumentStatus
from backend.services.bm25_indexer import load_bm25_index
from backend.services.embedder import embed_query

DATA_DIR = os.getenv("DATA_DIR", "./data")
INDEXES_DIR = os.path.join(DATA_DIR, "indexes")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "20"))
RETRIEVER_MODE = os.getenv("RETRIEVER", "faiss")  # "faiss" | "ensemble"
RRF_K = 60


def _load_faiss_index(index_dir: str):
    import faiss
    index_path = os.path.join(index_dir, "index.faiss")
    if not os.path.exists(index_path):
        return None, []
    index = faiss.read_index(index_path)
    with open(os.path.join(index_dir, "index.pkl"), "rb") as f:
        id_map = pickle.load(f)
    return index, id_map


def _rrf_score(rank: int) -> float:
    return 1.0 / (RRF_K + rank + 1)


def _faiss_search(
    doc: DocModel,
    query_vec: np.ndarray,
    top_k: int,
) -> List[tuple]:
    """FAISS dense 검색 → (score, chunk_id) 목록"""
    import faiss as faiss_lib

    if not doc.index_path:
        return []
    faiss_index, id_map = _load_faiss_index(doc.index_path)
    if faiss_index is None or faiss_index.ntotal == 0:
        return []

    k = min(top_k, faiss_index.ntotal)
    scores, indices = faiss_index.search(query_vec, k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(id_map):
            continue
        results.append((float(score), id_map[idx]))
    return results


def _bm25_search(
    doc: DocModel,
    question: str,
    top_k: int,
    db: Session,
) -> List[tuple]:
    """BM25 sparse 검색 → (score, chunk_id) 목록"""
    bm25, _ = load_bm25_index(doc.id)
    if bm25 is None:
        return []

    tokenized = question.lower().split()
    scores = bm25.get_scores(tokenized)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    # faiss_index_id → chunk UUID 매핑
    results = []
    for idx, score in ranked:
        if score <= 0:
            continue
        chunk = (
            db.query(Chunk)
            .filter(Chunk.document_id == doc.id, Chunk.faiss_index_id == idx)
            .first()
        )
        if chunk:
            results.append((float(score), chunk.id))
    return results


def _rrf_merge(
    faiss_results: List[tuple],
    bm25_results: List[tuple],
    top_k: int,
) -> List[tuple]:
    """RRF(k=60)로 두 순위 목록을 결합한다."""
    rrf_scores: dict = {}

    for rank, (_, chunk_id) in enumerate(faiss_results):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + _rrf_score(rank)

    for rank, (_, chunk_id) in enumerate(bm25_results):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + _rrf_score(rank)

    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_ids[:top_k]


def retrieve(
    question: str,
    db: Session,
    document_ids: Optional[List[str]] = None,
    top_k: int = RETRIEVAL_TOP_K,
) -> List[Document]:
    """RETRIEVER 환경변수에 따라 FAISS 단독 또는 FAISS+BM25 앙상블 검색을 수행한다."""
    import faiss  # noqa: F401 — 필요 시 내부에서 사용

    query = db.query(DocModel).filter(DocModel.status == DocumentStatus.READY)
    if document_ids:
        query = query.filter(DocModel.id.in_(document_ids))
    target_docs = query.all()

    if not target_docs:
        return []

    query_vec = np.array([embed_query(question)], dtype="float32")

    if RETRIEVER_MODE == "ensemble":
        return _ensemble_retrieve(question, query_vec, target_docs, db, top_k)
    return _faiss_retrieve(query_vec, target_docs, db, top_k)


def _faiss_retrieve(
    query_vec: np.ndarray,
    target_docs: list,
    db: Session,
    top_k: int,
) -> List[Document]:
    all_results: List[tuple] = []
    for doc in target_docs:
        all_results.extend(_faiss_search(doc, query_vec, top_k))

    all_results.sort(key=lambda x: x[0], reverse=True)
    return _build_langchain_docs(all_results[:top_k], db)


def _ensemble_retrieve(
    question: str,
    query_vec: np.ndarray,
    target_docs: list,
    db: Session,
    top_k: int,
) -> List[Document]:
    faiss_all: List[tuple] = []
    bm25_all: List[tuple] = []

    for doc in target_docs:
        faiss_all.extend(_faiss_search(doc, query_vec, top_k))
        bm25_all.extend(_bm25_search(doc, question, top_k, db))

    faiss_all.sort(key=lambda x: x[0], reverse=True)
    bm25_all.sort(key=lambda x: x[0], reverse=True)

    merged = _rrf_merge(faiss_all, bm25_all, top_k)
    # _rrf_merge returns (chunk_id, score); convert to (score, chunk_id) for _build_langchain_docs
    merged_normalized = [(score, chunk_id) for chunk_id, score in merged]
    return _build_langchain_docs(merged_normalized, db)


def _build_langchain_docs(
    results: List[tuple],
    db: Session,
) -> List[Document]:
    chunk_ids = [r[1] for r in results]
    score_map = {r[1]: r[0] for r in results}

    chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
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
        try:
            annotations = json.loads(chunk.annotation_types) if chunk.annotation_types else {}
        except (json.JSONDecodeError, TypeError):
            annotations = {}
        metadata["annotations"] = annotations
        metadata["annotation_types"] = list(annotations.keys())
        metadata["memo_content"] = chunk.memo_content

        langchain_docs.append(Document(page_content=chunk.content, metadata=metadata))

    return langchain_docs
