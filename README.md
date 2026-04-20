# rag-practice

PDF 문서를 업로드하고 자연어로 질의응답하는 RAG 기반 웹 앱.

---

## 아키텍처

```
PDF 업로드
    ↓
추출 (PyMuPDF)
    ↓
청킹 (RecursiveCharacterTextSplitter, chunk_size=800)
    ↓
임베딩 (BAAI/bge-m3)
    ↓
인덱싱 (FAISS + BM25)
    ↓
검색 (앙상블 RRF, top-20)
    ↓
리랭킹 (BAAI/bge-reranker-v2-m3, top-5)
    ↓
생성 (Claude API, SSE 스트리밍)
```

### 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 백엔드 | FastAPI, SQLAlchemy |
| 프론트엔드 | Streamlit |
| 데이터베이스 | PostgreSQL |
| 임베딩 모델 | `BAAI/bge-m3` (FlagEmbedding) |
| 벡터 검색 | FAISS (`IndexFlatIP`) |
| 키워드 검색 | BM25 (`rank-bm25`) |
| 리랭커 | `BAAI/bge-reranker-v2-m3` |
| LLM | Anthropic Claude (스트리밍) |

---

## 빠른 시작

### 1. PostgreSQL 실행

```bash
docker compose up -d postgres
```

### 2. 의존성 설치

```bash
uv pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# .env 파일에서 ANTHROPIC_API_KEY 설정
```

### 4. 백엔드 실행

```bash
uv run uvicorn backend.main:app --reload
```

### 5. 프론트엔드 실행

```bash
uv run streamlit run frontend/app.py
```

### 6. 기존 SQLite 데이터 마이그레이션 (선택)

`data/rag.db` 파일이 존재하는 경우에만 실행:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

---

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 문자열 | `postgresql://rag-practice:rag-practice@localhost:5434/rag-practice` |
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `EMBEDDING_MODEL` | 임베딩 모델 | `BAAI/bge-m3` |
| `DATA_DIR` | 데이터 저장 경로 | `./data` |
| `RETRIEVER` | 검색 방식 (`simple` \| `ensemble`) | `ensemble` |
| `RETRIEVAL_TOP_K` | 검색 후보 수 | `20` |
| `RERANK_TOP_N` | 리랭킹 후 최종 컨텍스트 수 | `5` |
| `MULTI_QUERY` | Multi-query 확장 활성화 | `false` |

전체 환경변수 목록은 `.env.example` 참조.

---

## 프로젝트 구조

```
rag-practice/
├── backend/
│   ├── api/
│   │   ├── chat.py          # POST /api/chat (SSE), DELETE /api/chat/{id}
│   │   └── documents.py     # POST/GET/DELETE /api/documents
│   ├── services/
│   │   ├── pipeline.py      # Retrieve → Rerank → Generate 통합
│   │   ├── retriever.py     # FAISS + BM25 앙상블 (RRF)
│   │   ├── reranker.py      # Cross-encoder 리랭킹
│   │   ├── generator.py     # Claude API 스트리밍
│   │   ├── embedder.py      # BGE-M3 임베딩
│   │   ├── indexer.py       # FAISS 인덱스 관리
│   │   ├── bm25_indexer.py  # BM25 인덱스 관리
│   │   ├── chunker.py       # 텍스트 청킹
│   │   ├── extractor.py     # PDF 텍스트 추출
│   │   └── query_expander.py# Multi-query paraphrase
│   ├── models/
│   └── main.py
├── frontend/
│   └── app.py               # Streamlit UI
├── evaluation/
│   ├── run_eval.py          # 평가 스크립트
│   ├── eval_set.json        # 평가 셋 (15개 질문)
│   ├── BASELINE.md          # 버전별 평가 결과
│   └── results/
├── specs/
│   ├── 001-pdf-rag-chat-webapp/  # v0~v3 구현 스펙
│   └── 002-postgres-local-db/    # PostgreSQL 마이그레이션 스펙
├── scripts/
│   └── migrate_sqlite_to_postgres.py
├── docker-compose.yml
└── pyproject.toml
```

---

## 평가 결과

평가 셋: 대신증권 FICC 투자 리포트 (PDF, 3페이지), 15개 질문

| 버전 | Recall@5 | Answerable@5 | Partial Match | 첫 토큰 지연 |
|------|----------|--------------|---------------|-------------|
| v0 (FAISS only) | 0.00% | 0.00% | 25.56% | 3,031ms |
| v1 (FAISS + BM25 앙상블) | 61.54% | 78.89% | 86.67% | 8,529ms |
| v2 (+ Multi-query) | 61.54% | — | 86.67% | 9,247ms |
| v3 (+ Reranker) | 61.54% | 76.67% | **85.00%** | 22,294ms* |

> *Reranker 모델 첫 로드(약 170초) 포함. 캐시 후 실 응답 10~25초 수준.

**Recall 한계 분석**: TABLE 카테고리 5문항(Q6~Q9, Q12)이 이미지 기반 데이터로 텍스트 추출 불가.
OCR 파이프라인 추가 시 Recall 대폭 향상 예상.

평가 실행 방법:

```bash
# 백엔드 실행 후, 테스트 PDF를 업로드한 상태에서
python -m evaluation.run_eval --doc-ids <문서_ID> --output-name v3_final
```

---

## 개발 가이드

- 기능 스펙: [`specs/001-pdf-rag-chat-webapp/spec.md`](specs/001-pdf-rag-chat-webapp/spec.md)
- 작업 목록: [`specs/001-pdf-rag-chat-webapp/plan/tasks.md`](specs/001-pdf-rag-chat-webapp/plan/tasks.md)
- 평가 기록: [`evaluation/BASELINE.md`](evaluation/BASELINE.md)
- 프로젝트 헌법: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
