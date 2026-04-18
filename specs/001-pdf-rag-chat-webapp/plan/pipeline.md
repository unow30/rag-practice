# Pipeline Architecture: PDF RAG 대화형 웹 앱

**Created**: 2026-04-18  
**Design Principle**: 디버깅 용이성 > 코드 우아함

---

## 전체 파이프라인 개요

```
PDF 업로드
    │
    ▼
[Extractor]          pyMuPDF4LLM → Markdown 텍스트 + 표 구조 보존
    │
    ▼
[Chunker]            RecursiveCharacterTextSplitter (size=800, overlap=120)
    │                + 메타데이터 부착 (source, page, doc_id, section, version)
    ▼
[Embedder]           BGE-M3 → Dense 벡터
    │
    ├──▶ FAISS Index (dense 벡터 저장)
    └──▶ BM25 Index  (sparse 역인덱스 저장)
    
────────────────────────────────────────

질문 입력
    │
    ▼
[Retriever]          FAISS + BM25 Hybrid → RRF 결합 → top-20 후보
    │
    ▼
[Reranker]           bge-reranker-v2-m3 Cross-encoder → top-5 선별
    │
    ▼
[Generator]          LLM (Claude/GPT) + 시스템 프롬프트 → 스트리밍 답변
    │
    ▼
[Response]           answer + sources (문서명, 페이지, 인용문, 점수)
```

---

## 핵심 오케스트레이션 함수

```python
# backend/services/pipeline.py

def ask(
    question: str,
    retriever,      # EnsembleRetriever (FAISS + BM25 + RRF)
    reranker,       # CrossEncoderReranker
    answer_chain,   # LLM chain with system prompt
    logger=None,
) -> dict:
    # 1단계: 후보 검색 (recall 우선)
    candidate_docs = retriever.invoke(question)
    if logger:
        logger.debug(f"[Retriever] {len(candidate_docs)}개 후보 검색됨")
        for i, doc in enumerate(candidate_docs[:3]):
            logger.debug(f"  [{i}] page={doc.metadata['page']} score={doc.metadata.get('score')}")

    # 2단계: 재정렬 (precision 향상)
    final_docs = reranker.rerank(question, candidate_docs)
    if logger:
        logger.debug(f"[Reranker] {len(final_docs)}개로 압축")
        for i, doc in enumerate(final_docs):
            logger.debug(f"  [{i}] page={doc.metadata['page']} rerank_score={doc.metadata.get('rerank_score'):.3f}")

    # 3단계: 답변 생성
    context = format_docs(final_docs)
    answer  = answer_chain.invoke({"question": question, "context": context})

    return {
        "answer":    answer,
        "documents": final_docs,
        "debug": {
            "candidate_count": len(candidate_docs),
            "final_count":     len(final_docs),
        }
    }
```

---

## 단계별 구현 마일스톤

### v0: 동작하는 베이스라인

**목표**: 일단 돌아가는 파이프라인 확인

```
Extractor:  PyMuPDFLoader (LangChain 기본)
Chunker:    RecursiveCharacterTextSplitter
Retriever:  FAISS Dense only (top-5 직접 사용)
Reranker:   없음
Generator:  Claude API
```

**완료 기준**: PDF 1개 업로드 후 텍스트 질문에 출처 있는 답변 반환

---

### v0.5: 평가 셋 구축 및 기준선 측정

**목표**: 개선 방향 수치로 파악

```
평가 셋:    10~20개 질문-정답 쌍 (텍스트/표/그래프 카테고리 포함)
지표:       Recall@5, Answerable@5, Exact/Partial Match, Latency
```

**평가 셋 JSON 구조**:
```json
[
  {
    "id": 1,
    "question": "3분기 영업이익은?",
    "expected_answer": "1,200억 원",
    "keywords": ["영업이익", "3분기", "1200"],
    "category": "TABLE",
    "source_page": 15,
    "difficulty": "MEDIUM"
  }
]
```

---

### v1: 하이브리드 검색 (BM25 + RRF)

**목표**: Recall@5 기준선 대비 +10% 이상

```
Retriever:  EnsembleRetriever(
              retrievers=[faiss_retriever, bm25_retriever],
              weights=[0.5, 0.5]
            )
            → RRF(k=60)로 결합 → top-20
```

**적용 판단 기준**: v0.5 Recall@5 < 80%이면 즉시 적용

---

### v2: Multi-query 확장 (조건부)

**목표**: 표현 불일치로 인한 검색 실패 감소

```
QueryExpander: LLM으로 원 질문 2~3개 paraphrase 생성
               → 각각 검색 → 중복 제거 → 합산 후 RRF
```

**적용 판단 기준**: 평가 셋에서 "표현만 다른" 질문의 Recall이 낮을 때

---

### v3: Cross-encoder Reranker

**목표**: Precision 향상, 더 관련성 높은 top-5 선별

```
Retriever:  top-20 후보 검색 (v1 기준)
Reranker:   BAAI/bge-reranker-v2-m3
            → top-5로 압축
Generator:  top-5 컨텍스트로 답변 생성
```

**적용 판단 기준**: Recall@5는 충분하나 답변 품질(Exact Match)이 낮을 때

---

## 디버깅 가이드

### 답변이 틀렸을 때 점검 순서

```
1. candidate_docs 확인
   → 정답 청크가 top-20 안에 있는가?
   → NO: Retriever 문제 (BM25 추가, Multi-query 검토)
   → YES: 2번으로

2. final_docs 확인
   → 정답 청크가 Reranker 후 top-5 안에 있는가?
   → NO: Reranker 문제 (reranker 모델 교체, top-N 증가)
   → YES: 3번으로

3. context 확인
   → format_docs() 결과에서 정답 내용이 보이는가?
   → NO: 청크 경계 문제 (chunk_size 조정, overlap 증가)
   → YES: 4번으로

4. 원본 청크 직접 확인
   → doc.metadata['page'], doc.metadata['section'] 확인
   → 추출이 잘못됐는가? → Extractor 문제 (pyMuPDF4LLM 파라미터 조정)
   → 내용은 있는데 LLM이 무시했는가? → 프롬프트 개선
```

### 유용한 디버깅 출력

```python
# 중간 단계 출력 (개발 환경)
print("=== CANDIDATES ===")
for doc in candidate_docs:
    print(f"[p.{doc.metadata['page']}] {doc.page_content[:100]}...")

print("=== RERANKED ===")
for doc in final_docs:
    print(f"[p.{doc.metadata['page']}] score={doc.metadata['rerank_score']:.3f}")
    print(doc.page_content[:200])
```

---

## 시스템 프롬프트 설계

```
당신은 업로드된 문서를 기반으로 질문에 답하는 어시스턴트입니다.

규칙:
1. 반드시 제공된 문서 컨텍스트에 근거하여 답변하세요.
2. 컨텍스트에 없는 내용은 추측하거나 생성하지 마세요.
3. 답변할 수 없는 경우 "문서에서 관련 정보를 찾을 수 없습니다"라고 말하세요.
4. 가능하면 구체적인 수치, 날짜, 고유명사를 원문 그대로 인용하세요.

[컨텍스트]
{context}

[질문]
{question}
```

---

## 추출기 교체 인터페이스

추출기는 하나의 인터페이스로 추상화하여 v0 → v1(pyMuPDF4LLM) → vN(VLM) 전환이 쉽도록 설계:

```python
# backend/services/extractor.py

class BaseExtractor:
    def extract(self, file_path: str, doc_id: str) -> list[Document]:
        raise NotImplementedError

class PyMuPDFExtractor(BaseExtractor):      # v0 베이스라인
    ...

class PyMuPDF4LLMExtractor(BaseExtractor):  # v1 기본
    ...

class VLMExtractor(BaseExtractor):          # vN 선택적
    ...
```

환경 변수 `EXTRACTOR=pymupdf4llm`으로 교체 가능.
