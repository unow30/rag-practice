# Claude 프로젝트 규칙

## 브랜치 명명 규칙

task 구현을 위한 브랜치를 생성할 때, 반드시 아래 형식을 따른다.

### 형식
```
{speckit-specify 폴더명}/{task-id}-{task-slug}
```

### 예시
- `001-pdf-rag-chat-webapp/T-14-evaluation-set`
- `001-pdf-rag-chat-webapp/T-15-bm25-hybrid`
- `001-pdf-rag-chat-webapp/T-16-reranker`

### 규칙 상세
1. **speckit-specify 폴더명**: `.specify/feature.json`의 `feature_directory` 값에서 `specs/` 접두어를 제거한 부분을 사용한다.
   - 예: `"feature_directory": "specs/001-pdf-rag-chat-webapp"` → `001-pdf-rag-chat-webapp`
2. **task-id**: tasks.md에 정의된 태스크 ID (예: `T-14`, `T-15`)
3. **task-slug**: 태스크 내용을 2~4단어로 요약한 kebab-case 문자열
4. 구분자는 슬래시(`/`)를 사용한다 (Git에서 네임스페이스 브랜치로 동작).

### 적용 시점
- `/speckit-implement` 실행 시 각 task 브랜치 생성 때
- 수동으로 feature 브랜치를 생성할 때
