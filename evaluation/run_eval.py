"""
평가 스크립트: v0 베이스라인 지표 측정
사용법:
  python -m evaluation.run_eval --doc-ids <doc_id1> [doc_id2 ...] [--output-name final]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DB_PATH", str(ROOT / "data" / "rag.db"))
os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy.orm import Session
from backend.models.database import SessionLocal
from backend.services.retriever import retrieve
from backend.services.pipeline import prepare_context
from backend.services.generator import generate_stream, format_docs, build_sources  # noqa: F401


# ── 설정 ──────────────────────────────────────────────────────────────────────
EVAL_SET_PATH = ROOT / "evaluation" / "eval_set.json"
RESULTS_DIR = ROOT / "evaluation" / "results"
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
USE_PIPELINE = os.getenv("USE_PIPELINE", "false").lower() == "true"


# ── 지표 계산 함수 ─────────────────────────────────────────────────────────────

def recall_at_k(retrieved_docs: list, source_page: int | None, k: int = 5) -> float:
    """정답 청크가 top-k 안에 있는가 (0.0 또는 1.0)."""
    if source_page is None:
        # negative case: 문서에 없는 질문 → 회수된 문서가 적을수록 좋음 (여기선 skip)
        return None
    for doc in retrieved_docs[:k]:
        page = doc.metadata.get("page")
        if page is not None and int(page) == int(source_page):
            return 1.0
    return 0.0


def answerable_at_k(retrieved_docs: list, keywords: list[str], k: int = 5) -> float:
    """top-k 컨텍스트만으로 키워드 기반 답변 가능 여부."""
    context = " ".join(d.page_content for d in retrieved_docs[:k]).lower()
    matched = sum(1 for kw in keywords if kw.lower() in context)
    return matched / len(keywords) if keywords else 0.0


def exact_match(answer: str, expected: str) -> float:
    """expected_answer가 실제 답변에 완전 포함되는가."""
    if not expected or expected == "문서에서 관련 정보를 찾을 수 없습니다":
        return None
    return 1.0 if expected.lower() in answer.lower() else 0.0


def partial_match(answer: str, keywords: list[str]) -> float:
    """키워드 중 몇 개가 답변에 포함되는가."""
    if not keywords:
        return 0.0
    answer_lower = answer.lower()
    matched = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return matched / len(keywords)


# ── 단일 질문 평가 ─────────────────────────────────────────────────────────────

async def evaluate_one(
    item: dict,
    document_ids: list[str],
    db: Session,
) -> dict:
    """질문 1개에 대해 전체 파이프라인을 실행하고 지표를 반환한다."""
    question = item["question"]
    expected = item.get("expected_answer", "")
    keywords = item.get("keywords", [])
    source_page = item.get("source_page")
    negative = item.get("negative_case", False)

    # ── 검색 (pipeline 또는 retriever 직접 호출) ──────────────────────────────
    t0 = time.monotonic()
    try:
        if USE_PIPELINE:
            retrieved_docs = prepare_context(
                question=question,
                db=db,
                document_ids=document_ids or None,
            )
        else:
            retrieved_docs = retrieve(
                question=question,
                db=db,
                document_ids=document_ids or None,
                top_k=RETRIEVAL_TOP_K,
            )
    except Exception as e:
        return {
            "id": item["id"],
            "question": question,
            "error": f"retrieve 실패: {e}",
            "recall_at_k": None,
            "answerable_at_k": None,
            "exact_match": None,
            "partial_match": None,
            "latency_ms": None,
        }

    # ── 생성 ──────────────────────────────────────────────────────────────────
    context_str = format_docs(retrieved_docs)
    full_answer_parts: list[str] = []
    first_token_ms: float | None = None

    try:
        async for token in generate_stream(question=question, context_docs=retrieved_docs):
            if first_token_ms is None:
                first_token_ms = (time.monotonic() - t0) * 1000
            full_answer_parts.append(token)
    except Exception as e:
        return {
            "id": item["id"],
            "question": question,
            "error": f"generate 실패: {e}",
            "recall_at_k": None,
            "answerable_at_k": None,
            "exact_match": None,
            "partial_match": None,
            "latency_ms": None,
        }

    answer = "".join(full_answer_parts)
    total_ms = (time.monotonic() - t0) * 1000

    # ── 지표 ──────────────────────────────────────────────────────────────────
    r_at_k = recall_at_k(retrieved_docs, source_page, k=RETRIEVAL_TOP_K)
    a_at_k = answerable_at_k(retrieved_docs, keywords, k=RETRIEVAL_TOP_K)
    em = exact_match(answer, expected)
    pm = partial_match(answer, keywords)

    result = {
        "id": item["id"],
        "question": question,
        "category": item.get("category"),
        "difficulty": item.get("difficulty"),
        "negative_case": negative,
        "answer": answer[:300],  # 저장 공간 절약
        "expected_answer": expected,
        "recall_at_k": r_at_k,
        "answerable_at_k": a_at_k,
        "exact_match": em,
        "partial_match": pm,
        "latency_first_token_ms": first_token_ms,
        "latency_total_ms": total_ms,
        "retrieved_count": len(retrieved_docs),
    }
    return result


# ── 전체 평가 실행 ─────────────────────────────────────────────────────────────

async def run_evaluation(document_ids: list[str], output_name: str | None = None) -> dict:
    """eval_set.json 전체를 순회하며 지표를 집계한다."""
    eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    print(f"\n📋 평가 시작: {len(eval_set)}개 질문, 문서 ID: {document_ids or '전체'}\n")

    db = SessionLocal()
    results = []
    try:
        for i, item in enumerate(eval_set, 1):
            print(f"  [{i:02d}/{len(eval_set)}] Q{item['id']}: {item['question'][:50]}...")
            res = await evaluate_one(item, document_ids, db)
            results.append(res)
            if "error" in res:
                print(f"         ❌ {res['error']}")
            else:
                r = f"{res['recall_at_k']:.2f}" if res["recall_at_k"] is not None else "N/A"
                a = f"{res['answerable_at_k']:.2f}" if res["answerable_at_k"] is not None else "N/A"
                print(f"         Recall@k={r}  Answerable@k={a}  "
                      f"Latency={res['latency_first_token_ms']:.0f}ms" if res.get("latency_first_token_ms") else "")
    finally:
        db.close()

    # ── 집계 ──────────────────────────────────────────────────────────────────
    valid = [r for r in results if "error" not in r]
    positive = [r for r in valid if not r.get("negative_case")]

    def avg(values):
        vals = [v for v in values if v is not None]
        return sum(vals) / len(vals) if vals else None

    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_questions": len(eval_set),
        "evaluated": len(valid),
        "errors": len(results) - len(valid),
        "document_ids": document_ids,
        "metrics": {
            "recall_at_k": avg([r["recall_at_k"] for r in positive]),
            "answerable_at_k": avg([r["answerable_at_k"] for r in valid]),
            "exact_match": avg([r["exact_match"] for r in positive]),
            "partial_match": avg([r["partial_match"] for r in valid]),
            "latency_first_token_ms_avg": avg([r["latency_first_token_ms"] for r in valid]),
            "latency_total_ms_avg": avg([r["latency_total_ms"] for r in valid]),
        },
        "by_category": {},
        "results": results,
    }

    # 카테고리별 집계
    categories = {r["category"] for r in valid if r.get("category")}
    for cat in sorted(categories):
        cat_results = [r for r in valid if r.get("category") == cat and not r.get("negative_case")]
        summary["by_category"][cat] = {
            "count": len(cat_results),
            "recall_at_k": avg([r["recall_at_k"] for r in cat_results]),
            "partial_match": avg([r["partial_match"] for r in cat_results]),
        }

    # ── 출력 ──────────────────────────────────────────────────────────────────
    m = summary["metrics"]
    print("\n" + "=" * 60)
    print("📊 평가 결과 요약")
    print("=" * 60)
    print(f"  총 질문수    : {summary['total_questions']}개")
    print(f"  평가 완료    : {summary['evaluated']}개  (오류: {summary['errors']}개)")
    print(f"  Recall@{RETRIEVAL_TOP_K}     : {m['recall_at_k']:.2%}" if m["recall_at_k"] is not None else "  Recall@k     : N/A")
    print(f"  Answerable@{RETRIEVAL_TOP_K} : {m['answerable_at_k']:.2%}" if m["answerable_at_k"] is not None else "  Answerable@k : N/A")
    print(f"  Exact Match  : {m['exact_match']:.2%}" if m["exact_match"] is not None else "  Exact Match  : N/A")
    print(f"  Partial Match: {m['partial_match']:.2%}" if m["partial_match"] is not None else "  Partial Match: N/A")
    print(f"  Latency (첫 토큰): {m['latency_first_token_ms_avg']:.0f}ms" if m["latency_first_token_ms_avg"] is not None else "  Latency      : N/A")
    print()

    # 목표 달성 여부
    goals = [
        ("Recall@5 ≥ 80%",       m["recall_at_k"],              0.80),
        ("Answerable@5 ≥ 80%",    m["answerable_at_k"],           0.80),
        ("Exact Match ≥ 60%",     m["exact_match"],               0.60),
        ("Partial Match ≥ 85%",   m["partial_match"],             0.85),
        ("Latency ≤ 3000ms",      (3000 - (m["latency_first_token_ms_avg"] or 9999)) / 3000 + 1, 1.0),
    ]
    print("🎯 목표 달성 여부")
    for label, value, threshold in goals:
        if value is None:
            print(f"  ⬜ {label}: 측정 불가")
        elif value >= threshold:
            print(f"  ✅ {label}: {value:.2%}")
        else:
            print(f"  ❌ {label}: {value:.2%} (목표 미달)")
    print("=" * 60)

    # ── 파일 저장 ──────────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_name:
        out_path = RESULTS_DIR / f"{output_name}.json"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"{ts}.json"

    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 결과 저장: {out_path}\n")

    return summary


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG 파이프라인 평가 스크립트")
    parser.add_argument(
        "--doc-ids",
        nargs="*",
        default=[],
        help="평가에 사용할 문서 ID 목록 (미입력 시 전체 READY 문서)",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="결과 파일명 (예: final → evaluation/results/final.json)",
    )
    args = parser.parse_args()
    asyncio.run(run_evaluation(document_ids=args.doc_ids, output_name=args.output_name))


if __name__ == "__main__":
    main()
