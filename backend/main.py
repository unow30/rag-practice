import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.documents import router as documents_router
from backend.models.database import init_db
from backend.services.file_watcher import start_file_watcher, stop_file_watcher

app = FastAPI(
    title="PDF RAG 대화형 웹 앱",
    description="PDF 문서를 업로드하고 자연어로 질문하는 RAG 시스템",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(chat_router)


@app.on_event("startup")
def on_startup():
    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(os.path.join(data_dir, "documents"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "indexes"), exist_ok=True)
    init_db()
    _recover_stuck_documents()
    start_file_watcher(os.path.join(data_dir, "documents"))


@app.on_event("shutdown")
def on_shutdown():
    stop_file_watcher()


def _recover_stuck_documents():
    """서버 재시작 시 처리 중 상태로 남은 문서를 FAILED로 복구한다."""
    from backend.models.database import SessionLocal
    from backend.models.document import Document, DocumentStatus

    processing = {
        DocumentStatus.PENDING,
        DocumentStatus.EXTRACTING,
        DocumentStatus.CHUNKING,
        DocumentStatus.EMBEDDING,
    }
    db = SessionLocal()
    try:
        stuck = db.query(Document).filter(Document.status.in_(processing)).all()
        if stuck:
            for doc in stuck:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "서버 재시작으로 인해 처리가 중단되었습니다."
            db.commit()
            import logging
            logging.getLogger(__name__).warning(
                "startup recovery: %d document(s) reset to FAILED %s",
                len(stuck),
                [d.name for d in stuck],
            )
    finally:
        db.close()


@app.get("/health")
def health_check():
    from backend.models.database import engine
    url = engine.url
    return {"status": "ok", "db": f"postgresql://{url.host}:{url.port}/{url.database}"}
