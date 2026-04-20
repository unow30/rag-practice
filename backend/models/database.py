import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://rag-practice:rag-practice@localhost:5434/rag-practice",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.models.document import Document, Chunk, DocumentAnnotationType  # noqa: F401

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as e:
        url = engine.url
        print(
            f"[ERROR] Cannot connect to PostgreSQL: {url.host}:{url.port}/{url.database}\n"
            f"  Reason: {e.orig}",
            file=sys.stderr,
        )
        sys.exit(1)

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_changed BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        # 기존 데이터 이전: chunks.annotation_types → document_annotation_types
        # annotation_types 컬럼이 아직 존재하는 경우에만 실행
        col_exists = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='chunks' AND column_name='annotation_types'"
        )).fetchone()
        if col_exists:
            conn.execute(text(
                "ALTER TABLE chunks ALTER COLUMN annotation_types TYPE JSONB "
                "USING annotation_types::jsonb"
            ))
            # object 형태 JSONB: key-value 합산
            conn.execute(text("""
                INSERT INTO document_annotation_types (id, document_id, annotation_types)
                SELECT gen_random_uuid()::text, c.document_id,
                       jsonb_object_agg(kv.key, kv.value)
                FROM chunks c, jsonb_each(c.annotation_types) kv
                WHERE c.annotation_types IS NOT NULL
                  AND jsonb_typeof(c.annotation_types) = 'object'
                GROUP BY c.document_id
                ON CONFLICT (document_id) DO NOTHING
            """))
            # array 형태 JSONB (예: ["highlight","memo"]): key→true 객체로 변환하여 합산
            conn.execute(text("""
                WITH array_chunks AS (
                    SELECT document_id, annotation_types
                    FROM chunks
                    WHERE annotation_types IS NOT NULL
                      AND jsonb_typeof(annotation_types) = 'array'
                )
                INSERT INTO document_annotation_types (id, document_id, annotation_types)
                SELECT gen_random_uuid()::text, ac.document_id,
                       jsonb_object_agg(elem, 'true'::jsonb)
                FROM array_chunks ac,
                     LATERAL jsonb_array_elements_text(ac.annotation_types) elem
                GROUP BY ac.document_id
                ON CONFLICT (document_id) DO NOTHING
            """))
            conn.execute(text(
                "ALTER TABLE chunks DROP COLUMN annotation_types"
            ))
        conn.commit()

    url = engine.url
    print(f"[DB] Connected to PostgreSQL: {url.host}:{url.port}/{url.database}")
