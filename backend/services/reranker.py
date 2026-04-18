import os
from typing import List

from langchain.schema import Document

RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from FlagEmbedding import FlagReranker
        _reranker = FlagReranker(RERANK_MODEL, use_fp16=True)
    return _reranker


def rerank(
    question: str,
    candidate_docs: List[Document],
    top_n: int = RERANK_TOP_N,
) -> List[Document]:
    """Cross-encoder로 후보 문서를 재정렬하고 상위 top_n개를 반환한다."""
    if not candidate_docs:
        return []

    reranker = _get_reranker()
    pairs = [[question, doc.page_content] for doc in candidate_docs]
    scores = reranker.compute_score(pairs, normalize=True)

    if not isinstance(scores, list):
        scores = [scores]

    scored = sorted(
        zip(scores, candidate_docs),
        key=lambda x: x[0],
        reverse=True,
    )

    result = []
    for score, doc in scored[:top_n]:
        doc.metadata["rerank_score"] = float(score)
        result.append(doc)

    return result
