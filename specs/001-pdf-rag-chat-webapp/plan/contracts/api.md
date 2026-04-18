# API Contracts: PDF RAG 대화형 웹 앱

**Base URL**: `http://localhost:8000/api`  
**Content-Type**: `application/json` (파일 업로드는 `multipart/form-data`)  
**Created**: 2026-04-18

---

## 문서 관리 API

### POST /api/documents — PDF 업로드

**Request** (`multipart/form-data`):
```
files: File[]   # PDF 파일 1~5개, 각 최대 50MB
```

**Response 202 Accepted**:
```json
{
  "documents": [
    {
      "id": "uuid",
      "name": "report.pdf",
      "size_bytes": 1048576,
      "status": "PENDING",
      "uploaded_at": "2026-04-18T10:00:00Z"
    }
  ]
}
```

**Error Responses**:
```json
// 400 - 잘못된 파일 형식
{ "error": "INVALID_FILE_TYPE", "message": "PDF 파일만 업로드 가능합니다." }

// 400 - 파일 크기 초과
{ "error": "FILE_TOO_LARGE", "message": "파일 크기가 50MB를 초과합니다: {filename}" }

// 409 - 중복 파일
{ "error": "DUPLICATE_FILE", "message": "이미 업로드된 문서입니다: {filename}" }

// 422 - 문서 수 한도 초과
{ "error": "DOCUMENT_LIMIT_EXCEEDED", "message": "최대 문서 수(20개)에 도달했습니다." }
```

---

### GET /api/documents — 문서 목록 조회

**Response 200**:
```json
{
  "documents": [
    {
      "id": "uuid",
      "name": "report.pdf",
      "size_bytes": 1048576,
      "page_count": 42,
      "chunk_count": 87,
      "status": "READY",
      "uploaded_at": "2026-04-18T10:00:00Z",
      "processed_at": "2026-04-18T10:00:28Z"
    }
  ],
  "total": 3,
  "limit": 20
}
```

---

### GET /api/documents/{id}/status — 처리 상태 조회

**Path Parameter**: `id` (UUID)

**Response 200**:
```json
{
  "id": "uuid",
  "status": "EMBEDDING",
  "progress_message": "임베딩 중... (42/87 청크)",
  "error_message": null
}
```

**Error Responses**:
```json
// 404 - 문서 없음
{ "error": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다." }
```

---

### DELETE /api/documents/{id} — 문서 삭제

**Path Parameter**: `id` (UUID)

**Response 204 No Content** (성공 시 본문 없음)

**Error Responses**:
```json
// 404 - 문서 없음
{ "error": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다." }
```

---

## 대화 API

### POST /api/chat — 질문 전송 (스트리밍)

**Request**:
```json
{
  "conversation_id": "uuid | null",
  "question": "3분기 매출은 얼마인가요?",
  "document_ids": ["uuid1", "uuid2"]  // 비어있으면 전체 READY 문서 대상
}
```

**Response 200** — SSE (Server-Sent Events) 스트리밍:
```
Content-Type: text/event-stream

event: token
data: {"token": "3분기"}

event: token
data: {"token": " 매출은"}

...

event: done
data: {
  "conversation_id": "uuid",
  "message_id": "uuid",
  "sources": [
    {
      "document_id": "uuid",
      "document_name": "report.pdf",
      "page_number": 15,
      "content_snippet": "3분기 매출은 총 1,200억 원으로...",
      "relevance_score": 0.92
    }
  ],
  "latency_ms": 1840
}

event: error
data: {"error": "SERVICE_UNAVAILABLE", "message": "AI 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."}
```

**Error Responses** (스트리밍 시작 전):
```json
// 400 - 빈 질문
{ "error": "EMPTY_QUESTION", "message": "질문을 입력해 주세요." }

// 400 - 대상 문서 없음 또는 미처리 상태
{ "error": "NO_READY_DOCUMENTS", "message": "질의 가능한 문서가 없습니다." }

// 504 - AI 서비스 타임아웃 (30초)
{ "error": "AI_TIMEOUT", "message": "AI 서비스가 응답하지 않습니다. 재시도해 주세요." }
```

---

### DELETE /api/chat/{conversation_id} — 대화 기록 초기화

**Path Parameter**: `conversation_id` (UUID)

**Response 204 No Content**

---

## 공통 규칙

- 모든 타임스탬프: ISO 8601 형식 (`2026-04-18T10:00:00Z`)
- 모든 ID: UUID v4
- 에러 응답 형식: `{ "error": "ERROR_CODE", "message": "사용자 표시용 메시지" }`
- 스트리밍 응답의 첫 토큰은 요청 후 **3초 이내** 전송
- AI 서비스 응답 없을 시 **30초** 후 타임아웃 이벤트 전송
