# rag-practice

PDF 문서를 업로드하고 자연어로 질의응답하는 RAG 기반 웹 앱.

---

## 빠른 시작

### 1. PostgreSQL 실행

```bash
docker compose up -d postgres
```

### 2. 의존성 설치

```bash
uv sync
# 또는
pip install -r requirements.txt
```

### 3. 환경변수 설정

```bash
cp .env.example .env
# .env 파일에서 ANTHROPIC_API_KEY 설정
```

### 4. 앱 실행

```bash
python -m uvicorn backend.main:app --reload
```

### 5. 기존 SQLite 데이터 마이그레이션 (선택)

`data/rag.db` 파일이 존재하는 경우에만 실행:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

---

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 문자열 | `postgresql://rag-practice:rag-practice@localhost:5434/rag-practice` |
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `EMBEDDING_MODEL` | 임베딩 모델 | `BAAI/bge-m3` |
| `DATA_DIR` | 데이터 저장 경로 | `./data` |

전체 환경변수 목록은 `.env.example` 참조.

---

## 개발 가이드

- 스펙: `specs/002-postgres-local-db/spec.md`
- 플랜: `specs/002-postgres-local-db/plan/`
- 프로젝트 헌법: `.specify/memory/constitution.md`
