# Research: PDF RAG 대화형 웹 앱

**Feature**: specs/001-pdf-rag-chat-webapp  
**Created**: 2026-04-18  
**Status**: Complete (Phase 2 업데이트: 오케스트레이션 설계 반영)

---

## 1. PDF 추출 라이브러리

### Decision: pyMuPDF4LLM (기본) + VLM 선택적 fallback

**Rationale**:
- `pyMuPDF4LLM`은 LLM 파이프라인에 최적화된 Markdown 출력을 제공하며, 표를 Markdown table 형태로 변환하여 청크 내 구조를 보존한다.
- `pyMuPDFLoader`(LangChain)는 페이지 단위 텍스트를 반환하지만 표 구조가 평탄화될 수 있어 표 비중이 높은 문서에서 품질 저하 가능.
- VLM(Vision Language Model)은 그래프·복잡한 레이아웃에 유효하나, 처리 시간과 비용이 크므로 표/그래프가 핵심 정답 소스인 경우에만 선택적으로 적용.

**Alternatives considered**:
- `pdfplumber`: 표 추출에 강하지만 LLM 파이프라인 통합 과정이 더 복잡.
- `unstructured`: 다목적이지만 의존성이 무겁고 설정 복잡도 높음.

**Phased approach**:
- v0: `pyMuPDF4LLM`만 사용
- v1+: 표/그래프 감지 후 VLM fallback 조건부 적용

---

## 2. 청킹 전략

### Decision: RecursiveCharacterTextSplitter, chunk_size=800, overlap=15%

**Rationale**:
- Recursive splitter는 단락 → 문장 → 단어 순서로 자연스러운 경계에서 분할하여 의미 단위 보존.
- chunk_size 700~1000 범위에서 시작, 700~1000 중 800을 기본값으로 사용.
- overlap 15~20%는 청크 경계에서 단절된 문맥을 보완. 120~160 토큰 overlap.
- 표는 pyMuPDF4LLM이 Markdown table로 출력하므로 가능하면 하나의 청크에 보존.

**Alternatives considered**:
- `SemanticChunker`: 의미 기반 분할이지만 임베딩 비용이 추가로 발생.
- 고정 페이지 단위 청킹: 단락 중간에서 잘릴 가능성 높음.

---

## 3. 임베딩 모델

### Decision: BGE-M3

**Rationale**:
- 다국어(한국어 포함) 지원, 한국어 문서·질문 모두 고품질 임베딩 생성.
- Dense + Sparse + ColBERT 방식 통합 지원(Multi-functionality), FAISS dense 검색과 궁합 우수.
- HuggingFace에서 무료 사용 가능, 로컬 실행으로 외부 API 의존성 제거.
- 최대 토큰 8192, chunk_size 800 기준으로 충분한 컨텍스트 처리 가능.

**Alternatives considered**:
- OpenAI `text-embedding-3-small`: 성능 우수하나 외부 API 비용 발생.
- `ko-sroberta-multitask`: 한국어 특화이지만 긴 문서 처리 제한.

---

## 4. 벡터 저장소

### Decision: FAISS (로컬 파일 기반)

**Rationale**:
- 개인용 단일 사용자 앱에서 서버 없이 로컬 파일(.faiss, .pkl)로 운영 가능.
- 최대 20개 문서, 50MB/파일 환경에서 완전히 적합한 규모.
- LangChain FAISS 통합이 잘 되어 있어 BM25 앙상블 구성 용이.
- 인덱스를 디스크에 저장·로드하여 서버 재시작 후에도 데이터 유지.

**Alternatives considered**:
- Chroma: 로컬 사용 가능하지만 FAISS 대비 속도 이점 없음.
- Pinecone/Weaviate: 클라우드 의존, 개인용 앱에 과함.

---

## 5. 검색 전략 (하이브리드 + RRF)

### Decision: FAISS(Dense) + BM25 Hybrid with Reciprocal Rank Fusion

**Rationale**:
- Dense(FAISS): 의미적 유사도 기반 검색, 표현 불일치에 강함.
- Sparse(BM25): 키워드 정확 매칭, 고유명사·숫자·전문 용어에 강함.
- RRF(Reciprocal Rank Fusion): 두 순위 목록을 단순 합산이 아닌 순위 기반으로 결합하여 분산 보상.
- 앙상블로 recall 우선 확보 → reranker로 precision 향상.

**BM25 구현**: `rank_bm25` 라이브러리 (BM25Okapi)  
**RRF 파라미터**: k=60 (표준값)

---

## 6. 쿼리 확장 (Multi-query)

### Decision: 조건부 적용 (v1 이후), 기본 2~3개 변형 생성

**Rationale**:
- 도메인 전문 용어나 표현 불일치가 많은 질문에서 recall 향상.
- LLM으로 원 질문의 2~3개 paraphrase 생성 후 각각 검색, 중복 제거 후 합산.
- v0에서는 단순 검색으로 시작하고, 평가 셋에서 recall 부족 확인 시 활성화.

---

## 7. Reranker

### Decision: Cross-encoder (BAAI/bge-reranker-v2-m3 권장)

**Rationale**:
- Bi-encoder(임베딩 검색)의 빠른 후보 선정 후, Cross-encoder로 정밀 재정렬.
- `BAAI/bge-reranker-v2-m3`: 한국어 지원, BGE-M3와 동일 계열로 일관성 높음.
- top-k=20 후보에서 top-5~10으로 좁혀 LLM 컨텍스트에 전달.

**Alternatives considered**:
- `cross-encoder/ms-marco-MiniLM-L-12-v2`: 영어 중심, 한국어 문서 성능 제한.
- Cohere Rerank API: 외부 의존성 및 비용 발생.

---

## 8. LLM (답변 생성)

### Decision: Claude API (claude-sonnet-4-6) 기본, OpenAI gpt-4o 호환

**Rationale**:
- 현재 프로젝트 환경(Claude Code)과 일관성.
- 스트리밍 응답 지원으로 첫 토큰 3초 이내 목표 달성 용이.
- "근거 없는 내용 추측 금지" 시스템 프롬프트와 함께 grounded 답변 생성.
- 환경 변수로 모델 전환 가능하게 구성.

---

## 9. 웹 프레임워크

### Decision: FastAPI (백엔드) + Streamlit 또는 Next.js (프론트엔드)

**Rationale**:
- FastAPI: 비동기 스트리밍 응답, 파일 업로드, OpenAPI 자동 문서화 지원.
- 프론트엔드:
  - **Streamlit**: 빠른 v0 구축, 파이썬 단일 스택, RAG 프로토타입에 적합.
  - **Next.js**: 완성도 높은 UI, 스트리밍 SSE 처리 용이, 프로덕션 품질.
  - v0는 Streamlit으로 시작하여 검증 후 Next.js로 교체 권장.

---

## 10. 데이터 저장

### Decision: 로컬 파일시스템 + SQLite

**Rationale**:
- PDF 원본: 로컬 `/data/documents/` 디렉토리에 저장.
- FAISS 인덱스: `/data/indexes/{document_id}/` 에 `.faiss` + `.pkl` 저장.
- 문서 메타데이터(Document 엔티티): SQLite (경량, 서버 불필요, 단일 사용자 적합).
- 세션 대화 기록: 서버 인메모리 (세션 종료 시 소멸, spec 결정 사항).

---

## 11. 평가 파이프라인

### Decision: 수동 질문-정답 셋 기반 오프라인 평가

**평가 지표**:
| 지표 | 측정 대상 | 목표 |
|------|-----------|------|
| Recall@5 | 정답 청크가 상위 5개 안에 포함 여부 | 80% 이상 |
| Answerable@5 | 상위 5 근거로 정답 생성 가능 여부 | 80% 이상 |
| Exact Match | 최종 답변이 정답과 완전 일치 | 60% 이상 |
| Partial Match | 핵심 키워드 포함 여부 | 85% 이상 |
| Latency | 질문 제출 ~ 첫 토큰 표시 | 3초 이내 |

**평가 셋 구성**: 10~20개 질문, 각 질문에 정답·키워드·카테고리(텍스트/표/그래프) 포함.

---

## 13. 오케스트레이션 패턴

### Decision: 단계 분리형 파이프라인 (Retrieve → Rerank → Generate)

**Rationale**:
- 1차 검색(retriever), 2차 재정렬(reranker), 최종 생성(generator)을 각각 독립 컴포넌트로 분리.
- 답변이 틀렸을 때 어느 단계에서 실패했는지 격리하여 빠르게 진단 가능.
- LangChain LCEL 체인으로 연결하되, 각 단계의 중간 출력을 로깅하여 디버깅 지원.

**코드 구조 원칙**:
- "예쁘게 짜는 것"보다 "실패 원인을 빨리 찾는 것"이 우선.
- 각 단계의 입출력을 명확하게 정의하여 단계별 단독 테스트 가능.

```python
# 핵심 파이프라인 시그니처
def ask(question, retriever, reranker, answer_chain) -> dict:
    candidate_docs = retriever.invoke(question)   # 1단계: 후보 검색
    final_docs     = reranker.rerank(question, candidate_docs)  # 2단계: 재정렬
    context        = format_docs(final_docs)
    answer         = answer_chain.invoke({"question": question, "context": context})
    return {"answer": answer, "documents": final_docs}
```

---

## 14. 단계별 구현 로드맵

### Decision: 5단계 점진적 고도화

| 단계 | 구성 | 목적 |
|------|------|------|
| v0 | PyMuPDFLoader + RecursiveSplitter + FAISS | 동작하는 베이스라인 확보 |
| v0.5 | 평가 셋 10~20개 구성 + 지표 측정 | 현재 성능 기준선 수립 |
| v1 | + BM25 Ensemble (RRF) | Recall 향상 |
| v2 | + Multi-query (필요 시) | 표현 불일치 도메인 대응 |
| v3 | + Cross-encoder Reranker | Precision 향상 |

**원칙**:
- 각 단계 적용 후 반드시 평가 셋으로 지표 재측정.
- 지표가 개선되지 않으면 다음 단계로 넘어가지 않음.
- VLM은 텍스트 중심 PDF에서 오히려 숫자 인식 오류 가능성 있음 → 성능 충분하면 도입하지 않음.

---

## 15. 청크 메타데이터 전략

### Decision: LangChain doc.metadata에 5개 필드 표준화

**Rationale**:
- 출처 표시, 디버깅, 필터링 모두 메타데이터에 의존.
- 답변이 틀렸을 때 근거 청크를 직접 확인하려면 페이지·섹션 정보가 필수.
- 추출 단계에서 한 번 설정하면 검색·재정렬·답변 생성 전 단계에서 재사용.

**표준 메타데이터 스키마**:
```python
doc.metadata = {
    "source":   file_path,      # 원본 PDF 경로 (디버깅용)
    "page":     page_num,       # 페이지 번호 (출처 표시)
    "doc_id":   doc_id,         # Document UUID (문서 필터링)
    "section":  section_title,  # 섹션 제목 (NULL 허용, 구조 파악용)
    "version":  version,        # 문서 버전 (NULL 허용, 동일 문서 복수 버전 대응)
}
```

---

## 12. 프로젝트 구조

```
rag-practice/
├── backend/
│   ├── api/                  # FastAPI 라우터
│   ├── services/
│   │   ├── extractor.py      # PDF 추출 (pyMuPDF4LLM)
│   │   ├── chunker.py        # 청킹
│   │   ├── embedder.py       # BGE-M3 임베딩
│   │   ├── indexer.py        # FAISS 인덱스 관리
│   │   ├── retriever.py      # FAISS + BM25 + RRF
│   │   ├── reranker.py       # Cross-encoder
│   │   └── generator.py      # LLM 답변 생성
│   ├── models/               # SQLite ORM 모델
│   └── main.py
├── frontend/
│   └── app/                  # Streamlit 또는 Next.js
├── data/
│   ├── documents/            # 업로드된 PDF 원본
│   └── indexes/              # FAISS 인덱스 파일
├── evaluation/
│   ├── eval_set.json         # 질문-정답 평가 셋
│   └── run_eval.py           # 평가 실행 스크립트
└── specs/                    # speckit 산출물
```
