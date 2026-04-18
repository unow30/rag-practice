# Quickstart: 로컬 PostgreSQL 설정 가이드

**Feature**: specs/002-postgres-local-db  
**Created**: 2026-04-18

---

## 사전 요구사항

- Docker Desktop (권장) 또는 로컬 PostgreSQL 15+ 설치
- 기존 `rag-practice` 앱 환경 설정 완료 (`.venv` 활성화 상태)

---

## 1. PostgreSQL 로컬 실행 (Docker 권장)

### Docker Compose로 실행

`docker-compose.yml`이 없다면 아래로 생성:

```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: rag-practice
      POSTGRES_USER: rag-practice
      POSTGRES_PASSWORD: rag-practice
    ports:
      - "5434:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

```bash
# PostgreSQL 시작
docker compose up -d postgres

# 연결 확인
docker compose exec postgres psql -U rag-practice -d rag-practice -c "SELECT version();"
```

### 로컬 PostgreSQL 직접 사용 시

```bash
# macOS (Homebrew)
brew install postgresql@15
brew services start postgresql@15

# DB 및 유저 생성
psql postgres -c "CREATE USER \"rag-practice\" WITH PASSWORD 'rag-practice';"
psql postgres -c "CREATE DATABASE \"rag-practice\" OWNER \"rag-practice\";"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE \"rag-practice\" TO \"rag-practice\";"

# 포트 5432가 기본값. 5434 사용 시 postgresql.conf에서 port 변경 필요
```

---

## 2. 의존성 설치

```bash
# 가상환경 활성화 상태에서
pip install -r requirements.txt
```

`requirements.txt`에 `psycopg2-binary`가 포함되어 있는지 확인:

```bash
grep psycopg2 requirements.txt
# 출력: psycopg2-binary>=2.9
```

---

## 3. 환경변수 설정

`.env` 파일에서 `DB_PATH`를 `DATABASE_URL`로 교체:

```bash
# 기존 줄 제거
# DB_PATH=./data/rag.db

# 아래 줄 추가
DATABASE_URL=postgresql://rag-practice:rag-practice@localhost:5434/rag-practice
```

---

## 4. 스키마 생성 확인

```bash
# 앱 시작 시 자동으로 테이블 생성
python -m uvicorn backend.main:app --reload

# 로그에서 확인
# INFO: Database initialized (PostgreSQL)
```

또는 수동으로 확인:

```bash
docker compose exec postgres psql -U rag-practice -d rag-practice -c "\dt"
# 출력:
#  Schema |    Name    | Type  |     Owner
# --------+------------+-------+---------------
#  public | chunks     | table | rag-practice
#  public | documents  | table | rag-practice
```

---

## 5. 기존 SQLite 데이터 마이그레이션 (선택)

SQLite에 기존 데이터가 있는 경우에만 실행:

```bash
# SQLite 파일 존재 확인
ls data/rag.db

# 마이그레이션 실행
python scripts/migrate_sqlite_to_postgres.py

# 결과 확인 (예시)
# [INFO] Documents: SQLite=5, PostgreSQL=5 ✓
# [INFO] Chunks: SQLite=347, PostgreSQL=347 ✓
# [INFO] Migration complete.
```

> **주의**: 마이그레이션 후 SQLite 파일(`data/rag.db`)은 자동으로 삭제하지 않습니다.  
> 검증 완료 후 수동으로 삭제하거나 별도 보관하세요.

---

## 6. 동작 확인

```bash
# 앱 실행
python -m uvicorn backend.main:app --reload

# 헬스체크
curl http://localhost:8000/health
# {"status": "ok", "db": "postgresql"}

# 문서 목록 조회
curl http://localhost:8000/api/documents
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 방법 |
|------|------|-----------|
| `could not connect to server` | PostgreSQL 미실행 | `docker compose up -d postgres` |
| `password authentication failed` | 연결 정보 불일치 | `.env`의 `DATABASE_URL` 확인 |
| `database "rag-practice" does not exist` | DB 미생성 | Docker Compose 재실행 또는 수동 DB 생성 |
| `port 5434 failed` | 포트 충돌 | `docker compose ps`로 상태 확인 |
| ENUM 생성 오류 | PostgreSQL ENUM 중복 | `DROP TYPE IF EXISTS` 후 재시도 |
