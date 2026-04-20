# Implementation Plan: chunks.annotation_types 정규화 - 별도 테이블 분리

**Feature**: annotation-types-table  
**Spec**: [spec.md](../spec.md)  
**Created**: 2026-04-20

---

## Technical Context

### 기술 스택 (Constitution §3 준수)

| 계층 | 선택 |
|------|------|
| 런타임 | Python ≥ 3.13 (uv 관리) |
| 백엔드 | FastAPI ≥ 0.100 |
| DB | PostgreSQL 15, SQLAlchemy 2.x, JSONB |
| ORM | SQLAlchemy DeclarativeBase (기존 `backend/models/database.py` 재활용) |
| 마이그레이션 | 기존 방식(Alembic 미사용): `init_db()` 내부 ALTER/INSERT SQL 삽입 |

### 신규 의존성

없음 — 기존 `sqlalchemy`, `psycopg2` 패키지만으로 구현 가능.

---

## 구현 전략

### 핵심 원칙

- **최소 침습**: `chunks`에서 `annotation_types` 컬럼만 제거. 나머지 컬럼(`memo_content` 등)은 현 위치 유지.
- **문서 단위 1:1 테이블**: `document_annotation_types`가 `documents.id`에 `UNIQUE FK` → CASCADE DELETE로 생명주기 일치.
- **기존 데이터 보존**: `init_db()`가 멱등성 있게 데이터 이전 → 컬럼 삭제를 수행.
- **API 응답 불변**: `Chunk.to_metadata()`의 `annotations`, `annotation_types` 필드 계약 유지.

### 데이터 흐름

```
[신규/재업로드 처리]
  process_document()
    └── 청크별 metadata["annotations"] 수집 → merged dict
          └── document_annotation_types upsert (document_id UNIQUE)

[검색 시]
  _build_langchain_docs()
    └── chunk.to_metadata()
          └── chunk.document.annotation_info.annotation_types (lazy load)
                → metadata["annotations"], metadata["annotation_types"]

[삭제 시]
  Document DELETE
    └── ON DELETE CASCADE → document_annotation_types 자동 삭제
```

### 마이그레이션 흐름

```
init_db()
  1. Base.metadata.create_all() → document_annotation_types 테이블 생성
  2. information_schema 확인: chunks.annotation_types 컬럼 존재 여부
  3. 존재 시:
       a. JSONB 타입 캐스팅 (이전 TEXT 호환)
       b. jsonb_each + jsonb_object_agg → 문서 단위 합산하여 INSERT
          (ON CONFLICT DO NOTHING으로 재실행 안전)
       c. ALTER TABLE chunks DROP COLUMN annotation_types
  4. commit
```

---

## 파일별 변경 목록

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `backend/models/document.py` | 수정 | `Chunk.annotation_types` 제거, `DocumentAnnotationType` 모델 추가, `Document.annotation_info` relationship 추가, `Chunk.to_metadata()` 수정 |
| `backend/models/database.py` | 수정 | `init_db()`에 데이터 이전 + 컬럼 삭제 SQL 추가 |
| `backend/services/indexer.py` | 수정 | 청크 저장 시 `annotation_types` 제거, 문서 단위 upsert 로직 추가 |
| `backend/services/retriever.py` | 수정 | `chunk.annotation_types` 직접 참조 제거 (`to_metadata()`가 일괄 처리) |

---

## Constitution 게이트 체크

| 게이트 | 결과 |
|--------|------|
| P-01 근거 우선 — 주석 데이터는 기존 동작 유지, 정규화만 수행 | ✅ PASS |
| P-02 단계적 고도화 — 기능 변경 없는 리팩터링 | ✅ PASS |
| P-03 출처 투명성 — API 응답 계약(`annotations`, `annotation_types`) 유지 | ✅ PASS |
| P-04 환경변수 전환 — 해당 없음 | N/A |
| P-05 측정 기반 — 평가 지표 영향 없음(동일 데이터) | ✅ PASS |
| P-06 브랜치 네이밍 — `004-annotation-types-table/T-XX-slug` 형식 준수 | ✅ 적용 예정 |
| P-07 Task 완성 표시 — tasks.md [x] 표시 규칙 준수 | ✅ 적용 예정 |
| 신규 외부 의존성 없음 | ✅ PASS |

---

## 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 기존 데이터 이전 실패 | `ON CONFLICT DO NOTHING` + information_schema 선제 확인으로 멱등성 보장 |
| 청크별 서로 다른 annotation → 문서 단위 합산 시 손실 | 현 데이터 구조상 문서 내 주석 유형은 중복 저장되므로 합산이 정당함 (spec Assumptions 참고) |
| Lazy load N+1 | `_build_langchain_docs()`에서 `selectinload(Chunk.document).selectinload(Document.annotation_info)` 적용 검토 |
