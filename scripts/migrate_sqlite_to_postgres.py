"""
SQLite → PostgreSQL 데이터 마이그레이션 스크립트

사용법:
    python scripts/migrate_sqlite_to_postgres.py

환경변수:
    DATABASE_URL  PostgreSQL 연결 문자열 (기본값: .env 파일 참조)
    DB_PATH       SQLite 파일 경로 (기본값: ./data/rag.db)

멱등성: 이미 존재하는 레코드(동일 id)는 건너뜁니다.
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 실행 시 backend 모듈 인식)
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.getenv("DB_PATH", "./data/rag.db")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://rag-practice:rag-practice@localhost:5434/rag-practice",
)


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def migrate():
    sqlite_path = Path(SQLITE_PATH)
    if not sqlite_path.exists():
        print(f"[SKIP] SQLite 파일 없음: {sqlite_path} — 마이그레이션 불필요")
        return

    print(f"[INFO] SQLite 원본: {sqlite_path}")
    print(f"[INFO] PostgreSQL 대상: {DATABASE_URL.split('@')[-1]}")

    # SQLite 연결
    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row

    # PostgreSQL 연결 (SQLAlchemy)
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        print(f"[ERROR] PostgreSQL 연결 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # 스키마 생성 (없으면)
    from backend.models.database import Base
    from backend.models.document import Document, Chunk  # noqa: F401
    Base.metadata.create_all(bind=engine)

    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    dest = Session()

    try:
        # ── Documents 마이그레이션 ─────────────────────────────────
        src_docs = src.execute("SELECT * FROM documents").fetchall()
        inserted_docs = 0
        skipped_docs = 0

        for row in src_docs:
            if dest.get(Document, row["id"]):
                skipped_docs += 1
                continue
            doc = Document(
                id=row["id"],
                name=row["name"],
                file_path=row["file_path"],
                file_hash=row["file_hash"],
                size_bytes=row["size_bytes"],
                page_count=row["page_count"],
                chunk_count=row["chunk_count"],
                index_path=row["index_path"],
                status=row["status"],
                error_message=row["error_message"],
                uploaded_at=_parse_dt(row["uploaded_at"]),
                processed_at=_parse_dt(row["processed_at"]),
            )
            dest.add(doc)
            inserted_docs += 1

        dest.commit()

        # ── Chunks 마이그레이션 ────────────────────────────────────
        src_chunks = src.execute("SELECT * FROM chunks").fetchall()
        inserted_chunks = 0
        skipped_chunks = 0

        for row in src_chunks:
            if dest.get(Chunk, row["id"]):
                skipped_chunks += 1
                continue
            chunk = Chunk(
                id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                content_type=row["content_type"],
                page_number=row["page_number"],
                page_end=row["page_end"],
                section_title=row["section_title"],
                version=row["version"],
                token_count=row["token_count"] or 0,
                faiss_index_id=row["faiss_index_id"],
                created_at=_parse_dt(row["created_at"]),
            )
            dest.add(chunk)
            inserted_chunks += 1

        dest.commit()

        # ── 검증 ──────────────────────────────────────────────────
        sqlite_doc_count = src.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        sqlite_chunk_count = src.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        pg_doc_count = dest.query(Document).count()
        pg_chunk_count = dest.query(Chunk).count()

        doc_ok = sqlite_doc_count == pg_doc_count
        chunk_ok = sqlite_chunk_count == pg_chunk_count

        print(f"\n[RESULT] Documents : SQLite={sqlite_doc_count}, PostgreSQL={pg_doc_count} "
              f"{'✓' if doc_ok else '✗ 불일치!'}")
        print(f"[RESULT] Chunks    : SQLite={sqlite_chunk_count}, PostgreSQL={pg_chunk_count} "
              f"{'✓' if chunk_ok else '✗ 불일치!'}")
        print(f"[INFO]   삽입={inserted_docs} docs / {inserted_chunks} chunks, "
              f"건너뜀={skipped_docs} docs / {skipped_chunks} chunks")

        if not doc_ok or not chunk_ok:
            print("[WARN] 레코드 수 불일치 — 마이그레이션을 재검토하세요.", file=sys.stderr)
            sys.exit(1)

        print("\n[INFO] 마이그레이션 완료.")
        print("[INFO] 검증 완료 후 data/rag.db 파일을 수동으로 삭제하거나 보관하세요.")

    except Exception as e:
        dest.rollback()
        print(f"[ERROR] 마이그레이션 실패: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        dest.close()
        src.close()


if __name__ == "__main__":
    migrate()
