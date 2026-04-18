# Tasks: 로컬 PostgreSQL 데이터베이스 마이그레이션

**Feature**: specs/002-postgres-local-db  
**Branch prefix**: `002-postgres-local-db/`  
**Created**: 2026-04-18  
**Total Tasks**: 15  
**User Stories**: 4

---

## User Story 매핑

| ID | 시나리오 | 성공 기준 |
|----|----------|-----------|
| US1 | 마이그레이션 후 문서 업로드 및 처리 | PostgreSQL에 Document·Chunk 저장, 30초 이내 READY |
| US2 | 마이그레이션 후 질의응답 | FAISS→PostgreSQL 청크 조회 정상, 첫 토큰 3초 이내 |
| US3 | 기존 SQLite 데이터 이전 | 레코드 수 100% 일치, 멱등성 보장 |
| US4 | 데이터베이스 연결 실패 처리 | 연결 실패 시 명확한 오류 메시지 출력 후 종료 |

---

## Phase 1: Setup

> PostgreSQL 실행 환경 및 Python 드라이버 준비.

- [x] T001 docker-compose.yml 생성 — PostgreSQL 15 서비스 정의 (포트 5434, DB/유저/비밀번호: rag-practice)
- [x] T002 [P] requirements.txt에 `psycopg2-binary>=2.9` 추가

---

## Phase 2: Foundational — DB 연결 레이어 교체

> 모든 User Story의 전제 조건. 이 Phase 완료 전까지 US1~US4 진행 불가.

- [x] T003 backend/models/database.py — `DB_PATH`/`sqlite:///` 제거, `DATABASE_URL` 환경변수 읽기로 교체, `connect_args={"check_same_thread": False}` 제거, `pool_pre_ping=True` 추가
- [x] T004 [P] .env — `DB_PATH=./data/rag.db` 줄을 `DATABASE_URL=postgresql://rag-practice:rag-practice@localhost:5434/rag-practice`로 교체
- [x] T005 [P] .env.example — `DB_PATH` 줄을 `DATABASE_URL=postgresql://user:password@localhost:5434/dbname` (주석 포함)으로 교체

---

## Phase 3: US1 — 문서 업로드 및 처리 (PostgreSQL 저장)

> **목표**: PDF 업로드 → Document/Chunk 레코드가 PostgreSQL에 저장되고, 문서가 READY 상태로 전환된다.  
> **독립 검증**: `docker compose exec postgres psql -U rag-practice -d rag-practice -c "SELECT status, COUNT(*) FROM documents GROUP BY status;"` 실행 시 결과 반환.

- [x] T006 [US1] backend/models/document.py — `Column(DateTime, ...)` → `Column(DateTime(timezone=True), ...)` 로 `uploaded_at`, `processed_at`, `created_at` 3개 필드 업데이트
- [x] T007 [US1] backend/models/database.py — `init_db()` 함수에 PostgreSQL 연결 성공 로그 추가 (`[DB] Connected to PostgreSQL: {host}:{port}/{dbname}`)
- [x] T008 [P] [US1] backend/main.py — 앱 시작 시 `@app.on_event("startup")`에서 `init_db()` 호출 확인 및 연결 실패 시 앱 종료(`sys.exit(1)`) 처리, `/health` 응답에 DB 정보 포함

---

## Phase 4: US2 — 질의응답 CRUD 호환성

> **목표**: FAISS 검색으로 얻은 chunk_id로 PostgreSQL에서 청크 내용을 조회하고 답변을 생성한다.  
> **독립 검증**: 문서 업로드 후 `/api/chat` 질의 요청 시 `sources` 필드에 chunk 내용이 포함된 응답 반환.

- [x] T009 [US2] backend/api/documents.py — 문서 목록 조회·삭제 엔드포인트가 PostgreSQL 세션으로 정상 동작하는지 확인 (SQLite 특화 쿼리 패턴 없음 — 변경 불필요)
- [x] T010 [P] [US2] backend/api/chat.py & retriever.py — FAISS index_id → chunk_id → PostgreSQL Chunk 조회 경로 확인 (표준 SQLAlchemy 패턴 사용 — 변경 불필요)

---

## Phase 5: US3 — SQLite 데이터 마이그레이션 스크립트

> **목표**: 기존 `data/rag.db`의 Document·Chunk 레코드를 PostgreSQL로 이전한다.  
> **독립 검증**: 스크립트 실행 후 `[RESULT] Documents: SQLite=N, PostgreSQL=N ✓` 출력.

- [x] T011 [US3] scripts/migrate_sqlite_to_postgres.py 신규 생성:
  - `sqlite3`로 `data/rag.db` 읽기 (환경변수 `DB_PATH` 또는 기본값 `./data/rag.db`)
  - SQLAlchemy PostgreSQL 세션으로 Document 전체 삽입 (id 중복 시 skip — 멱등성 보장)
  - Document 삽입 완료 후 Chunk 전체 삽입 (FK 의존성 보장)
  - 완료 후 SQLite ↔ PostgreSQL 레코드 수 비교 출력 및 불일치 시 경고
  - FAISS 인덱스 파일은 건드리지 않음

---

## Phase 6: US4 — 연결 실패 처리

> **목표**: PostgreSQL 연결 불가 시 사용자가 원인을 즉시 파악할 수 있는 명확한 오류 메시지를 출력하고 앱이 안전하게 종료된다.  
> **독립 검증**: 잘못된 `DATABASE_URL`로 앱 기동 시 `[ERROR] Cannot connect to PostgreSQL: ...` 메시지가 stderr에 출력되고 프로세스가 non-zero exit code로 종료.

- [x] T012 [US4] backend/models/database.py — `init_db()`에 `OperationalError` 캐치 후 연결 정보(호스트, 포트, DB명) 포함 오류 메시지 출력, `sys.exit(1)` 호출 (T003과 통합 완료)

---

## Phase 7: Polish

> 문서화 및 마무리.

- [x] T013 [P] README.md — PostgreSQL 로컬 설정 섹션 추가 (`docker compose up -d`, `.env` 설정, 마이그레이션 스크립트 실행 순서)
- [x] T014 [P] specs/002-postgres-local-db/plan/tasks.md — 모든 완료 태스크 [x]로 업데이트
- [ ] T015 git 커밋 — "feat: SQLite → PostgreSQL 마이그레이션 (specs/002-postgres-local-db)" 메시지로 변경 사항 커밋

---

## 의존성 그래프

```
T001, T002 (Setup)
    ↓
T003, T004, T005 (Foundational — 병렬 가능)
    ↓
┌───────────────────────────────┐
│ T006, T007, T008 (US1)       │  ← T004 완료 후 시작
│ T009, T010 (US2)              │  ← T003 완료 후 시작 (US1과 병렬 가능)
│ T011 (US3)                    │  ← T003, T004 완료 후 시작
│ T012 (US4)                    │  ← T003 완료 후 시작
└───────────────────────────────┘
    ↓
T013, T014, T015 (Polish)
```

---

## 병렬 실행 전략

### Setup 완료 후 동시 실행 가능한 태스크 묶음

```
묶음 A (Phase 2 내):
  - T004: .env 수정
  - T005: .env.example 수정
  - T002: requirements.txt 수정

묶음 B (Phase 3~6 내):
  - T006, T007, T008: US1 (models 먼저, main.py는 T006 완료 후)
  - T009, T010: US2 (T003 완료 후)
  - T011: US3 (T003, T004 완료 후)
  - T012: US4 (T003 완료 후)
```

---

## MVP 범위 제안

**US1 + US2 (T001~T010)** 만으로 핵심 기능 동작 검증 가능.  
US3(마이그레이션)과 US4(에러 핸들링)은 기존 데이터가 있거나 안정화 단계에서 추가.

---

## 완료 기준

- [ ] `docker compose up -d postgres` 후 앱 기동 시 PostgreSQL 연결 성공 로그 출력
- [ ] PDF 업로드 → PostgreSQL `documents`/`chunks` 테이블에 레코드 생성 확인
- [ ] 질의응답 E2E 동작 — 첫 토큰 3초 이내
- [ ] `python scripts/migrate_sqlite_to_postgres.py` 실행 시 레코드 수 일치 출력
- [ ] 잘못된 DATABASE_URL로 기동 시 명확한 오류 메시지 및 non-zero exit
