import os
import pickle
from typing import List

DATA_DIR = os.getenv("DATA_DIR", "./data")
INDEXES_DIR = os.path.join(DATA_DIR, "indexes")


def _bm25_path(doc_id: str) -> str:
    return os.path.join(INDEXES_DIR, doc_id, "bm25.pkl")


def build_bm25_index(doc_id: str, texts: List[str]) -> None:
    """청크 텍스트 목록으로 BM25 인덱스를 생성하고 저장한다."""
    from rank_bm25 import BM25Okapi

    tokenized = [text.lower().split() for text in texts]
    bm25 = BM25Okapi(tokenized)

    path = _bm25_path(doc_id)
    with open(path, "wb") as f:
        pickle.dump({"bm25": bm25, "texts": texts}, f)


def load_bm25_index(doc_id: str):
    """저장된 BM25 인덱스를 로드한다. 없으면 None을 반환한다."""
    path = _bm25_path(doc_id)
    if not os.path.exists(path):
        return None, []
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data["bm25"], data["texts"]


def delete_bm25_index(doc_id: str) -> None:
    """BM25 인덱스 파일을 삭제한다."""
    path = _bm25_path(doc_id)
    if os.path.exists(path):
        os.remove(path)


def search_bm25(doc_id: str, query: str, top_k: int = 20) -> List[tuple]:
    """BM25 검색 결과를 (score, text_index) 목록으로 반환한다."""
    bm25, texts = load_bm25_index(doc_id)
    if bm25 is None:
        return []

    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    return [(score, idx) for idx, score in ranked[:top_k] if score > 0]
