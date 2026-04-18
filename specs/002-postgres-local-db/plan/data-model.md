# Data Model: 로컬 PostgreSQL 데이터베이스 마이그레이션

**Feature**: specs/002-postgres-local-db  
**Created**: 2026-04-18

> 이 문서는 기존 SQLite 스키마를 PostgreSQL로 이전할 때의 변경 사항을 기술한다.  
> 엔티티 구조는 `specs/001-pdf-rag-chat-webapp/plan/data-model.md`와 동일하며,  
> PostgreSQL 특화 항목만 별도로 명시한다.

---

## 스키마 변경 요약

| 항목 | 기존 (SQLite) | 변경 (PostgreSQL) |
|------|--------------|-----------------|
| 연결 URL | `sqlite:///./data/rag.db` | `postgresql://user:pass@localhost:5434/rag-practice` |
| connect_args | `{"check_same_thread": False}` | 제거 |
| Connection Pool | 없음 (파일 기반) | SQLAlchemy QueuePool (기본값) + `pool_pre_ping=True` |
| ENUM 타입 | SQLAlchemy 소프트 ENUM | PostgreSQL 네이티브 ENUM 자동 생성 |
| DateTime | naive datetime | `DateTime(timezone=True)` (UTC) |

---

## 1. Document (문서)

**저장소**: PostgreSQL `documents` 테이블 + 로컬 파일시스템

| 필드 | 타입 | 제약 | PostgreSQL 타입 |
|------|------|------|----------------|
| id | String(36) | PK, NOT NULL | VARCHAR(36) |
| name | String(255) | NOT NULL | VARCHAR(255) |
| file_path | String(512) | NOT NULL, UNIQUE | VARCHAR(512) |
| file_hash | String(64) | NOT NULL, UNIQUE | VARCHAR(64) |
| size_bytes | BigInteger | NOT NULL | BIGINT |
| page_count | Integer | NULL | INTEGER |
| chunk_count | Integer | NULL | INTEGER |
| index_path | String(512) | NULL | VARCHAR(512) |
| status | Enum(DocumentStatus) | NOT NULL | ENUM('PENDING','EXTRACTING','CHUNKING','EMBEDDING','READY','FAILED') |
| error_message | Text | NULL | TEXT |
| uploaded_at | DateTime(timezone=True) | NOT NULL, DEFAULT now() | TIMESTAMPTZ |
| processed_at | DateTime(timezone=True) | NULL | TIMESTAMPTZ |

### Document.status 상태 전이

```
PENDING → EXTRACTING → CHUNKING → EMBEDDING → READY
                                             ↗
                       → FAILED (any step)
```

---

## 2. Chunk (문서 청크)

**저장소**: PostgreSQL `chunks` 테이블 (메타데이터) + FAISS 인덱스 파일 (벡터)

| 필드 | 타입 | 제약 | PostgreSQL 타입 |
|------|------|------|----------------|
| id | String(36) | PK, NOT NULL | VARCHAR(36) |
| document_id | String(36) | FK → documents.id CASCADE DELETE, NOT NULL | VARCHAR(36) |
| chunk_index | Integer | NOT NULL | INTEGER |
| content | Text | NOT NULL | TEXT |
| content_type | Enum(ContentType) | NOT NULL | ENUM('TEXT','TABLE','FIGURE') |
| page_number | Integer | NOT NULL | INTEGER |
| page_end | Integer | NULL | INTEGER |
| section_title | String(255) | NULL | VARCHAR(255) |
| version | String(64) | NULL | VARCHAR(64) |
| token_count | Integer | NOT NULL, DEFAULT 0 | INTEGER |
| faiss_index_id | Integer | NULL | INTEGER |
| created_at | DateTime(timezone=True) | NOT NULL, DEFAULT now() | TIMESTAMPTZ |

---

## 3. Conversation & Message (변경 없음)

**저장소**: 서버 인메모리 유지 — 이번 마이그레이션 범위 외.

---

## 인덱스 설계 (PostgreSQL)

```sql
-- Document 조회 최적화
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_uploaded_at ON documents(uploaded_at DESC);

-- Chunk 조회 최적화
CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_page ON chunks(document_id, page_number);
```

SQLAlchemy ORM 모델에 `Index()` 지시자를 추가하거나 `Base.metadata.create_all()` 후 별도 실행.

---

## FAISS 인덱스 구조 (변경 없음)

```
data/indexes/
└── {document_id}/
    ├── index.faiss      # FAISS 벡터 인덱스
    └── index.pkl        # chunk_id 매핑 테이블
```

`document.index_path`가 동일 경로를 참조하므로 마이그레이션 후 별도 변경 불필요.

---

## 마이그레이션 데이터 흐름

```
SQLite (data/rag.db)
  └── documents 테이블  →  PostgreSQL documents 테이블
  └── chunks 테이블     →  PostgreSQL chunks 테이블
                                  (document FK 선행 삽입 보장)

FAISS 인덱스 (data/indexes/)  →  변경 없음 (파일 그대로 유지)
```

### 마이그레이션 스크립트 위치

```
scripts/
└── migrate_sqlite_to_postgres.py
```

**실행 방법**:
```bash
# 기존 SQLite 데이터가 있을 때만 실행
python scripts/migrate_sqlite_to_postgres.py
```

**멱등성**: 이미 존재하는 레코드(동일 id)는 skip 처리하여 중복 실행에 안전.
