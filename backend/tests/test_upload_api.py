"""T-13 v0 통합 테스트 — 업로드 API 검증"""
import io
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PATH", "./data/test_rag.db")
os.environ.setdefault("DATA_DIR", "./data/test")

from backend.main import app

client = TestClient(app)


def _fake_pdf(name: str = "test.pdf") -> tuple:
    content = b"%PDF-1.4 fake content"
    return ("files", (name, io.BytesIO(content), "application/pdf"))


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_invalid_type():
    resp = client.post(
        "/api/documents",
        files=[("files", ("test.txt", io.BytesIO(b"hello"), "text/plain"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "INVALID_FILE_TYPE"


def test_upload_too_large():
    large_content = b"x" * (51 * 1024 * 1024)
    resp = client.post(
        "/api/documents",
        files=[("files", ("large.pdf", io.BytesIO(large_content), "application/pdf"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "FILE_TOO_LARGE"


def test_list_documents_empty():
    resp = client.get("/api/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert "total" in data
