# Data Model: document_annotation_types

**Feature**: annotation-types-table  
**Created**: 2026-04-20

---

## ER 다이어그램 (변경 전)

```
┌─────────────┐       ┌──────────────────────────┐
│  documents  │ 1───N │  chunks                  │
│             │       │  - id                    │
│  - id       │       │  - document_id (FK)      │
│  - name     │       │  - content               │
│  - ...      │       │  - annotation_types JSONB│ ← 정규화 위반
│             │       │  - memo_content          │
└─────────────┘       │  - ...                   │
                      └──────────────────────────┘
```

## ER 다이어그램 (변경 후)

```
┌─────────────┐       ┌──────────────────────────┐
│  documents  │ 1───N │  chunks                  │
│             │       │  - id                    │
│  - id       │       │  - document_id (FK)      │
│  - name     │       │  - content               │
│  - ...      │       │  - memo_content          │
│             │       │  - ...                   │
└──────┬──────┘       └──────────────────────────┘
       │ 1:1
       │ (CASCADE DELETE)
       ▼
┌───────────────────────────────────┐
│  document_annotation_types        │
│  - id                             │
│  - document_id (FK, UNIQUE)       │
│  - annotation_types JSONB         │
└───────────────────────────────────┘
```

---

## Entity: DocumentAnnotationType (신규)

### 스키마

| 필드 | 타입 | 제약 | 설명 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK, UUID v4 | 레코드 고유 ID |
| `document_id` | VARCHAR(36) | FK → `documents.id`, UNIQUE, NOT NULL, ON DELETE CASCADE | 문서 참조 (1:1) |
| `annotation_types` | JSONB | NULLABLE | 주석 유형 딕셔너리 |

### JSONB 구조

```json
{
  "highlight": [...],
  "underline": [...],
  "strikeout": [...],
  "memo": [...]
}
```

- 키: 주석 유형명 (`highlight`, `underline`, `strikeout`, `memo`)
- 값: PDF 파서가 반환하는 주석 상세 (텍스트 구간 배열 등)
- 특정 유형이 없을 경우 키 자체가 생략됨

### 제약 조건

- `document_id`는 `UNIQUE` → 문서당 1개 레코드만 허용 (1:1 보장)
- `ON DELETE CASCADE` → 문서 삭제 시 자동 삭제

---

## Entity: Chunk (변경)

| 필드 | 변경 |
|------|------|
| `annotation_types` | **삭제** |
| 기타 필드 | 변경 없음 |

---

## Entity: Document (변경)

SQLAlchemy 관계만 추가되며 컬럼 변경 없음.

```python
annotation_info = relationship(
    "DocumentAnnotationType",
    back_populates="document",
    uselist=False,
    cascade="all, delete-orphan",
)
```

---

## 상태 전이

해당 없음 (테이블 레코드는 생성/갱신/삭제만 수행).

---

## 데이터 이전 규칙

### 기존 → 신규 매핑

- **Source**: `chunks.annotation_types` (JSONB or TEXT, per-chunk)
- **Target**: `document_annotation_types.annotation_types` (JSONB, per-document)
- **Aggregation**: 동일 `document_id`의 모든 청크 JSONB를 `jsonb_object_agg`로 합산 (key 충돌 시 임의 값 선택)
- **Filter**: `annotation_types IS NOT NULL`인 청크만 포함
- **Conflict**: `document_id` 중복 시 DO NOTHING (멱등성)

### SQL 구현

```sql
INSERT INTO document_annotation_types (id, document_id, annotation_types)
SELECT gen_random_uuid()::text, document_id, jsonb_object_agg(key, value)
FROM chunks, jsonb_each(annotation_types)
WHERE annotation_types IS NOT NULL
GROUP BY document_id
ON CONFLICT (document_id) DO NOTHING;
```
