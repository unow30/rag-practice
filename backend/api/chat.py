import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.document import DocumentStatus, Document as DocModel
from backend.services.generator import build_sources, format_docs, generate_stream
from backend.services.retriever import retrieve

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── 인메모리 대화 저장소 ──────────────────────────────────────────
_conversations: Dict[str, dict] = {}


def _new_conversation(document_ids: List[str]) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "document_scope": document_ids,
        "messages": [],
        "created_at": time.time(),
    }


# ── 요청 스키마 ───────────────────────────────────────────────────
class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    question: str
    document_ids: Optional[List[str]] = None


# ── 엔드포인트 ────────────────────────────────────────────────────
@router.post("")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": "EMPTY_QUESTION", "message": "질문을 입력해 주세요."},
        )

    # 대상 문서 확인
    doc_query = db.query(DocModel).filter(DocModel.status == DocumentStatus.READY)
    if request.document_ids:
        doc_query = doc_query.filter(DocModel.id.in_(request.document_ids))
    ready_docs = doc_query.all()

    if not ready_docs:
        raise HTTPException(
            status_code=400,
            detail={"error": "NO_READY_DOCUMENTS", "message": "질의 가능한 문서가 없습니다."},
        )

    # 대화 세션 조회 또는 생성
    conv_id = request.conversation_id
    if conv_id and conv_id in _conversations:
        conversation = _conversations[conv_id]
    else:
        conversation = _new_conversation(request.document_ids or [])
        conv_id = conversation["id"]
        _conversations[conv_id] = conversation

    # 검색
    candidate_docs = retrieve(
        question=request.question,
        db=db,
        document_ids=request.document_ids,
    )

    async def event_stream():
        start_ms = int(time.time() * 1000)
        full_answer = []

        try:
            async for token in generate_stream(request.question, candidate_docs):
                full_answer.append(token)
                yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            latency_ms = int(time.time() * 1000) - start_ms
            sources = build_sources(candidate_docs)
            msg_id = str(uuid.uuid4())

            # 대화 기록 저장
            conversation["messages"].append({
                "id": msg_id,
                "role": "user",
                "content": request.question,
            })
            conversation["messages"].append({
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "".join(full_answer),
                "sources": sources,
                "latency_ms": latency_ms,
            })

            done_payload = {
                "conversation_id": conv_id,
                "message_id": msg_id,
                "sources": sources,
                "latency_ms": latency_ms,
            }
            yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

        except asyncio.TimeoutError:
            error_payload = {
                "error": "AI_TIMEOUT",
                "message": "AI 서비스가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.",
            }
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            error_payload = {
                "error": "INTERNAL_ERROR",
                "message": str(e),
            }
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{conversation_id}", status_code=204)
def clear_conversation(conversation_id: str):
    if conversation_id in _conversations:
        del _conversations[conversation_id]
