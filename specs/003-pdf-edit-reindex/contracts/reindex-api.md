# API Contract: 문서 재처리 엔드포인트

**Feature**: pdf-edit-reindex  
**Created**: 2026-04-20

---

## POST /api/documents/{doc_id}/reindex

### 설명
지정한 문서의 기존 청크·인덱스를 삭제하고 추출→청킹→임베딩→인덱싱 파이프라인을 재실행한다.

### Path Parameters

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `doc_id` | string (UUID) | ✅ | 재처리할 문서의 ID |

### Request Body
없음 (body 불필요)

### Response

#### 202 Accepted — 재처리 시작됨

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PENDING",
  "message": "재처리가 시작되었습니다."
}
```

#### 404 Not Found — 문서 없음

```json
{
  "error": "DOCUMENT_NOT_FOUND",
  "message": "문서를 찾을 수 없습니다."
}
```

#### 409 Conflict — 이미 처리 중

```json
{
  "error": "ALREADY_PROCESSING",
  "message": "이미 처리 중인 문서입니다."
}
```

### 상태 조회

재처리 진행 상황은 기존 `GET /api/documents/{doc_id}/status` 엔드포인트로 확인.

```json
{
  "id": "550e8400-...",
  "status": "EXTRACTING",
  "progress_message": "텍스트 추출 중...",
  "error_message": null
}
```

### 허용 시작 상태

| 현재 상태 | 재처리 허용 |
|-----------|------------|
| READY | ✅ |
| FAILED | ✅ |
| PENDING | ❌ (409) |
| EXTRACTING | ❌ (409) |
| CHUNKING | ❌ (409) |
| EMBEDDING | ❌ (409) |
