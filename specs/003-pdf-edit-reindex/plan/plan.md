# Implementation Plan: 업로드 PDF 편집 반영 및 재처리

**Feature**: pdf-edit-reindex  
**Spec**: [spec.md](../spec.md)  
**Created**: 2026-04-20

---

## Technical Context

### 기술 스택 (Constitution §3 준수)

| 계층 | 선택 |
|------|------|
| 런타임 | Python ≥ 3.13 (uv 관리) |
| 백엔드 | FastAPI ≥ 0.100 |
| 프론트엔드 | Streamlit ≥ 1.30 |
| DB | PostgreSQL + SQLAlchemy (Alembic 마이그레이션) |
| PDF 파싱 | PyMuPDF(fitz) — 기존 라이브러리 재활용 |
| 임베딩 | BGE-M3, FAISS IndexFlatIP |

### 신규 의존성
없음 — PyMuPDF `page.annots()` API는 기존 fitz 패키지에 포함.

---

## 구현 전략

### 핵심 원칙
- 기존 `process_document()` 파이프라인을 최대한 재활용한다.
- `Chunk` 모델에 컬럼 2개만 추가하여 변경 범위를 최소화한다.
- `annotation_types`는 TEXT 컬럼에 JSON 직렬화 방식으로 저장한다.

### 주석 추출 흐름

```
PDF 파일
  └── fitz.open() → page 순회
        ├── page.get_text() → 기존 텍스트 추출 (변경 없음)
        └── page.annots() → 주석 순회
              ├── type 0/2 (메모) → annot.info["content"] → memo_content
              └── type 8/9/11 (H/U/S) → page.get_text(clip=annot.rect) → annotation_types
```

### 재처리 흐름

```
POST /api/documents/{doc_id}/reindex
  └── 상태 검증 (처리 중이면 409)
        └── BackgroundTask: reprocess_document(doc_id)
              ├── Chunk 레코드 삭제 (CASCADE 없이 직접 DELETE)
              ├── FAISS 인덱스 파일 삭제 (shutil.rmtree)
              ├── BM25 인덱스 파일 삭제 (delete_bm25_index)
              └── process_document() 재실행
```

---

## 파일별 변경 목록

| 파일 | 변경 유형 | 내용 |
|------|-----------|------|
| `backend/models/document.py` | 수정 | `Chunk`에 `annotation_types`, `memo_content` 컬럼 추가 |
| `backend/services/extractor.py` | 수정 | `_extract_annotations()` 추가, 두 Extractor에 호출 |
| `backend/services/indexer.py` | 수정 | Chunk 저장 시 주석 필드 반영, `reprocess_document()` 추가 |
| `backend/api/documents.py` | 수정 | `POST /{doc_id}/reindex` 엔드포인트 추가 |
| `backend/services/retriever.py` | 수정 | `_build_langchain_docs()`에 주석 메타데이터 포함 |
| `backend/services/pipeline.py` | 수정 | 컨텍스트 문자열에 `memo_content` 포함 |
| `frontend/app.py` | 수정 | 재처리 버튼 및 상태 표시 추가 |
| `scripts/` (신규 또는 alembic) | 신규 | DB 마이그레이션 스크립트 |

---

## Constitution 게이트 체크

| 게이트 | 결과 |
|--------|------|
| P-01 근거 우선 — 주석은 문서 내 사용자 작성 정보 | ✅ PASS |
| P-02 단계적 고도화 — 기존 파이프라인 재활용 | ✅ PASS |
| P-04 환경변수 전환 — EXTRACTOR 분기 양쪽 모두 적용 | ✅ PASS |
| 신규 외부 의존성 없음 | ✅ PASS |
