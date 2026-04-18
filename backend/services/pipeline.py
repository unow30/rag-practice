import logging
from typing import List, Optional

from langchain.schema import Document
from sqlalchemy.orm import Session

from backend.services.query_expander import expand_query
from backend.services.reranker import rerank
from backend.services.retriever import retrieve

logger = logging.getLogger(__name__)


def prepare_context(
    question: str,
    db: Session,
    document_ids: Optional[List[str]] = None,
) -> List[Document]:
    """Retrieve → (Multi-query) → Rerank 단계를 거쳐 최종 컨텍스트 문서를 반환한다."""
    queries = expand_query(question)
    logger.debug("query expansion: %d variant(s)", len(queries))

    seen_ids: set = set()
    candidate_docs: List[Document] = []

    for q in queries:
        results = retrieve(question=q, db=db, document_ids=document_ids)
        for doc in results:
            chunk_id = doc.metadata.get("chunk_id") or doc.page_content[:50]
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                candidate_docs.append(doc)

    logger.debug("candidates after retrieval: %d", len(candidate_docs))

    final_docs = rerank(question=question, candidate_docs=candidate_docs)
    logger.debug(
        "rerank scores: %s",
        [round(d.metadata.get("rerank_score", 0), 3) for d in final_docs],
    )

    return final_docs
