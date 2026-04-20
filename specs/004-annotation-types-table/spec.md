# Feature Specification: chunks.annotation_types 정규화 - 별도 테이블 분리

**Feature Name**: chunks.annotation_types 정규화 - 별도 테이블 분리  
**Short Name**: annotation-types-table  
**Created**: 2026-04-20  
**Updated**: 2026-04-20  
**Status**: Draft

---

## Overview

현재 `chunks` 테이블의 `annotation_types` 컬럼(JSONB 타입)은 문서 내 주석 유형 정보를 각 청크마다 중복 저장하고 있어 정규화 원칙에 위배된다. 이 데이터를 `documents` 테이블과 1:1 관계를 갖는 별도 테이블 `document_annotation_types`로 분리하여 데이터 중복을 제거하고 무결성을 강화한다. 기존 `chunks.annotation_types` 컬럼은 삭제하며, 연관 코드(인덱서, 리트리버 등)를 새 테이블 구조에 맞게 수정한다.

---

## Problem Statement

`chunks.annotation_types`(JSONB)는 특정 문서에 포함된 주석 유형(`highlight`, `underline`, `strikeout`, `memo`) 정보를 저장한다. 그런데 이 정보는 문서 단위 속성임에도 불구하고, 동일 문서에 속하는 모든 청크에 동일한 값이 중복 저장된다. 이는 다음 문제를 야기한다:

- **데이터 중복**: 동일 문서의 N개 청크에 동일한 주석 유형 정보가 N번 저장된다.
- **갱신 이상(Update Anomaly)**: 주석 유형이 변경될 경우 해당 문서의 모든 청크 레코드를 수정해야 한다.
- **정규화 위반**: JSONB 컬럼 내부에 반복 그룹(repeating group)이 존재하며, 원자값(atomic value) 조건을 만족하지 않는다.

---

## Goals

- `chunks.annotation_types` JSONB 컬럼을 제거하고 별도 테이블로 분리한다.
- 신규 테이블은 `documents`와 1:1 관계를 맺어 문서당 하나의 주석 유형 레코드를 보장한다.
- 기존 데이터를 신규 테이블로 마이그레이션하며, 데이터 손실 없이 전환한다.
- 인덱서, 리트리버 등 관련 서비스 코드를 신규 구조에 맞게 수정한다.
- API 응답 스펙(주석 유형 정보 포함)이 기존과 동일하게 유지된다.

---

## Non-Goals

- `chunks.memo_content` 컬럼의 구조 변경 (이번 범위 외)
- 주석 유형 데이터 외 다른 JSONB 컬럼의 정규화
- 기존 PDF 문서의 재파싱 또는 주석 재추출
- 주석 유형의 종류 추가·변경 (기존 4종 유지)

---

## User Scenarios & Testing

### 시나리오 1: 주석 포함 PDF 신규 업로드

**Actor**: 일반 사용자  
**전제조건**: 분리 작업이 완료된 상태.

1. 사용자가 주석 포함 PDF를 업로드한다.
2. 시스템이 문서를 처리하며 주석 유형을 추출한다.
3. 추출된 주석 유형이 `document_annotation_types` 테이블에 저장된다.
4. 사용자가 주석 관련 질문을 한다.
5. 시스템이 올바른 주석 유형 정보를 메타데이터에 포함하여 반환한다.

**성공 기준**: 신규 테이블에 문서당 하나의 레코드가 생성되며, 청크 메타데이터에 주석 유형 정보가 정상 포함된다.

---

### 시나리오 2: 기존 데이터 마이그레이션 후 질의응답

**Actor**: 시스템 관리자 (마이그레이션 실행)  
**전제조건**: 기존에 주석 포함 문서가 처리되어 `chunks.annotation_types`에 데이터가 있다.

1. 마이그레이션 스크립트가 실행된다.
2. 각 문서별로 청크의 `annotation_types` 값을 집계하여 `document_annotation_types` 테이블에 저장한다.
3. `chunks.annotation_types` 컬럼이 삭제된다.
4. 사용자가 기존 문서에 대해 주석 관련 질문을 한다.
5. 마이그레이션 전과 동일한 응답이 반환된다.

**성공 기준**: 마이그레이션 전후 주석 유형 정보가 동일하며, 기존 질의응답 결과에 차이가 없다.

---

### 시나리오 3: 주석 없는 문서 처리

**Actor**: 일반 사용자

1. 사용자가 주석 없는 PDF를 업로드한다.
2. 시스템이 처리한다.
3. `document_annotation_types` 테이블에 해당 문서 레코드가 생성되나 모든 주석 유형 값이 비어 있거나 레코드가 생성되지 않는다.
4. 질의응답 시 주석 관련 메타데이터가 빈 값으로 반환된다.

**성공 기준**: 주석 없는 문서도 기존과 동일하게 처리되며 오류가 발생하지 않는다.

---

## Functional Requirements

### 데이터베이스

- FR-01: `document_annotation_types` 테이블을 신규 생성한다. `document_id`(FK → `documents.id`, UNIQUE)를 포함하여 `documents`와 1:1 관계를 보장한다.
- FR-02: `document_annotation_types`는 주석 유형 정보를 JSONB 또는 개별 boolean 컬럼으로 저장한다.
- FR-03: `documents`가 삭제될 경우 연관 `document_annotation_types` 레코드도 자동 삭제된다(CASCADE DELETE).
- FR-04: 마이그레이션 스크립트가 기존 `chunks.annotation_types` 데이터를 `document_annotation_types`로 이전한다. 동일 문서의 여러 청크에서 주석 유형을 합산(union)하여 저장한다.
- FR-05: 마이그레이션 완료 후 `chunks.annotation_types` 컬럼을 삭제한다.

### 서비스 레이어

- FR-06: 인덱서(`indexer.py`)가 청크 저장 시 `annotation_types`를 `chunks`가 아닌 `document_annotation_types` 테이블에 저장하도록 수정한다.
- FR-07: 리트리버(`retriever.py`)가 청크 메타데이터 구성 시 `document_annotation_types`에서 주석 유형을 조회하여 포함시킨다.
- FR-08: `Chunk.to_metadata()` 메서드가 연관 문서의 `annotation_types`를 참조하도록 수정한다.

### ORM 모델

- FR-09: `Chunk` 모델에서 `annotation_types` 컬럼을 제거한다.
- FR-10: `Document` 모델에 `annotation_types` 역참조 관계(`relationship`)를 추가한다.
- FR-11: `DocumentAnnotationType` ORM 모델을 신규 작성한다.

---

## Success Criteria

- 마이그레이션 전후 API 응답의 `annotation_types`, `annotations` 필드 값이 동일하다.
- `chunks` 테이블에서 `annotation_types` 컬럼이 완전히 제거된다.
- 동일 문서의 모든 청크가 `document_annotation_types`의 단일 레코드를 공유한다.
- 주석 포함 문서와 미포함 문서 모두 오류 없이 처리된다.
- 마이그레이션 스크립트가 멱등성을 보장한다(이미 실행된 경우 재실행 시 오류 없음).

---

## Key Entities

| 엔티티 | 변경 사항 |
|--------|-----------|
| `Chunk` | `annotation_types` JSONB 컬럼 제거 |
| `Document` | `annotation_types` 역참조 관계(`one-to-one`) 추가 |
| `DocumentAnnotationType` (신규) | `id`, `document_id`(FK, UNIQUE), `annotation_types`(JSONB) |

---

## Assumptions

- `chunks.annotation_types`는 동일 문서의 모든 청크에서 동일한 값을 가지거나, 청크별로 다른 경우 합산(union)하여 문서 수준에서 표현 가능하다고 가정한다.
- 기존 JSONB 구조(`{"highlight": ..., "underline": ...}`)는 그대로 유지한다.
- Alembic 없이 수동 SQL + `init_db()` 패턴으로 마이그레이션을 처리한다(기존 방식 유지).
- 재처리(reindex) 시에도 `document_annotation_types` 레코드를 갱신하는 방식으로 동작한다.

---

## Dependencies

- `backend/models/document.py` — `Chunk`, `Document` ORM 모델 수정
- `backend/models/database.py` — `init_db()` 마이그레이션 로직 수정
- `backend/services/indexer.py` — 청크 저장 시 `document_annotation_types` 쓰기
- `backend/services/retriever.py` — 청크 메타데이터 구성 시 `document_annotation_types` 읽기
- `scripts/add_annotation_columns.py` — 기존 마이그레이션 스크립트 참고
