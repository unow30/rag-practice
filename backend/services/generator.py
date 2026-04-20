import os
from typing import AsyncIterator, List

from langchain.schema import Document

LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

SYSTEM_PROMPT = """당신은 업로드된 문서를 기반으로 질문에 답하는 어시스턴트입니다.

규칙:
1. 반드시 아래 제공된 문서 컨텍스트에 근거하여 답변하세요.
2. 컨텍스트에 없는 내용은 절대 추측하거나 생성하지 마세요.
3. 문서에서 답변할 수 없는 질문에는 정확히 다음과 같이 말하세요: "문서에서 관련 정보를 찾을 수 없습니다."
4. 가능하면 구체적인 수치, 날짜, 고유명사를 원문 그대로 인용하세요.
5. 표나 그래프에서 근거를 찾은 경우, 해당 내용을 텍스트로 설명하세요."""


def _format_annotations(annotations: dict) -> str:
    """주석 딕셔너리를 LLM이 이해할 수 있는 텍스트로 변환한다."""
    if not annotations:
        return ""
    label_map = {
        "highlight": "색상 강조",
        "underline": "밑줄",
        "strikeout": "취소선",
        "memo": "메모",
    }
    lines = []
    for key, items in annotations.items():
        label = label_map.get(key, key)
        if key == "memo":
            for entry in items:
                content = entry.get("content", "")
                anchor = entry.get("anchor", "")
                note = f'[{label}] "{anchor}" → {content}' if anchor else f"[{label}] {content}"
                lines.append(note)
        else:
            for span in items:
                lines.append(f"[{label}] {span}")
    return "\n".join(lines)


def format_docs(docs: List[Document]) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        header = f"[출처 {i}] 문서: {meta.get('document_name', '알 수 없음')}, 페이지: {meta.get('page', '?')}"
        body = doc.page_content
        annot_text = _format_annotations(meta.get("annotations", {}))
        if annot_text:
            body += f"\n\n[사용자 주석]\n{annot_text}"
        parts.append(f"{header}\n{body}")
    return "\n\n---\n\n".join(parts)


def build_sources(docs: List[Document]) -> List[dict]:
    sources = []
    for doc in docs:
        meta = doc.metadata
        sources.append({
            "document_id": meta.get("doc_id", ""),
            "document_name": meta.get("document_name", ""),
            "page_number": meta.get("page", 0),
            "content_snippet": doc.page_content[:200],
            "relevance_score": round(meta.get("rerank_score", meta.get("score", 0.0)), 4),
        })
    return sources


async def generate_stream(
    question: str,
    context_docs: List[Document],
) -> AsyncIterator[str]:
    """LLM 스트리밍 답변을 토큰 단위로 yield한다."""
    context = format_docs(context_docs)
    user_message = f"[컨텍스트]\n{context}\n\n[질문]\n{question}"

    if LLM_MODEL.startswith("claude"):
        async for token in _stream_claude(user_message):
            yield token
    else:
        async for token in _stream_openai(user_message):
            yield token


async def _stream_claude(user_message: str) -> AsyncIterator[str]:
    import anthropic
    import asyncio

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    loop = asyncio.get_event_loop()

    def _sync_stream():
        tokens = []
        with client.messages.stream(
            model=LLM_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                tokens.append(text)
        return tokens

    tokens = await asyncio.wait_for(
        loop.run_in_executor(None, _sync_stream),
        timeout=AI_TIMEOUT,
    )
    for token in tokens:
        yield token


async def _stream_openai(user_message: str) -> AsyncIterator[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    stream = await client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        stream=True,
        timeout=AI_TIMEOUT,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
