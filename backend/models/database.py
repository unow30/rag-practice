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
    from backend.models.document import Document, Chunk  # noqa: F401

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

    url = engine.url
    print(f"[DB] Connected to PostgreSQL: {url.host}:{url.port}/{url.database}")
