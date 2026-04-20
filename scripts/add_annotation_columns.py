"""
chunks 테이블에 주석 컬럼 추가 마이그레이션

사용법:
    python scripts/add_annotation_columns.py

환경변수:
    DATABASE_URL  PostgreSQL 연결 문자열 (기본값: .env 파일 참조)

멱등성: IF NOT EXISTS 사용으로 중복 실행 시 오류 없음.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://rag-practice:rag-practice@localhost:5434/rag-practice",
)


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS annotation_types TEXT;")
    print("  annotation_types 컬럼 추가 완료 (또는 이미 존재)")

    cur.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS memo_content TEXT;")
    print("  memo_content 컬럼 추가 완료 (또는 이미 존재)")

    cur.close()
    conn.close()
    print("마이그레이션 완료.")


if __name__ == "__main__":
    run()
