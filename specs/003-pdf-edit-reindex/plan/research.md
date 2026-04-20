# Research: 업로드 PDF 편집 반영 및 재처리

**Feature**: pdf-edit-reindex  
**Created**: 2026-04-20

---

## 1. PDF 주석 추출 — PyMuPDF annots() API

**Decision**: PyMuPDF(fitz) `page.annots()` 사용, 별도 라이브러리 추가 없음  
**Rationale**: 프로젝트가 이미 `fitz`(PyMuPDF)를 사용 중이며, `annots()` API가 ISO 32000 표준 주석 유형을 모두 지원한다. `pymupdf4llm`은 내부적으로 fitz를 래핑하므로 동일 방식으로 접근 가능.

| 주석 유형 | fitz annot.type[0] | 처리 방식 |
|-----------|-------------------|-----------|
| Text (메모 팝업) | 0 | `annot.info["content"]`에서 메모 텍스트 추출 |
| FreeText (인라인 메모) | 2 | `annot.info["content"]`에서 텍스트 추출 |
| Highlight | 8 | `page.get_text("text", clip=annot.rect)`로 해당 구간 텍스트 추출 |
| Underline | 9 | `page.get_text("text", clip=annot.rect)`로 해당 구간 텍스트 추출 |
| StrikeOut | 11 | `page.get_text("text", clip=annot.rect)`로 해당 구간 텍스트 추출 |

**Alternatives considered**:
- pdfplumber: 주석 API 미지원
- pypdf: 주석 접근 가능하나 텍스트 구간 추출이 불편

---

## 2. 주석 메타데이터 저장 방식

**Decision**: `Chunk` 테이블에 `annotation_types`(TEXT, JSON 직렬화 배열)와 `memo_content`(TEXT) 컬럼 추가. PostgreSQL JSON 타입 대신 TEXT로 저장하고 Python에서 직렬화/역직렬화.  
**Rationale**: 현재 모델이 SQLAlchemy Core 타입만 사용하며, JSON 타입을 추가하면 DB 의존성이 높아진다. TEXT로 저장하면 SQLite 호환성도 유지되고 구현이 단순하다.  
**How to apply**: `json.dumps(["highlight", "underline"])` 저장, `json.loads()` 읽기. `to_metadata()`에서 파싱하여 list 반환.

---

## 3. 재처리 시 기존 데이터 삭제 순서

**Decision**: Chunk DB 레코드 삭제 → FAISS 인덱스 파일 삭제 → BM25 인덱스 파일 삭제 → `process_document()` 재실행  
**Rationale**: `Document`에 `cascade="all, delete-orphan"` 설정이 있으나, 재처리는 Document를 삭제하지 않으므로 Chunk를 직접 쿼리로 삭제한다. FAISS와 BM25는 파일 기반이므로 `shutil.rmtree` + `delete_bm25_index()`로 제거.

---

## 4. 재처리 중 중복 요청 방지

**Decision**: 문서 상태(status)가 EXTRACTING·CHUNKING·EMBEDDING인 경우 409 Conflict 반환  
**Rationale**: 기존 `_processing_semaphore`(threading.Semaphore(1))는 전역 동시성 제어용이므로, 문서별 중복 방지는 status 필드로 판단하는 것이 간결하다.

---

## 5. 주석 정보와 RAG 컨텍스트 연동 방식

**Decision**: 메모 내용(`memo_content`)은 해당 청크 컨텍스트에 `[메모: {내용}]` 형태로 포함. `annotation_types`는 메타데이터로만 전달하여 LLM이 주석 유형을 인식할 수 있도록 함.  
**Rationale**: 메모는 사용자가 직접 작성한 의미 있는 텍스트이므로 검색 대상에 포함해야 한다. 강조 유형(하이라이트 등)은 검색 우선순위 힌트로 활용.

---

## 6. Constitution 적합성 검토

| 원칙 | 상태 | 비고 |
|------|------|------|
| P-01 근거 우선 | ✅ | 주석 파싱은 문서 내 정보 추출이므로 적합 |
| P-02 단계적 고도화 | ✅ | 기존 파이프라인 재활용, 최소 변경 |
| P-03 출처 투명성 | ✅ | `annotation_types` 메타데이터로 출처 표시 강화 |
| P-04 환경변수 전환 | ✅ | `EXTRACTOR` 환경변수 분기에서 두 추출기 모두 주석 파싱 적용 |
| P-06 브랜치 네이밍 | ✅ | `003-pdf-edit-reindex/T-XX-slug` 형식 준수 |
| P-07 Task 완성 상태 | ✅ | tasks.md 체크박스 `[x]` 규칙 준수 |
