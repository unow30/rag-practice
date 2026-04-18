# 구현 작업 목록: PDF RAG 대화형 웹 앱

**Feature**: specs/001-pdf-rag-chat-webapp  
**Created**: 2026-04-18  
**Strategy**: v0 베이스라인 → 평가 → 단계적 고도화

> 각 단계 완료 후 평가 지표를 반드시 측정하고, 목표치 미달 시 다음 단계로 넘어가기 전에 해당 단계를 개선한다.

---

## 마일스톤 개요

| 마일스톤 | 목표 | 완료 기준 |
|----------|------|-----------|
| **v0** | 동작하는 베이스라인 | PDF 업로드 → 질문 → 출처 있는 답변 반환 |
| **v0.5** | 평가 기준선 수립 | Recall@5, Exact Match 등 지표 측정 완료 |
| **v1** | 하이브리드 검색 | Recall@5 ≥ 80% |
| **v2** | Multi-query (조건부) | 표현 불일치 질문 Recall 개선 확인 |
| **v3** | Reranker 도입 | Exact Match ≥ 60%, Partial Match ≥ 85% |

---

## v0: 베이스라인 구축

### [T-01] 프로젝트 초기 설정

**의존성**: 없음  
**산출물**: 디렉토리 구조, `requirements.txt`, `.env.example`

- [x] 디렉토리 구조 생성
  ```
  rag-practice/
  ├── backend/
  │   ├── api/
  │   ├── services/
  │   ├── models/
  │   └── main.py
  ├── frontend/
  ├── data/
  │   ├── documents/
  │   └── indexes/
  └── evaluation/
  ```
- [x] `requirements.txt` 작성 (fastapi, uvicorn, pymupdf, langchain, faiss-cpu, sentence-transformers, FlagEmbedding, sqlalchemy, python-multipart, anthropic, streamlit)
- [x] `.env.example` 작성 (ANTHROPIC_API_KEY, EMBEDDING_MODEL, CHUNK_SIZE, CHUNK_OVERLAP, DATA_DIR, DB_PATH)
- [x] `data/documents/`, `data/indexes/` 디렉토리 생성

---

### [T-02] 데이터베이스 초기화

**의존성**: T-01  
**산출물**: `backend/models/database.py`, `backend/models/document.py`

- [x] SQLite 연결 설정 (SQLAlchemy)
- [x] `Document` 테이블 정의
  - id (UUID PK), name, file_path, file_hash, size_bytes, page_count, chunk_count, index_path, status, error_message, uploaded_at, processed_at
- [x] `Chunk` 테이블 정의
  - id (UUID PK), document_id (FK), chunk_index, content, content_type, page_number, page_end, section_title, version, token_count, faiss_index_id, created_at
- [x] `Document.status` ENUM 정의 (PENDING / EXTRACTING / CHUNKING / EMBEDDING / READY / FAILED)
- [x] DB 마이그레이션 스크립트 또는 `create_all()` 초기화

---

### [T-03] PDF 업로드 API

**의존성**: T-02  
**산출물**: `backend/api/documents.py` — `POST /api/documents`

- [x] 파일 유효성 검사
  - PDF 형식 확인 (MIME type + 확장자)
  - 파일 크기 ≤ 50MB
  - 중복 파일 감지 (SHA-256 해시 비교)
  - 문서 수 한도 확인 (≤ 20개)
- [x] 파일 저장: `data/documents/{doc_id}_{filename}`
- [x] Document 레코드 생성 (status=PENDING)
- [x] 백그라운드 처리 작업 트리거
- [x] 응답: `{ documents: [{ id, name, size_bytes, status, uploaded_at }] }`
- [x] 오류 응답: INVALID_FILE_TYPE, FILE_TOO_LARGE, DUPLICATE_FILE, DOCUMENT_LIMIT_EXCEEDED

---

### [T-04] PDF 추출 서비스 (v0: PyMuPDFLoader)

**의존성**: T-03  
**산출물**: `backend/services/extractor.py`

- [x] `BaseExtractor` 인터페이스 정의 (`extract(file_path, doc_id) -> list[Document]`)
- [x] `PyMuPDFExtractor` 구현 (v0 베이스라인)
  - `PyMuPDFLoader`로 페이지별 텍스트 추출
  - 이미지 기반 PDF 감지 → "이미지 기반 PDF는 현재 지원되지 않습니다" 오류
- [x] **메타데이터 필수 부착**:
  ```python
  doc.metadata = {
      "source":  file_path,
      "page":    page_num,
      "doc_id":  doc_id,
      "section": None,   # v0에서는 None
      "version": None,
  }
  ```
- [x] Document.status → EXTRACTING 업데이트
- [x] 추출 실패 시 status → FAILED, error_message 저장

---

### [T-05] 청킹 서비스

**의존성**: T-04  
**산출물**: `backend/services/chunker.py`

- [x] `RecursiveCharacterTextSplitter` 설정 (chunk_size=800, chunk_overlap=120)
- [x] 청크별 Chunk 레코드 생성 (content, page_number, chunk_index, content_type=TEXT)
- [x] 표 청크 감지: Markdown table 패턴(`|---`) 포함 시 content_type=TABLE
- [x] Document.page_count, chunk_count 업데이트
- [x] Document.status → CHUNKING 업데이트

---

### [T-06] 임베딩 및 FAISS 인덱싱 서비스

**의존성**: T-05  
**산출물**: `backend/services/embedder.py`, `backend/services/indexer.py`

- [x] BGE-M3 모델 로드 (`BAAI/bge-m3`, FlagEmbedding)
- [x] 청크 배치 임베딩 (배치 크기 32)
- [x] FAISS `IndexFlatIP` 생성 및 벡터 추가
- [x] 인덱스 저장: `data/indexes/{doc_id}/index.faiss`, `index.pkl` (chunk_id 매핑)
- [x] Document.index_path, Chunk.faiss_index_id 업데이트
- [x] Document.status → EMBEDDING → READY 업데이트
- [x] 처리 실패 시 status → FAILED, error_message 저장

---

### [T-07] 문서 관리 API (목록, 상태, 삭제)

**의존성**: T-02  
**산출물**: `backend/api/documents.py` — GET, DELETE 엔드포인트

- [x] `GET /api/documents`: 문서 목록 반환 (id, name, size_bytes, page_count, chunk_count, status, uploaded_at, processed_at)
- [x] `GET /api/documents/{id}/status`: 처리 상태 + 진행 메시지 반환
- [x] `DELETE /api/documents/{id}`:
  - PDF 파일 삭제 (`data/documents/`)
  - FAISS 인덱스 디렉토리 삭제 (`data/indexes/{doc_id}/`)
  - SQLite Chunk + Document 레코드 삭제
  - 404 처리

---

### [T-08] 단순 FAISS 검색 서비스 (v0 Retriever)

**의존성**: T-06  
**산출물**: `backend/services/retriever.py`

- [x] 지정 문서(들)의 FAISS 인덱스 로드 및 병합
- [x] 질문 임베딩 후 top-k 검색 (RETRIEVAL_TOP_K 환경 변수, 기본 20)
- [x] 검색 결과에 메타데이터(page, doc_id, content, document_name, score) 포함하여 반환
- [x] 문서 범위 필터링 (document_ids 지정 시 해당 문서만 검색)

---

### [T-09] LLM 답변 생성 서비스

**의존성**: T-08  
**산출물**: `backend/services/generator.py`

- [x] 시스템 프롬프트 정의 ("근거 없는 추측 금지" 원칙)
- [x] `format_docs()` 함수 구현 (청크 목록 → 컨텍스트 문자열)
- [x] Claude API 스트리밍 연결 (anthropic SDK, `stream=True`)
- [x] 문서에서 답변 불가 시 "문서에서 관련 정보를 찾을 수 없습니다" 반환
- [x] Source 객체 구성: document_name, page_number, content_snippet, relevance_score

---

### [T-10] 대화 API (스트리밍)

**의존성**: T-08, T-09  
**산출물**: `backend/api/chat.py` — `POST /api/chat`, `DELETE /api/chat/{id}`

- [x] 세션 인메모리 대화 저장소 구현 (Conversation, Message)
- [x] `POST /api/chat` — SSE 스트리밍 응답
  - conversation_id 신규 생성 또는 기존 세션 이어서
  - document_ids로 검색 범위 설정
  - retriever → generator 순서로 호출
  - `event: token` 스트림 전송
  - `event: done` — sources, latency_ms 포함
  - `event: error` — AI 서비스 타임아웃(30초) 처리
- [x] `DELETE /api/chat/{id}` — 대화 기록 초기화
- [x] READY 상태 문서 없을 시 NO_READY_DOCUMENTS 오류

---

### [T-11] FastAPI 앱 조립

**의존성**: T-03, T-07, T-10  
**산출물**: `backend/main.py`

- [x] FastAPI 앱 생성, 라우터 등록
- [x] CORS 설정 (Streamlit 프론트엔드 허용)
- [x] 앱 시작 시 DB 초기화, 데이터 디렉토리 확인
- [x] 백그라운드 처리 플레이스홀더 → 실제 process_document 연결

---

### [T-12] Streamlit 프론트엔드 (v0)

**의존성**: T-10, T-11  
**산출물**: `frontend/app.py`

- [x] **사이드바**: 문서 업로드 (드래그 앤 드롭, 진행률), 문서 목록, 질의 대상 문서 선택, 삭제 버튼
- [x] **메인 영역**: 대화창 (질문 입력, 답변 스트리밍 표시)
- [x] 답변 하단에 출처 표시 (문서명, 페이지 번호, 인용 구절)
- [x] 대화 기록 초기화 버튼
- [x] 문서 처리 중 상태 폴링 (2초 간격 자동 rerun)
- [x] AI 오류 시 재시도 버튼 표시

---

### [T-13] v0 통합 테스트

**의존성**: T-12  
**완료 기준**: 아래 시나리오 모두 동작 확인

- [ ] PDF 1개 업로드 → 30초 이내 READY 전환 확인 (수동)
- [ ] 텍스트 질문 → 3초 이내 첫 토큰 + 출처 포함 답변 (수동)
- [ ] 문서에 없는 내용 질문 → "찾을 수 없습니다" 응답 (수동)
- [ ] 문서 삭제 후 해당 문서 내용 미반환 확인 (수동)
- [x] 50MB 초과 파일 업로드 → 오류 메시지 (자동 테스트)
- [x] 잘못된 파일 형식 업로드 → INVALID_FILE_TYPE 오류 (자동 테스트)
- [x] 빈 문서 목록 조회 → 정상 응답 (자동 테스트)

---

## v0.5: 평가 셋 구축

### [T-14] 평가 셋 JSON 구성

**의존성**: T-13 (실제 PDF로 테스트 가능한 상태)  
**산출물**: `evaluation/eval_set.json`

- [x] 테스트 PDF 준비 (실제 사용할 문서 유형과 동일한 종류)
- [x] 최소 15개 질문-정답 쌍 작성
  - 텍스트 질문 5개 (EASY ~ MEDIUM)
  - 표 기반 질문 5개 (수치, 비교)
  - 그래프/복합 질문 3개 (HARD)
  - 문서에 없는 질문 2개 (negative case)
- [x] 각 질문에 keywords, category, source_page, difficulty 기재

```json
[
  {
    "id": 1,
    "question": "...",
    "expected_answer": "...",
    "keywords": ["..."],
    "category": "TEXT | TABLE | FIGURE | MIXED",
    "source_page": 0,
    "difficulty": "EASY | MEDIUM | HARD"
  }
]
```

---

### [T-15] 평가 스크립트 구현

**의존성**: T-14  
**산출물**: `evaluation/run_eval.py`

- [x] 평가 셋 로드, 각 질문을 파이프라인에 전송
- [x] Recall@5 계산: 정답 청크가 candidate_docs top-5 안에 있는가
- [x] Answerable@5 계산: final_docs 컨텍스트만으로 정답 포함 가능한가
- [x] Exact Match: 답변에 expected_answer 완전 포함
- [x] Partial Match: keywords 중 몇 개 포함
- [x] Latency: 질문 제출 ~ 첫 토큰 시간(ms)
- [x] 결과 콘솔 출력 + `evaluation/results/YYYYMMDD_HHMMSS.json` 저장

---

### [T-16] v0 기준선 측정

**의존성**: T-15  
**완료 기준**: 지표 측정 완료 및 기록

- [ ] 평가 스크립트 실행
- [ ] 결과 기록 (각 지표 수치)
- [ ] **판단**: Recall@5 ≥ 80% → v3로 바로 이동, < 80% → v1 진행

---

## v1: 하이브리드 검색 (BM25 + RRF)

> **진입 조건**: v0.5 Recall@5 < 80%

### [T-17] BM25 인덱싱 추가

**의존성**: T-06  
**산출물**: `backend/services/bm25_indexer.py`

- [ ] `rank_bm25` 설치 및 `BM25Okapi` 초기화
- [ ] 문서 인덱싱 시 BM25 역인덱스 생성
- [ ] BM25 인덱스 저장: `data/indexes/{doc_id}/bm25.pkl`
- [ ] 문서 삭제 시 BM25 인덱스도 함께 삭제

---

### [T-18] EnsembleRetriever (FAISS + BM25 + RRF) 구현

**의존성**: T-17  
**산출물**: `backend/services/retriever.py` 수정

- [ ] `EnsembleRetriever(retrievers=[faiss, bm25], weights=[0.5, 0.5])` 구성
- [ ] RRF(k=60)로 결합, top-20 후보 반환
- [ ] 환경 변수 `RETRIEVER=ensemble` 로 v0 단순 FAISS와 전환 가능하게 설계

---

### [T-19] v1 평가 재측정

**의존성**: T-18  
**완료 기준**: Recall@5 ≥ 80%

- [ ] 평가 스크립트 재실행
- [ ] v0 대비 Recall@5 변화 확인
- [ ] **판단**: 목표 미달 시 RRF weight 조정 (예: [0.6, 0.4]) 후 재측정

---

## v2: Multi-query 확장 (조건부)

> **진입 조건**: 표현 불일치 카테고리 질문의 Recall 개선이 필요할 때

### [T-20] Multi-query 모듈 구현

**의존성**: T-18  
**산출물**: `backend/services/query_expander.py`

- [ ] LLM으로 원 질문의 2~3개 paraphrase 생성
- [ ] 각 변형 질문으로 검색 실행
- [ ] 중복 청크 제거 후 RRF 결합
- [ ] 환경 변수 `MULTI_QUERY=true/false`로 활성화 제어

---

### [T-21] v2 평가 재측정

**의존성**: T-20

- [ ] 평가 스크립트 재실행
- [ ] 표현 불일치 카테고리 질문 Recall 개선 확인
- [ ] Latency 증가분 확인 (Multi-query는 LLM 호출 추가 → 지연 증가)

---

## v3: Cross-encoder Reranker 도입

### [T-22] Reranker 서비스 구현

**의존성**: T-18  
**산출물**: `backend/services/reranker.py`

- [ ] `BAAI/bge-reranker-v2-m3` 모델 로드 (FlagEmbedding)
- [ ] `rerank(question, candidate_docs, top_n=5) -> list[Document]` 구현
- [ ] 각 문서에 `metadata['rerank_score']` 부착
- [ ] top_n 환경 변수 설정 (`RERANK_TOP_N=5`)

---

### [T-23] 파이프라인 통합 (Retrieve → Rerank → Generate)

**의존성**: T-22  
**산출물**: `backend/services/pipeline.py`

- [ ] `ask()` 함수 구현 (research.md §13 참조)
- [ ] 각 단계 디버그 로깅 추가 (candidate 수, rerank 점수)
- [ ] `POST /api/chat` 에서 `ask()` 함수 호출로 전환
- [ ] Retriever top-k 20 → Reranker top-n 5로 파이프라인 연결

---

### [T-24] 최종 평가 및 검증

**의존성**: T-23  
**완료 기준**: 모든 Success Criteria 충족

- [ ] 평가 스크립트 최종 실행
- [ ] 목표 지표 확인:
  - Recall@5 ≥ 80% ✓
  - Answerable@5 ≥ 80% ✓
  - Exact Match ≥ 60% ✓
  - Partial Match ≥ 85% ✓
  - Latency (첫 토큰) ≤ 3,000ms ✓
- [ ] 실패 카테고리 분석 (텍스트/표/그래프별)
- [ ] 결과 `evaluation/results/final.json` 저장

---

## 전체 작업 의존성 요약

```
T-01 → T-02 → T-03 → T-04 → T-05 → T-06 → T-08 → T-09 → T-10 → T-11 → T-12 → T-13
                ↘                                    ↗
                 T-07 ─────────────────────────────
                 
T-13 → T-14 → T-15 → T-16
                        ↓
              Recall@5<80%? → T-17 → T-18 → T-19
                                              ↓
                              표현 불일치? → T-20 → T-21
                                              ↓
                                           T-22 → T-23 → T-24
```

---

## 작업 우선순위 (v0 병렬 가능 항목)

T-01 완료 후 아래 두 흐름 병렬 진행 가능:
- **흐름 A**: T-02 → T-03 → T-04 → T-05 → T-06 → T-08 → T-09 → T-10
- **흐름 B**: T-02 → T-07

T-11은 흐름 A + 흐름 B 완료 후 진행.
