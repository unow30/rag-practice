import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.documents import router as documents_router
from backend.models.database import init_db

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


@app.get("/health")
def health_check():
    return {"status": "ok"}
