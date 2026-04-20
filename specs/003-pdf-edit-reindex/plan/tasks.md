# Tasks: 업로드 PDF 편집 반영 및 재처리

**Feature**: pdf-edit-reindex  
**Spec**: [spec.md](../spec.md) | **Plan**: [plan.md](plan.md)  
**Created**: 2026-04-20  
**Total Tasks**: 19

---

## 의존성 그래프

```
Phase 1 (DB 스키마 변경)
  └── Phase 2 (Alembic 마이그레이션) ← 모든 Phase의 전제 조건
        ├── Phase 3 (US1: 주석 파싱)
        │     └── Phase 5 (US3: 프론트엔드) — US1 완료 후 주석 표시 가능
        ├── Phase 4 (US2: 재처리 API)
        │     └── Phase 5 (US3: 프론트엔드) — US2 완료 후 버튼 연결 가능
        └── Phase 6 (Polish: 검색 연동) ← US1 완료 후 진행
```

---

## Phase 1: Foundational — DB 스키마

> `Chunk` 모델 확장. 이후 모든 Phase가 이 변경에 의존한다.

- [x] T001 `backend/models/document.py`의 `Chunk` 클래스에 `annotation_types = Column(Text, nullable=True)` 와 `memo_content = Column(Text, nullable=True)` 컬럼 추가
- [x] T002 `backend/models/document.py`의 `Chunk.to_metadata()`에서 `"annotation_types": json.loads(self.annotation_types) if self.annotation_types else []` 와 `"memo_content": self.memo_content` 를 반환 딕셔너리에 추가 (`import json` 포함)

---

## Phase 2: Foundational — DB 마이그레이션

> T001·T002 완료 후 실행. PostgreSQL `chunks` 테이블에 신규 컬럼을 실제로 추가한다.

- [x] T003 `scripts/` 디렉터리에 `add_annotation_columns.py` 마이그레이션 스크립트 작성: `ALTER TABLE chunks ADD COLUMN IF NOT EXISTS annotation_types TEXT; ALTER TABLE chunks ADD COLUMN IF NOT EXISTS memo_content TEXT;` 실행 후 성공 메시지 출력 (기존 `scripts/migrate_sqlite_to_postgres.py` 패턴 참고)

---

## Phase 3: User Story 1 — 주석 파싱 (신규 업로드 자동 적용)

> **목표**: PDF 업로드 시 4종 주석(하이라이트·밑줄·취소선·메모)을 자동 감지하여 Chunk 메타데이터에 저장  
> **독립 검증**: 주석 포함 샘플 PDF 업로드 후 `SELECT annotation_types, memo_content FROM chunks WHERE document_id = '...'` 로 값 확인

- [x] T004 [US1] `backend/services/extractor.py`에 모듈 수준 함수 `_extract_annotations(page) -> dict` 추가: `page.annots()`로 type 0(Text)·2(FreeText)·8(Highlight)·9(Underline)·11(StrikeOut) 순회 → `{"annotation_types": [...], "memo_content": "..."}` 반환 (fitz 미설치 환경에서도 import 오류 없도록 함수 내부에서 fitz 사용)
- [x] T005 [P] [US1] `backend/services/extractor.py`의 `PyMuPDFExtractor.extract()` 내 페이지 루프에서 `_extract_annotations(page)` 를 호출하고 결과를 `Document.metadata` 에 `annotation_types`, `memo_content` 키로 병합
- [x] T006 [P] [US1] `backend/services/extractor.py`의 `PyMuPDF4LLMExtractor.extract()` 내 페이지 루프에서 `_extract_annotations(page)` 호출을 위해 `fitz.open(file_path)[page_num]` 으로 페이지 객체를 얻어 주석을 추출하고 `Document.metadata` 에 병합
- [x] T007 [US1] `backend/services/indexer.py`의 `process_document()` 내 `Chunk` 생성 루프에서 `meta.get("annotation_types")` 와 `meta.get("memo_content")` 를 읽어 `json.dumps()` 직렬화 후 `Chunk` 레코드의 해당 컬럼에 저장 (`import json` 추가)

---

## Phase 4: User Story 2 — 재처리 API

> **목표**: 기존 문서 ID 유지 채 파이프라인 재실행 API 제공 (계약: [contracts/reindex-api.md](../contracts/reindex-api.md))  
> **독립 검증**: `curl -X POST http://localhost:8000/api/documents/{doc_id}/reindex` → 202 확인 → `GET /api/documents/{doc_id}/status` 폴링 → READY 확인

- [x] T008 [US2] `backend/services/indexer.py`에 `reprocess_document(doc_id: str, db: Session) -> None` 함수 추가: `db.query(Chunk).filter(Chunk.document_id == doc_id).delete()` → `shutil.rmtree(doc.index_path, ignore_errors=True)` → `delete_bm25_index(doc_id)` → `doc.index_path = None` → `db.commit()` → `process_document(doc_id, db)` 순서로 실행 (`import shutil` 추가)
- [x] T009 [US2] `backend/api/documents.py`에 `POST /{doc_id}/reindex` 엔드포인트 추가: 문서 존재 확인(404), 처리 중 상태(EXTRACTING·CHUNKING·EMBEDDING·PENDING) 확인 후 409 반환, 통과 시 `doc.status = DocumentStatus.PENDING; db.commit()` 후 `BackgroundTasks.add_task(_reprocess_document_background, doc_id)` 호출하여 202 반환
- [x] T010 [US2] `backend/api/documents.py`에 `_reprocess_document_background(doc_id: str)` 헬퍼 함수 추가: `_process_document_background` 와 동일한 패턴으로 `SessionLocal` 생성, `_processing_semaphore` 획득 후 `reprocess_document(doc_id, db)` 호출 (`from backend.services.indexer import reprocess_document` import 추가)

---

## Phase 5: User Story 3 — 프론트엔드 재처리 UI

> **목표**: 문서 목록에서 재처리 버튼 제공, 진행 상태 실시간 표시, 완료/실패 알림  
> **독립 검증**: Streamlit 앱에서 READY 문서의 "재처리" 버튼 클릭 → 상태 배지 변화 확인 → READY 복귀 후 성공 토스트 확인

- [x] T011 [US3] `frontend/app.py`에 `reindex_document(doc_id: str) -> int` 헬퍼 함수 추가: `requests.post(f"{API_BASE}/api/documents/{doc_id}/reindex", timeout=10)` 호출 후 `resp.status_code` 반환
- [x] T012 [US3] `frontend/app.py`의 문서 목록 렌더링 부분에서 각 문서에 "재처리" 버튼 추가: `doc["status"]` 가 `"READY"` 또는 `"FAILED"` 일 때만 `st.button("🔄 재처리", key=f"reindex_{doc['id']}")` 활성화, 그 외 상태에서는 `st.button(..., disabled=True)` 표시
- [x] T013 [US3] `frontend/app.py`에서 재처리 버튼 클릭 시 `reindex_document()` 호출: 응답 202면 `st.rerun()` 으로 상태 갱신 시작, 409면 `st.warning("이미 처리 중입니다.")`, 그 외 에러 코드는 `st.error("재처리 요청에 실패했습니다.")` 표시
- [x] T014 [US3] `frontend/app.py`에서 문서 상태가 EXTRACTING·CHUNKING·EMBEDDING 인 경우 처리 상태를 `time.sleep(2); st.rerun()` 루프로 자동 폴링하여 진행 상태 배지를 실시간 갱신하고, READY/FAILED 도달 시 `st.success` / `st.error` 알림 표시 (기존 `poll_status()`, `status_badge()` 함수 재활용)

---

## Phase 6: Polish — 검색 연동 및 안정성

> 주석 메타데이터가 RAG 답변에 실제로 반영되도록 retriever·pipeline 보완

- [x] T015 [P] `backend/services/retriever.py`의 `_build_langchain_docs()` 함수에서 `chunk.annotation_types` 와 `chunk.memo_content` 를 각각 `json.loads()` 후 `metadata["annotation_types"]`, `metadata["memo_content"]` 로 포함 (`import json` 추가, NULL 안전 처리 포함)
- [x] T016 [P] `backend/services/pipeline.py`의 `prepare_context()` 에서 컨텍스트 문자열 구성 시 청크의 `metadata.get("memo_content")` 가 있으면 본문 뒤에 `\n[메모: {memo_content}]` 를 추가하여 LLM이 메모 내용을 인식하도록 수정
- [x] T017 `backend/services/retriever.py`의 `_build_langchain_docs()` 에서 `chunk.annotation_types` 가 NULL 이거나 파싱 실패 시 `[]` 로 fallback 처리하는 방어 코드 추가 (기존 업로드 문서 하위 호환성 보장)
- [x] T018 `scripts/add_annotation_columns.py` 를 실행하여 실제 로컬 PostgreSQL DB에 마이그레이션 적용 및 결과 확인: `psql -h localhost -p 5434 -U postgres -d rag-practice -c "\d chunks"` 로 신규 컬럼 존재 확인
- [x] T019 `specs/003-pdf-edit-reindex/tasks.md` 의 완료된 태스크를 `[x]` 로 표시 (CLAUDE.md P-07 규칙 준수)

---

## 병렬 실행 예시

| 병렬 그룹 | 태스크 | 조건 |
|-----------|--------|------|
| Phase 3 내 | T005, T006 | 각자 다른 Extractor 클래스 수정 |
| Phase 6 내 | T015, T016 | retriever.py, pipeline.py 독립 수정 |

---

## MVP 범위 제안

**Phase 1 + Phase 2 + Phase 3 + Phase 4** (T001 ~ T010)  
→ 업로드 시 주석 파싱·저장 + API 재처리 가능한 상태.  
프론트엔드(Phase 5) 없이 curl로 전 기능 검증 가능.  
Phase 6는 검색 품질 향상이므로 MVP 이후 적용.
