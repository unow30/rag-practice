# Research: chunks.annotation_types 정규화

**Feature**: annotation-types-table  
**Created**: 2026-04-20

---

## R-01: 관계 테이블의 주체 결정 (chunks vs documents)

**Decision**: `documents`와 1:1 관계인 `document_annotation_types` 테이블로 분리.

**Rationale**:
- 현재 `chunks.annotation_types`는 동일 문서의 모든 청크에 동일한 JSONB가 저장되는 중복 패턴.
- 주석 유형 정보는 "이 문서에 어떤 주석이 존재하는가"라는 문서 단위 속성에 해당.
- 1:1 관계 + `UNIQUE` 제약으로 문서당 단일 레코드를 강제.
- CASCADE DELETE로 생명주기를 `documents`와 일치시켜 데이터 무결성 확보.

**Alternatives considered**:
- **청크 단위 M:N 정규화** (`chunk_annotation_types` 별도 테이블): 청크별로 주석 유형이 다르다면 이상적이나, 현재 코드/데이터 흐름에서 청크별 차별화가 없어 과도한 설계.
- **enum 배열 컬럼으로 변경**: 정규화 위반은 해소되지 않음(여전히 반복 그룹).

---

## R-02: JSONB 구조 유지 여부

**Decision**: JSONB 형태 유지 (`{"highlight": ..., "underline": ..., ...}`).

**Rationale**:
- 기존 `to_metadata()` 계약(`annotations` 딕셔너리, `annotation_types` 키 목록) 변경 없이 마이그레이션 가능.
- 주석 유형별 부가 데이터(색상, 좌표 등)가 미래에 추가될 여지 확보.
- PostgreSQL JSONB의 GIN 인덱스 활용 가능.

**Alternatives considered**:
- **개별 boolean 컬럼**(`has_highlight`, `has_underline` ...): 쿼리는 단순하나 주석 유형 추가 시 ALTER TABLE 필요. 스키마 경직성 증가.
- **enum 배열**: 유형 추가 시 enum 변경 필요. PostgreSQL enum은 추가는 가능하나 삭제가 까다로움.

---

## R-03: 데이터 이전 전략

**Decision**: `init_db()` 내 멱등성 있는 마이그레이션 SQL 삽입.

**Rationale**:
- 프로젝트는 Alembic을 사용하지 않으며, 기존 패턴(`ALTER TABLE ... IF NOT EXISTS`)을 따르는 것이 일관성 있음.
- `information_schema.columns` 조회로 `chunks.annotation_types` 존재 여부를 선제 확인 → 재실행 시 안전.
- `jsonb_each` + `jsonb_object_agg`로 문서 단위로 모든 청크의 JSONB를 합산.
- `ON CONFLICT (document_id) DO NOTHING`으로 중복 삽입 방지.

**Alternatives considered**:
- **독립 마이그레이션 스크립트** (`scripts/migrate_annotation_types.py`): 개발자가 수동 실행해야 하며, 앱 시작 시 자동 적용되지 않아 운영 편의성 떨어짐.
- **Alembic 도입**: 기존 프로젝트 전체 마이그레이션 방식을 바꿔야 하므로 범위 초과.

---

## R-04: N+1 쿼리 방지

**Decision**: 현 단계에서는 SQLAlchemy lazy load 기본 동작에 의존. 필요 시 `selectinload` 추가.

**Rationale**:
- 현재 `retriever.py._build_langchain_docs()`는 이미 각 청크마다 `db.query(DocModel).first()`를 호출하고 있어(N+1 존재), annotation_info 접근이 별도 성능 저하를 유발하지 않음.
- `to_metadata()` 내 `self.document.annotation_info` 접근은 세션 활성 상태에서 자동 로드됨.
- 성능 최적화는 별도 태스크(추후 개선)로 분리.

**Alternatives considered**:
- `joinedload(Chunk.document, Document.annotation_info)`: 조인 쿼리 1회로 전체 로드. 다만 현 코드에 기존 N+1이 있으므로 개별 최적화는 범위 초과.
