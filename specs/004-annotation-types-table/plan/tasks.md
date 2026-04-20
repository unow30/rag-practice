# Tasks: chunks.annotation_types 정규화 - 별도 테이블 분리

**Feature**: annotation-types-table  
**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](plan.md)  
**Created**: 2026-04-20  
**Total Tasks**: 10

---

## 의존성 그래프

```
Phase 1 (ORM 모델)
  └── Phase 2 (DB 마이그레이션) ← 모든 이후 Phase의 전제 조건
        ├── Phase 3 (인덱서 수정)
        └── Phase 4 (리트리버 수정)
              └── Phase 5 (검증 및 마무리)
```

---

## Phase 1: Foundational — ORM 모델 변경

> `DocumentAnnotationType` 모델 신규 도입 및 `Chunk`에서 컬럼 제거.

- [x] T-01 `backend/models/document.py`에 `DocumentAnnotationType` 클래스 추가: `__tablename__ = "document_annotation_types"`, `id` PK (UUID v4), `document_id` FK → `documents.id` (UNIQUE, ondelete="CASCADE"), `annotation_types` JSONB nullable, `document` relationship(back_populates="annotation_info")
- [x] T-02 `backend/models/document.py`의 `Document` 클래스에 `annotation_info = relationship("DocumentAnnotationType", back_populates="document", uselist=False, cascade="all, delete-orphan")` 추가
- [x] T-03 `backend/models/document.py`의 `Chunk` 클래스에서 `annotation_types = Column(JSONB, nullable=True)` 라인 제거 및 `Chunk.to_metadata()`가 `self.document.annotation_info.annotation_types`를 참조하도록 수정 (연관 엔티티 없을 시 `{}` fallback)

---

## Phase 2: Foundational — DB 마이그레이션

> T-01 ~ T-03 완료 후 실행. 기존 데이터 이전 및 컬럼 삭제.

- [x] T-04 `backend/models/database.py`의 `init_db()`에 `DocumentAnnotationType` import 추가 후, `Base.metadata.create_all()` 이후 블록에 마이그레이션 SQL 추가: (a) `information_schema.columns`로 `chunks.annotation_types` 컬럼 존재 여부 확인, (b) 존재 시 JSONB 타입 캐스팅 + 두 가지 분기로 데이터 이전 — object 형태는 `jsonb_each` + `jsonb_object_agg`, array 형태는 CTE + `LATERAL jsonb_array_elements_text`로 key→true 객체 변환 (기존 데이터 호환), `ON CONFLICT (document_id) DO NOTHING`, (c) `ALTER TABLE chunks DROP COLUMN annotation_types` 실행, (d) `conn.commit()`

---

## Phase 3: 인덱서 수정

> 청크 저장 시 `annotation_types` 제거 및 문서 단위 upsert.

- [x] T-05 `backend/services/indexer.py`의 import에 `DocumentAnnotationType` 추가
- [x] T-06 `backend/services/indexer.py`의 `process_document()` 청크 루프에서: (a) 로컬 `merged_annotations: dict` 누적 변수 도입, (b) 각 청크의 `meta.get("annotations")`를 `merged_annotations.update()`로 병합, (c) `Chunk(...)` 생성 시 `annotation_types` 파라미터 제거, (d) 루프 종료 후 `DocumentAnnotationType`을 조회하여 존재 시 update, 없으면 새 레코드 추가 (upsert)

---

## Phase 4: 리트리버 수정

> 중복 조회 제거, `to_metadata()`에 위임.

- [x] T-07 `backend/services/retriever.py`의 `_build_langchain_docs()`에서 `chunk.annotation_types` 직접 참조 코드(`annotations = chunk.annotation_types or {}` 이하 3줄) 제거 — `chunk.to_metadata()`가 이미 `annotations`, `annotation_types`를 반환함

---

## Phase 5: 검증 및 마무리

- [x] T-08 앱 실행 또는 `init_db()` 호출하여 로컬 PostgreSQL에 마이그레이션 적용: `docker compose up -d postgres` 후 백엔드 기동 → 로그에서 `[DB] Connected to PostgreSQL` 확인
- [x] T-09 DB 검증: `psql -h localhost -p 5434 -U rag-practice -d rag-practice -c "\d chunks"`로 `annotation_types` 컬럼 제거 확인, `SELECT * FROM document_annotation_types LIMIT 5;`로 데이터 이전 결과 확인
- [x] T-10 `specs/004-annotation-types-table/plan/tasks.md`의 완료된 태스크를 `[x]`로 표시 (Constitution P-07 준수)

---

## 병렬 실행 예시

| 병렬 그룹 | 태스크 | 조건 |
|-----------|--------|------|
| 없음 | — | 모든 태스크가 순차 의존 |

---

## MVP 범위

Phase 1 + Phase 2 (T-01 ~ T-04) 만으로 데이터 이전 및 스키마 정규화 완료.  
Phase 3 + Phase 4 (T-05 ~ T-07)은 서비스 코드 호환성 유지를 위해 필수.  
Phase 5는 실운영 검증 단계.
