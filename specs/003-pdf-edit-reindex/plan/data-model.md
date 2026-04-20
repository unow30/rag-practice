# Data Model: 업로드 PDF 편집 반영 및 재처리

**Feature**: pdf-edit-reindex  
**Created**: 2026-04-20

---

## 변경 엔티티: Chunk

기존 `chunks` 테이블에 두 컬럼 추가.

### 신규 컬럼

| 컬럼 | 타입 | Nullable | 기본값 | 설명 |
|------|------|----------|--------|------|
| `annotation_types` | TEXT | YES | NULL | JSON 직렬화 배열 — `["highlight"]`, `["underline", "memo"]` 등 |
| `memo_content` | TEXT | YES | NULL | 사용자가 작성한 메모(Text/FreeText 주석) 내용 |

### 허용 값 (`annotation_types` 배열 원소)

| 값 | 의미 | PDF annot.type[0] |
|----|------|-------------------|
| `"highlight"` | 하이라이트 | 8 |
| `"underline"` | 밑줄 | 9 |
| `"strikeout"` | 취소선 | 11 |
| `"memo"` | 메모(팝업/인라인) | 0, 2 |

### 상태 전이 (재처리 흐름)

```
READY / FAILED
    │ POST /reindex
    ▼
EXTRACTING → CHUNKING → EMBEDDING → READY
                                      │ (실패 시)
                                      ▼
                                   FAILED
```

### to_metadata() 반환값 확장

```python
{
    "source": ...,
    "page": ...,
    "doc_id": ...,
    "section": ...,
    "version": ...,
    "chunk_id": ...,
    "content_type": ...,
    # 신규
    "annotation_types": ["highlight", "memo"],  # None이면 []
    "memo_content": "사용자 메모 내용",           # None이면 None
}
```

---

## 변경 없는 엔티티

- `Document`: 컬럼 변경 없음. 재처리 시 `status`, `processed_at`, `error_message`만 갱신.
- FAISS Index 파일: 재처리 시 `shutil.rmtree(doc.index_path)` 후 재생성.
- BM25 Index 파일: 재처리 시 `delete_bm25_index(doc.id)` 후 재생성.

---

## Alembic 마이그레이션 요약

```sql
ALTER TABLE chunks ADD COLUMN annotation_types TEXT;
ALTER TABLE chunks ADD COLUMN memo_content TEXT;
```
