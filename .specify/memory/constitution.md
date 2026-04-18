<!--
SYNC IMPACT REPORT
==================
Version change  : 1.2.0 → 1.2.1
Modified        : 2026-04-18
Added sections  : N/A
Removed sections: N/A
Changed sections: 3절 기술 스택 제약 — Python 런타임 ≥3.13, 패키지 관리 uv 항목 추가 (pyproject.toml 반영)
Templates updated: N/A
-->

# 프로젝트 헌법 (Project Constitution)

**Project**: PDF RAG 대화형 웹 앱 (`rag-practice`)
**Constitution Version**: 1.2.1
**Ratification Date**: 2026-04-18
**Last Amended Date**: 2026-04-18

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

task 구현을 위한 브랜치는 반드시 아래 형식을 따른다.

```
{speckit-specify 폴더명}/{task-id}-{task-slug}
```

- **speckit-specify 폴더명**: `.specify/feature.json`의 `feature_directory`에서 `specs/` 제거
- **task-id**: tasks.md에 정의된 태스크 ID (예: `T-14`, `T-22`)
- **task-slug**: 태스크 내용을 2~4단어 kebab-case로 요약
- **구분자**: 슬래시(`/`) — Git 네임스페이스 브랜치로 동작

**예시**: `001-pdf-rag-chat-webapp/T-17-bm25-indexer`

**적용 범위**: 모든 feature 브랜치 생성 시 (`/speckit-implement` 포함)

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

### 버전 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| 1.0.0 | 2026-04-18 | 초기 제정 |
| 1.1.0 | 2026-04-18 | P-07 Task 완성 상태 표시 규칙 추가 |
| 1.2.0 | 2026-04-18 | 3절 데이터베이스 제약 SQLite → PostgreSQL 변경 (specs/002-postgres-local-db) |
| 1.2.1 | 2026-04-18 | 3절 Python 런타임 ≥3.13, 패키지 관리 uv 항목 추가 (pyproject.toml 반영) |
