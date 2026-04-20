<!--
SYNC IMPACT REPORT
==================
Version change  : 1.2.1 → 1.3.0
Modified        : 2026-04-20
Added sections  :
  - P-08 데이터 정규화 (Data Normalization) — specs/004-annotation-types-table 회고 반영
  - P-09 외부 파일 변경 처리 (External Mutation Handling) — specs/003-pdf-edit-reindex + feat/file-watcher-auto-detect 회고 반영
Changed sections:
  - P-06 브랜치 네이밍 — spec이 없는 일반 작업 브랜치 프리픽스(`feat/`, `fix/`, `refactor/`) 규칙 보완
  - 5절 거버넌스 — 규정 준수 검토 체크리스트에 P-08·P-09 항목 추가, 버전 이력 추가
Removed sections: N/A
Templates updated: N/A (`.specify/templates/` 디렉토리 미존재)
Follow-up TODOs : 없음
-->

# 프로젝트 헌법 (Project Constitution)

**Project**: PDF RAG 대화형 웹 앱 (`rag-practice`)
**Constitution Version**: 1.3.0
**Ratification Date**: 2026-04-18
**Last Amended Date**: 2026-04-20

---

## 1. Identity

이 프로젝트는 PDF 문서를 업로드하고 자연어로 질의응답할 수 있는 **RAG(Retrieval-Augmented Generation) 기반 대화형 웹 앱**이다.

- **사용자**: 단일 사용자 (인증 없음)
- **핵심 가치**: 근거 있는 답변 — 문서에 존재하는 내용만을 기반으로 답변한다
- **개발 전략**: v0 단순 베이스라인 → 평가 셋 측정 → 단계적 고도화

---

## 2. 설계 원칙 (Principles)

### P-01: 근거 우선 (Evidence-First)

시스템은 반드시 업로드된 문서 컨텍스트에 근거하여 답변해야 한다.
문서에 없는 내용은 추측하거나 생성하지 않는다.
문서에서 답변할 수 없는 경우 반드시 "문서에서 관련 정보를 찾을 수 없습니다."라고 명시한다.

**적용 범위**: LLM 시스템 프롬프트, generate_stream(), 평가 negative case 처리

**위반 감지 기준**: negative_case 질문에 대해 문서 내용과 무관한 답변 생성 시 P-01 위반.

---

### P-02: 단계적 고도화 (Phased Improvement)

복잡한 최적화보다 **동작하는 베이스라인 먼저** 구축한다.
각 단계 완료 후 평가 지표를 측정하고, 목표치 미달 시에만 다음 고도화 단계로 진행한다.

| 단계 | 진입 조건 |
|------|-----------|
| v0 → v0.5 | 베이스라인 동작 확인 |
| v0.5 → v1 | Recall@5 < 80% |
| v1 → v2 | 표현 불일치 카테고리 Recall 개선 필요 |
| v2 → v3 | Precision 추가 개선 필요 |

**적용 범위**: tasks.md 마일스톤, 검색·추출·재정렬 컴포넌트 도입 시점

---

### P-03: 출처 투명성 (Source Transparency)

모든 답변에는 출처(문서명, 페이지 번호, 인용 구절)를 함께 제공해야 한다.
복수 문서에서 답변을 구성한 경우 문서별로 구분하여 표시한다.

**적용 범위**: build_sources(), SSE `event: done` 페이로드, 프론트엔드 출처 expander

---

### P-04: 환경변수 기반 전환 (Env-Driven Switching)

핵심 컴포넌트(추출기, 검색기, Multi-query, Reranker)는 환경변수로 활성화/전환 가능해야 한다.
코드 변경 없이 파이프라인 구성을 바꿀 수 있어야 한다.

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `EXTRACTOR` | `pymupdf` | `pymupdf` / `pymupdf4llm` |
| `RETRIEVER` | `faiss` | `faiss` / `ensemble` |
| `MULTI_QUERY` | `false` | `true` / `false` |
| `RERANK_TOP_N` | `5` | Reranker 반환 청크 수 |

**적용 범위**: extractor.py `get_extractor()`, retriever.py, query_expander.py, reranker.py

---

### P-05: 측정 기반 개선 (Metrics-Driven)

기능 개선의 효과는 반드시 평가 지표로 검증한다.
임의적 감각 판단보다 수치 측정 결과를 우선한다.

**필수 지표**:

| 지표 | 목표 |
|------|------|
| Recall@5 | ≥ 80% |
| Answerable@5 | ≥ 80% |
| Exact Match | ≥ 60% |
| Partial Match | ≥ 85% |
| Latency (첫 토큰) | ≤ 3,000ms |

**적용 범위**: evaluation/run_eval.py, evaluation/eval_set.json, evaluation/BASELINE.md

---

### P-06: 브랜치 네이밍 규칙 (Branch Naming)

모든 작업 브랜치는 목적에 따라 아래 두 형식 중 하나를 따른다.

#### (A) Spec 기반 task 브랜치

```
{speckit-specify 폴더명}/{task-id}-{task-slug}
```

- **speckit-specify 폴더명**: `.specify/feature.json`의 `feature_directory`에서 `specs/` 제거
- **task-id**: tasks.md에 정의된 태스크 ID (예: `T-14`, `T-22`)
- **task-slug**: 태스크 내용을 2~4단어 kebab-case로 요약

**예시**: `001-pdf-rag-chat-webapp/T-17-bm25-indexer`, `004-annotation-types-table/T-01-normalize-annotation`

#### (B) Spec이 없는 일반 작업 브랜치

Spec 없이 진행하는 소규모 기능·버그 수정·리팩터링은 아래 프리픽스를 사용한다.

| 프리픽스 | 용도 | 예시 |
|----------|------|------|
| `feat/` | 신규 기능 추가 | `feat/open-pdf-native`, `feat/file-watcher-auto-detect` |
| `fix/` | 버그 수정 | `fix/bm25-loader-race` |
| `refactor/` | 리팩터링 | `refactor/pipeline-split` |
| `docs/` | 문서 변경 | `docs/readme-badges` |

- **slug**: 변경 내용을 2~4단어 kebab-case로 요약
- 일정 규모 이상(파일 5개↑ 또는 데이터 모델 변경 포함) 작업은 spec을 먼저 작성하고 (A) 형식을 사용한다.

**구분자**: 슬래시(`/`) — Git 네임스페이스 브랜치로 동작 (두 형식 공통)

**적용 범위**: 모든 feature/fix 브랜치 생성 시 (`/speckit-implement`, 수동 브랜치 포함)

---

### P-07: Task 완성 상태 표시 (Task Completion Tracking)

모든 tasks.md 파일의 체크박스는 완성 상태를 명확히 표시해야 한다.
미완료: `[ ]`, 완료: `[x]` 형식을 사용한다.

형식:
```markdown
- [ ] T-01 미완료 task
- [x] T-02 완료된 task
```

**적용 범위**: 모든 specs/*/tasks.md 파일

---

### P-08: 데이터 정규화 (Data Normalization)

RDB 스키마 설계 시 제1정규형(1NF)을 준수한다. 반복 그룹·배열·다중 값 JSONB 컬럼으로
**동일 의미의 데이터를 여러 행에 중복 저장**하거나, **배열 원소를 쿼리 대상**으로 삼지
않는다. 다대다 관계는 별도 관계 테이블로, 부모-자식 1:1/1:N 관계는 외래 키 + UNIQUE
제약으로 표현한다.

**예외 허용**: 순수 확장 메타데이터(키마다 이질적 의미를 가지며 WHERE 절 쿼리 대상이
아닌 경우)는 JSONB 사용 가능.

**위반 감지 기준**:
- 동일 스키마의 JSONB 값이 같은 부모를 가진 여러 행에 반복 저장되는 경우
- 배열/JSONB 컬럼의 원소를 WHERE/JOIN에서 직접 조회해야 하는 경우

**적용 범위**: `backend/models/*.py`, `init_db()` 마이그레이션 블록.

**회고 근거**: specs/004-annotation-types-table — `chunks.annotation_types` JSONB가
동일 문서의 모든 청크에 중복 저장되던 문제를 `document_annotation_types` 1:1 테이블로
분리하여 해소.

---

### P-09: 외부 파일 변경 처리 (External Mutation Handling)

업로드된 원본 파일(`data/documents/*`)에 대한 외부 수정은 **자동 감지하되 자동 재처리는
금지**한다. 재처리는 반드시 사용자의 명시적 요청(API 호출 또는 UI 버튼)으로만 실행한다.

**구성 요소**:
- **감지**: watchdog 파일 이벤트 + SHA-256 해시 비교로 실제 내용 변경만 필터링
- **표시**: `documents.file_changed` 플래그 + 프론트엔드 UI 배지
- **반영**: 사용자가 재처리 버튼을 눌러야 `reprocess_document()` 실행
- **ID 보존**: 재처리 시 문서 ID 및 연관 메타데이터(대화 기록 등) 유지

**근거**: 무의식적 자동 재처리는 LLM 비용 부담과 예상치 못한 인덱스 변경을 초래하며,
P-03(출처 투명성)에 따른 예측 가능성을 훼손한다.

**적용 범위**: `backend/services/file_watcher.py`, `backend/services/indexer.py`
(`reprocess_document`), 재처리 API 엔드포인트.

**회고 근거**: specs/003-pdf-edit-reindex, feat/file-watcher-auto-detect.

---

## 3. 기술 스택 제약 (Tech Constraints)

아래 항목은 프로젝트 생애 동안 핵심 스택으로 유지한다.
교체 시 헌법 개정이 필요하다.

| 계층 | 선택 | 버전 조건 |
|------|------|-----------|
| Python 런타임 | CPython | ≥ 3.13 |
| 패키지 관리 | uv | — |
| 백엔드 프레임워크 | FastAPI | ≥ 0.100 |
| 프론트엔드 | Streamlit | ≥ 1.30 |
| 데이터베이스 | PostgreSQL (SQLAlchemy) — 로컬: `localhost:5434/rag-practice` | ≥ 15 |
| 임베딩 모델 | BGE-M3 (`BAAI/bge-m3`) | 고정 |
| 벡터 저장소 | FAISS IndexFlatIP | — |
| LLM | Claude API (`claude-sonnet-4-6`) | 환경변수로 교체 가능 |
| 청킹 | RecursiveCharacterTextSplitter (size=800, overlap=120) | 기본값 |

---

## 4. 경계 (Scope Boundaries)

**포함 (In-Scope)**:
- PDF 파일 업로드, 저장, 처리 (추출 → 청킹 → 임베딩 → 인덱싱)
- 자연어 질의응답 (검색 → 재정렬 → 생성)
- SSE 스트리밍 답변 및 출처 표시
- 세션 내 대화 맥락 유지

**제외 (Out-of-Scope)**:
- 사용자 인증 및 다중 사용자 지원
- PDF 이외 문서 형식 (Word, Excel, 이미지 등)
- 문서 편집·수정 기능
- 오프라인 모드

---

## 5. 거버넌스 (Governance)

### 개정 절차

1. 개정 필요 사항을 PR 설명에 명시한다.
2. 버전을 Semantic Versioning 규칙에 따라 올린다.
   - **MAJOR**: 원칙 제거 또는 정의 변경 (하위 호환 불가)
   - **MINOR**: 원칙 추가 또는 범위 확장
   - **PATCH**: 오탈자, 표현 정제, 예시 추가
3. `LAST_AMENDED_DATE`를 개정일로 업데이트한다.
4. Sync Impact Report를 파일 상단 HTML 주석으로 추가한다.

### 규정 준수 검토

- `/speckit-implement` 실행 시 task 브랜치 네이밍이 P-06을 따르는지 확인한다.
- 새로운 LLM 호출 코드 추가 시 P-01(근거 우선) 시스템 프롬프트 적용 여부를 확인한다.
- 새로운 컴포넌트 도입 시 P-04(환경변수 전환) 적용 여부를 확인한다.
- 마일스톤 전환 시 P-05(측정 기반) 평가 스크립트 실행 결과를 기록한다.
- 새로운 DB 스키마·모델 추가 시 P-08(데이터 정규화) 위반 여부(중복 JSONB, 배열 쿼리 대상)를 확인한다.
- 원본 파일 변경을 감지·반영하는 코드 추가 시 P-09(외부 파일 변경 처리)에 따라 사용자 확인 경로를 거치는지 확인한다.

### 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| 1.0.0 | 2026-04-18 | 초기 제정 |
| 1.1.0 | 2026-04-18 | P-07 Task 완성 상태 표시 규칙 추가 |
| 1.2.0 | 2026-04-18 | 3절 데이터베이스 제약 SQLite → PostgreSQL 변경 (specs/002-postgres-local-db) |
| 1.2.1 | 2026-04-18 | 3절 Python 런타임 ≥3.13, 패키지 관리 uv 항목 추가 (pyproject.toml 반영) |
| 1.3.0 | 2026-04-20 | P-08 데이터 정규화, P-09 외부 파일 변경 처리 원칙 추가; P-06 spec 없는 작업 브랜치 규칙 보완 (specs/003, specs/004, file-watcher, open-pdf-native 회고) |
