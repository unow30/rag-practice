# Data Model: PDF RAG 대화형 웹 앱

**Feature**: specs/001-pdf-rag-chat-webapp  
**Created**: 2026-04-18

---

## 엔티티 관계 개요

```
Document (1) ──── (N) Chunk
Document (N) ──── (N) Conversation  [document_scope]
Conversation (1) ──── (N) Message
Message (1) ──── (N) Source
Source (N) ──── (1) Chunk
```

---

## 1. Document (문서)

**저장소**: SQLite `documents` 테이블 + 로컬 파일시스템

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | UUID | PK, NOT NULL | 고유 식별자 |
| name | VARCHAR(255) | NOT NULL | 원본 파일명 |
| file_path | VARCHAR(512) | NOT NULL, UNIQUE | 로컬 저장 경로 |
| file_hash | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 해시 (중복 업로드 감지) |
| size_bytes | INTEGER | NOT NULL | 파일 크기 (≤ 52,428,800 = 50MB) |
| page_count | INTEGER | NULL | 추출 후 확정 |
| chunk_count | INTEGER | NULL | 인덱싱 후 확정 |
| index_path | VARCHAR(512) | NULL | FAISS 인덱스 디렉터리 경로 |
| status | ENUM | NOT NULL | 처리 상태 (아래 참조) |
| error_message | TEXT | NULL | 실패 시 오류 내용 |
| uploaded_at | DATETIME | NOT NULL, DEFAULT now | 업로드 일시 |
| processed_at | DATETIME | NULL | 처리 완료 일시 |

### Document.status 상태 전이

```
PENDING → EXTRACTING → CHUNKING → EMBEDDING → READY
                                              ↑
PENDING → EXTRACTING → FAILED (any step)
```

| 상태 | 의미 |
|------|------|
| PENDING | 업로드 완료, 처리 대기 중 |
| EXTRACTING | 텍스트 추출 중 |
| CHUNKING | 청킹 및 전처리 중 |
| EMBEDDING | 임베딩 및 인덱싱 중 |
| READY | 질의 가능 상태 |
| FAILED | 처리 실패 (error_message 참조) |

### 유효성 규칙

- `size_bytes` ≤ 52,428,800 (50MB)
- 전체 문서 수 ≤ 20개 (application-level 제약)
- `file_hash` UNIQUE: 동일 PDF 중복 업로드 차단
- `name` 은 업로드 시 원본 파일명 그대로 저장

---

## 2. Chunk (문서 조각)

**저장소**: SQLite `chunks` 테이블 (메타데이터) + FAISS 인덱스 (벡터)

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | UUID | PK, NOT NULL | 고유 식별자 |
| document_id | UUID | FK → Document.id, NOT NULL | 소속 문서 |
| chunk_index | INTEGER | NOT NULL | 문서 내 순서 (0-based) |
| content | TEXT | NOT NULL | 청크 텍스트 내용 |
| content_type | ENUM | NOT NULL | 콘텐츠 유형 (TEXT / TABLE / FIGURE) |
| page_number | INTEGER | NOT NULL | 원문 페이지 번호 (1-based) |
| page_end | INTEGER | NULL | 청크가 걸친 끝 페이지 (멀티페이지 청크) |
| section_title | VARCHAR(255) | NULL | 해당 청크의 섹션 제목 (구조 파악·디버깅용) |
| version | VARCHAR(64) | NULL | 문서 버전 식별자 (동일 문서 복수 버전 대응) |
| token_count | INTEGER | NOT NULL | 청크 토큰 수 |
| faiss_index_id | INTEGER | NULL | FAISS 내부 인덱스 ID |
| created_at | DATETIME | NOT NULL, DEFAULT now | 생성 일시 |

### Chunk.content_type

| 값 | 의미 |
|----|------|
| TEXT | 일반 텍스트 단락 |
| TABLE | Markdown table 형식으로 추출된 표 |
| FIGURE | 그래프·이미지에 대한 캡션/설명 텍스트 |

### LangChain 메타데이터 매핑

추출 시 각 `Document` 객체의 `metadata`에 아래 필드를 설정하여 이후 검색·재정렬·출처 표시에 일관되게 활용:

```python
doc.metadata = {
    "source":   file_path,      # → Chunk.document.file_path
    "page":     page_num,       # → Chunk.page_number
    "doc_id":   doc_id,         # → Chunk.document_id
    "section":  section_title,  # → Chunk.section_title (NULL 허용)
    "version":  version,        # → Chunk.version (NULL 허용)
}
```

### 유효성 규칙

- `content` 길이: 100 ~ 1500 characters (청킹 파라미터에 따라 조정)
- `token_count`: chunk_size 기준 ≤ 1000 토큰
- `chunk_index`: 동일 `document_id` 내에서 0부터 순차 증가, UNIQUE(document_id, chunk_index)
- `section_title`, `version`: 추출 불가 시 NULL 허용 (필수 아님)

---

## 3. Conversation (대화 세션)

**저장소**: 서버 인메모리 (세션 종료 시 소멸)

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | UUID | PK | 고유 식별자 |
| document_scope | List[UUID] | NOT NULL | 질의 대상 문서 ID 목록 (비어있으면 전체) |
| created_at | DATETIME | NOT NULL | 대화 시작 일시 |
| message_count | INTEGER | NOT NULL, DEFAULT 0 | 누적 메시지 수 |

### 유효성 규칙

- `document_scope`의 각 UUID는 `status = READY`인 Document.id 여야 함
- 세션(브라우저 탭) 종료 시 서버 메모리에서 제거

---

## 4. Message (메시지)

**저장소**: 서버 인메모리 (Conversation에 소속)

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | UUID | PK | 고유 식별자 |
| conversation_id | UUID | FK → Conversation.id, NOT NULL | 소속 대화 |
| role | ENUM | NOT NULL | 역할 (USER / ASSISTANT) |
| content | TEXT | NOT NULL | 메시지 내용 |
| sources | List[Source] | NULL | 답변 근거 출처 (ASSISTANT만 해당) |
| created_at | DATETIME | NOT NULL | 생성 일시 |
| latency_ms | INTEGER | NULL | 답변 생성 소요 시간 (ms) |

---

## 5. Source (출처)

**저장소**: Message 내 임베디드 (별도 테이블 없음)

| 필드 | 타입 | 설명 |
|------|------|------|
| chunk_id | UUID | 참조 Chunk.id |
| document_id | UUID | 참조 Document.id |
| document_name | VARCHAR(255) | 표시용 문서명 (비정규화) |
| page_number | INTEGER | 원문 페이지 번호 |
| content_snippet | VARCHAR(500) | 답변 근거 인용 텍스트 (최대 200자) |
| relevance_score | FLOAT | Reranker 점수 (0.0 ~ 1.0) |

---

## 6. EvaluationSet (평가 셋) — 개발/테스트 전용

**저장소**: `evaluation/eval_set.json`

| 필드 | 타입 | 설명 |
|------|------|------|
| id | INTEGER | 고유 번호 |
| question | TEXT | 질문 |
| expected_answer | TEXT | 정답 |
| keywords | List[str] | 핵심 키워드 |
| category | ENUM | 질문 유형 (TEXT / TABLE / FIGURE / MIXED) |
| source_page | INTEGER | 정답이 있는 페이지 |
| difficulty | ENUM | 난이도 (EASY / MEDIUM / HARD) |

---

## 인덱스 설계 (SQLite)

```sql
-- Document 조회 최적화
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_uploaded_at ON documents(uploaded_at DESC);

-- Chunk 조회 최적화
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_page ON chunks(document_id, page_number);
```

---

## FAISS 인덱스 구조

```
data/indexes/
└── {document_id}/
    ├── index.faiss      # FAISS 벡터 인덱스 (IVF 또는 Flat)
    ├── index.pkl        # chunk_id 매핑 테이블
    └── bm25.pkl         # BM25 역인덱스 (해당 문서)
```

- **FAISS 인덱스 유형**: `IndexFlatIP` (v0, 소규모 문서에 충분) → 문서 수 증가 시 `IndexIVFFlat` 전환 검토
- 문서 삭제 시 해당 디렉토리 전체 삭제 + SQLite chunks 레코드 삭제
