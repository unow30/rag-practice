# Research: 로컬 PostgreSQL 데이터베이스 마이그레이션

**Feature**: specs/002-postgres-local-db  
**Created**: 2026-04-18  
**Status**: Complete

---

## 1. SQLAlchemy PostgreSQL 드라이버 선택

### Decision: `psycopg2-binary`

**Rationale**:
- SQLAlchemy 2.0의 동기 세션(sync `SessionLocal`)은 `psycopg2`를 기본 드라이버로 사용.
- `psycopg2-binary`는 사전 컴파일된 바이너리 패키지로, 별도의 C 컴파일 없이 설치 가능.
- 기존 코드베이스가 동기 SQLAlchemy(ORM 모델, `SessionLocal`)로 작성되어 있으므로 `asyncpg`(비동기 전용)로 전환하면 전체 서비스 레이어를 재작성해야 하는 위험이 있음.

**Alternatives considered**:
- `psycopg2`: 소스 컴파일 필요, 로컬 개발 환경에서 불필요한 복잡도.
- `asyncpg`: FastAPI의 비동기 패턴과 궁합이 좋으나, 현재 ORM 코드가 동기 방식이므로 별도 마이그레이션 범위가 필요.
- `psycopg3` (`psycopg`): 안정성 검증 중, 프로덕션 전환 시 재평가.

**DATABASE_URL 형식**:
```
postgresql://rag-practice:rag-practice@localhost:5434/rag-practice
```

---

## 2. SQLite → PostgreSQL 스키마 차이점

### Decision: 최소 변경으로 호환성 유지

**주요 차이 및 처리 방안**:

| 항목 | SQLite | PostgreSQL | 처리 방안 |
|------|--------|-----------|----------|
| `connect_args={"check_same_thread": False}` | 필요 | 불필요 | 제거 |
| ENUM 타입 | SQLAlchemy String ENUM | 네이티브 ENUM (PostgreSQL) | `create_constraint=False` 또는 그대로 유지 |
| UUID 컬럼 | `String(36)` | `String(36)` 또는 `UUID` 네이티브 | 현재 `String(36)` 그대로 유지 (안전) |
| AUTOINCREMENT | 자동 | `SERIAL` / `IDENTITY` | SQLAlchemy가 자동 처리 |
| 타임존 DATETIME | naive datetime | `TIMESTAMP WITH TIME ZONE` 권장 | `DateTime(timezone=True)` 으로 업데이트 |
| Connection Pooling | 없음 (파일 기반) | `QueuePool` (기본) | SQLAlchemy 기본값 사용 |

**Rationale**:
- 대부분 SQLAlchemy가 추상화하므로 모델 코드 변경 최소화.
- UUID를 `String(36)`으로 유지하면 기존 코드·데이터 호환성 보장.
- ENUM은 PostgreSQL 네이티브 ENUM을 생성하게 되므로, `create_type=True` (기본값) 유지.

---

## 3. SQLite 데이터 마이그레이션 전략

### Decision: Python 스크립트 기반 일회성 마이그레이션

**Rationale**:
- Alembic 같은 마이그레이션 도구는 스키마 버전 관리에 적합하지만, 이번 작업은 데이터베이스 자체를 교체하는 일회성 마이그레이션.
- Python 스크립트(SQLite 읽기 → PostgreSQL 쓰기)가 가장 단순하고 제어하기 쉬움.
- `sqlite3` 내장 모듈로 SQLite 직접 읽고, SQLAlchemy PostgreSQL 세션으로 삽입.

**마이그레이션 순서**:
1. PostgreSQL 스키마 생성 (`init_db()`)
2. SQLite `documents` 테이블 전체 읽기
3. PostgreSQL `documents` 삽입 (batch insert)
4. SQLite `chunks` 테이블 전체 읽기
5. PostgreSQL `chunks` 삽입 (batch insert, document FK 의존성 고려)
6. 레코드 수 검증 (SQLite 수 = PostgreSQL 수)

**멱등성 보장**: `INSERT ... ON CONFLICT DO NOTHING` 또는 삽입 전 존재 여부 확인.

---

## 4. 환경변수 구조 변경

### Decision: `DB_PATH` 제거 → `DATABASE_URL` 단일 변수

**Rationale**:
- 현재 `.env`의 `DB_PATH=./data/rag.db`는 SQLite 전용 경로 방식.
- PostgreSQL은 표준 connection string(`DATABASE_URL`)을 사용.
- `DATABASE_URL`은 다양한 DB 드라이버와 호환되는 업계 표준 환경변수명.
- P-04(환경변수 기반 전환) 원칙에 따라 환경변수만 바꾸면 DB를 교체할 수 있어야 함.

**변경**:
```bash
# 이전
DB_PATH=./data/rag.db

# 이후
DATABASE_URL=postgresql://rag-practice:rag-practice@localhost:5434/rag-practice
```

---

## 5. Connection Pooling 설정

### Decision: SQLAlchemy 기본 QueuePool + pool_pre_ping=True

**Rationale**:
- 단일 사용자 앱이므로 pool_size=5, max_overflow=10 기본값으로 충분.
- `pool_pre_ping=True`: 연결 유효성을 요청 전 확인하여 "stale connection" 오류 방지.
- SQLite의 `check_same_thread=False`는 제거하고 PostgreSQL 기본 풀링 사용.

```python
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)
```

---

## 6. 헌법 P-04 준수 검토

**P-04: 환경변수 기반 전환** — 코드 변경 없이 파이프라인 구성 변경 가능.

현재 P-04는 추출기/검색기/Multi-query/Reranker에 적용되어 있음. DB 연결 역시 동일 원칙 적용:
- `DATABASE_URL` 환경변수만 변경하면 SQLite ↔ PostgreSQL 전환 가능.
- `database.py`에서 `DB_PATH` 하드코딩 의존성 제거.

**헌법 3절 기술 스택 제약 업데이트 필요**:
- 현재: `데이터베이스: SQLite (SQLAlchemy)`
- 변경: `데이터베이스: PostgreSQL (SQLAlchemy) — 로컬 개발 기준`
- → 헌법 개정 필요 (MINOR 버전 업, P-06 아닌 기술 스택 변경이므로 별도 처리)

---

## 7. 기존 FAISS 인덱스 영향 분석

### Decision: 영향 없음 — 변경 불필요

**Rationale**:
- FAISS 인덱스(`data/indexes/{document_id}/index.faiss`, `index.pkl`)는 파일시스템 기반.
- PostgreSQL 마이그레이션 후에도 `document.index_path` 컬럼이 동일 경로를 참조.
- 마이그레이션 스크립트에서 `index_path` 값을 그대로 복사하면 정합성 유지.

---

## 8. 프로젝트 구조 변경 사항

변경되는 파일 목록:

| 파일 | 변경 내용 |
|------|-----------|
| `backend/models/database.py` | `DB_PATH`/`sqlite:///` → `DATABASE_URL`/`postgresql://`, `connect_args` 제거, `pool_pre_ping=True` 추가 |
| `.env` | `DB_PATH` → `DATABASE_URL` |
| `.env.example` | PostgreSQL 연결 변수 문서화 |
| `requirements.txt` | `psycopg2-binary` 추가 |
| `scripts/migrate_sqlite_to_postgres.py` | SQLite → PostgreSQL 마이그레이션 스크립트 (신규) |
| `specs/002-postgres-local-db/plan/quickstart.md` | PostgreSQL 로컬 설정 가이드 |
| `.specify/memory/constitution.md` | 3절 기술 스택 제약 업데이트 |
