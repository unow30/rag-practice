# Feature Specification: 로컬 PostgreSQL 데이터베이스 마이그레이션

**Feature Name**: 로컬 PostgreSQL 데이터베이스 마이그레이션  
**Short Name**: postgres-local-db  
**Created**: 2026-04-18  
**Status**: Draft

---

## Overview

현재 SQLite 기반으로 저장되는 문서(Document)와 청크(Chunk) 데이터를 로컬 환경에서 실행 중인 PostgreSQL 데이터베이스로 이전한다. 벡터 검색은 기존 FAISS 방식을 유지하며, 데이터 저장 계층만 교체한다.

---

## Problem Statement

현재 SQLite는 동시 쓰기 처리 한계, 운영 환경과의 불일치, 고급 쿼리 기능 부재 등 개발 및 향후 확장에 제약이 있다. PostgreSQL로 전환하면 동시 접근 안정성, 운영 환경 일관성, 더 풍부한 데이터 조작 기능을 확보할 수 있다.

---

## Goals

- 문서(Document)와 청크(Chunk) 데이터를 PostgreSQL에 저장한다.
- 로컬 PostgreSQL 인스턴스(`localhost:5434`, DB명: `rag-practice`)에 연결한다.
- 기존 기능(문서 업로드, 처리 파이프라인, 질의응답, 문서 관리)이 마이그레이션 후에도 동일하게 동작한다.
- 기존 SQLite 데이터의 PostgreSQL 이전을 지원한다.

---

## Non-Goals

- 대화(Conversation) 및 메시지 데이터의 영구 저장 (현재 인메모리 방식 유지)
- FAISS 벡터 저장소 교체 (pgvector 등으로의 전환은 별도 태스크)
- 운영(Production) 환경 또는 원격 PostgreSQL 설정
- 스키마 변경 또는 새로운 엔터티 추가

---

## User Scenarios & Testing

### 시나리오 1: 마이그레이션 후 문서 업로드 및 처리

**Actor**: 개발자 (로컬 환경 실행)  
**전제조건**: 로컬 PostgreSQL이 `localhost:5434`에서 실행 중이며 `rag-practice` 데이터베이스가 존재한다.

1. 개발자가 애플리케이션을 시작한다.
2. 시스템이 PostgreSQL에 연결되고 필요한 테이블이 자동으로 생성된다.
3. 사용자가 PDF를 업로드한다.
4. 시스템이 문서를 처리하고 Document·Chunk 레코드를 PostgreSQL에 저장한다.
5. 문서가 `READY` 상태로 전환되고 질의가 가능해진다.

**성공 기준**: 업로드부터 질의 가능 상태까지 마이그레이션 전과 동일한 시간(20페이지 기준 30초 이내) 내에 완료된다.

---

### 시나리오 2: 마이그레이션 후 질의응답

**Actor**: 일반 사용자  
**전제조건**: PostgreSQL에 문서가 저장되어 있으며 FAISS 인덱스가 존재한다.

1. 사용자가 자연어로 질문을 입력한다.
2. 시스템이 FAISS로 관련 청크 ID를 검색하고 PostgreSQL에서 청크 내용을 조회한다.
3. 시스템이 답변과 출처를 반환한다.

**성공 기준**: 질문 제출 후 첫 토큰 응답이 3초 이내에 표시된다.

---

### 시나리오 3: 기존 SQLite 데이터 이전

**Actor**: 개발자  
**전제조건**: 기존 `data/rag.db` SQLite 파일에 문서·청크 데이터가 존재한다.

1. 개발자가 데이터 마이그레이션 절차를 실행한다.
2. 시스템이 SQLite의 모든 Document·Chunk 레코드를 PostgreSQL로 복사한다.
3. 기존 FAISS 인덱스 파일은 그대로 유지된다.
4. 마이그레이션 완료 후 기존 문서들을 정상적으로 조회하고 질의할 수 있다.

**성공 기준**: 마이그레이션 전후 문서 수와 청크 수가 동일하며, 기존 문서에 대한 질의가 정상 동작한다.

---

### 시나리오 4: 데이터베이스 연결 실패 처리

**Actor**: 개발자  
**전제조건**: PostgreSQL이 실행되지 않거나 연결 정보가 잘못된 상태.

1. 개발자가 애플리케이션을 시작한다.
2. 시스템이 데이터베이스 연결을 시도한다.
3. 연결에 실패하면 명확한 오류 메시지와 함께 애플리케이션이 종료된다.

**성공 기준**: 연결 실패 원인(잘못된 호스트, 포트, 자격증명 등)을 명확히 안내하는 오류 메시지가 출력된다.

---

## Functional Requirements

### FR-01: PostgreSQL 연결 설정

- 애플리케이션은 환경 변수로 PostgreSQL 연결 정보를 관리한다.
  - 호스트: `localhost`
  - 포트: `5434`
  - 데이터베이스명: `rag-practice`
  - 사용자: `rag-practice`
  - 비밀번호: `rag-practice`
- 연결 정보는 `.env` 파일에서 관리되며 소스 코드에 하드코딩되지 않는다.
- 애플리케이션 시작 시 데이터베이스 연결 상태를 검증한다.

### FR-02: 스키마 자동 생성

- 애플리케이션 최초 실행 시 PostgreSQL에 `documents` 및 `chunks` 테이블이 자동으로 생성된다.
- 테이블이 이미 존재하는 경우 중복 생성하지 않는다.
- 기존 SQLite 스키마(컬럼명, 타입, 관계)와 동일한 구조를 PostgreSQL에 구현한다.

### FR-03: CRUD 동작 호환성

- 문서 업로드, 상태 업데이트, 조회, 삭제 동작이 PostgreSQL에서도 정상 동작한다.
- 청크 저장, 조회, 삭제(문서 삭제 시 연쇄 삭제 포함) 동작이 PostgreSQL에서도 정상 동작한다.
- 기존 SQLite 코드베이스에서 데이터베이스 연결 및 쿼리 레이어만 교체한다.

### FR-04: SQLite 데이터 마이그레이션

- 기존 SQLite 데이터를 PostgreSQL로 이전하는 마이그레이션 스크립트를 제공한다.
- 스크립트는 Document·Chunk 레코드를 모두 이전하며, 이전 후 데이터 정합성을 검증한다.
- FAISS 인덱스 파일(`data/indexes/`)은 마이그레이션 대상에서 제외한다.
- 마이그레이션 스크립트는 멱등성(idempotency)을 보장한다(중복 실행해도 안전).

### FR-05: 환경 설정 문서화

- PostgreSQL 연결을 위한 환경 변수 항목이 `.env.example` 또는 관련 설정 파일에 문서화된다.
- 로컬 환경에서 PostgreSQL을 설정하는 방법이 개발 가이드에 추가된다.

---

## Success Criteria

| 기준 | 측정 방법 | 목표값 |
|------|-----------|--------|
| 기능 회귀 없음 | 기존 E2E 시나리오(업로드·처리·질의·삭제) 전체 통과 여부 | 100% 통과 |
| 문서 처리 성능 유지 | 마이그레이션 전후 문서 처리 시간 비교 | 기존 대비 20% 이내 차이 |
| 질의 응답 성능 유지 | 마이그레이션 전후 첫 토큰 응답 시간 비교 | 3초 이내 유지 |
| 데이터 마이그레이션 정확도 | SQLite와 PostgreSQL의 레코드 수 및 내용 일치 여부 | 100% 일치 |
| 연결 실패 안내 | 잘못된 연결 정보로 시작 시 오류 메시지 출력 여부 | 명확한 원인 메시지 출력 |

---

## Key Entities

### Document (문서)

| 속성 | 설명 |
|------|------|
| id | 고유 식별자 (UUID) |
| name | 파일명 |
| file_path | 저장 경로 (unique) |
| file_hash | 파일 해시 (unique) |
| size_bytes | 파일 크기 |
| page_count | 페이지 수 |
| chunk_count | 청크 수 |
| index_path | FAISS 인덱스 경로 |
| status | 처리 상태 (PENDING/EXTRACTING/CHUNKING/EMBEDDING/READY/FAILED) |
| error_message | 오류 메시지 |
| uploaded_at | 업로드 일시 |
| processed_at | 처리 완료 일시 |

### Chunk (문서 청크)

| 속성 | 설명 |
|------|------|
| id | 고유 식별자 (UUID) |
| document_id | 소속 문서 ID (FK, cascade delete) |
| chunk_index | 청크 순서 |
| content | 텍스트 내용 |
| content_type | 콘텐츠 유형 (TEXT/TABLE/FIGURE) |
| page_number | 시작 페이지 번호 |
| page_end | 종료 페이지 번호 |
| section_title | 섹션 제목 |
| token_count | 토큰 수 |
| faiss_index_id | FAISS 내부 인덱스 ID |
| created_at | 생성 일시 |

---

## Assumptions

- 로컬 환경에 PostgreSQL 15 이상이 이미 설치되어 있거나 Docker로 실행 가능하다.
- `rag-practice` 데이터베이스와 사용자 계정이 PostgreSQL에 사전 생성되어 있다.
- 기존 FAISS 인덱스 파일 경로(`data/indexes/`)는 변경되지 않는다.
- 대화(Conversation) 데이터는 인메모리 상태로 유지하며 이번 마이그레이션 범위에 포함되지 않는다.
- SQLite에서 PostgreSQL로 스키마 변환 시 데이터 타입 매핑은 최대한 동일하게 유지한다.

---

## Dependencies

- 로컬 PostgreSQL 인스턴스 (`localhost:5434`)
- PostgreSQL Python 드라이버 (`psycopg2` 또는 `asyncpg`)
- 기존 SQLAlchemy ORM 구조 유지

---

## Out of Scope

- 운영 환경 PostgreSQL 배포 및 설정
- pgvector를 이용한 벡터 저장소 통합
- 대화·메시지 데이터의 PostgreSQL 저장
- 데이터베이스 마이그레이션 도구(Alembic 등) 도입
- 멀티 테넌시 또는 멀티 사용자 데이터 분리
