import os
from typing import List

MULTI_QUERY = os.getenv("MULTI_QUERY", "false").lower() == "true"
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

_EXPAND_PROMPT = """다음 질문을 검색에 활용할 수 있도록 표현이 다른 2개의 변형 질문을 생성하세요.
원래 질문의 의도는 유지하되, 다른 어휘나 문장 구조를 사용하세요.
각 변형 질문을 줄바꿈으로 구분하여 번호 없이 출력하세요.

원래 질문: {question}"""


def expand_query(question: str) -> List[str]:
    """MULTI_QUERY가 비활성화된 경우 원 질문만 반환한다."""
    if not MULTI_QUERY:
        return [question]

    variants = _generate_variants(question)
    seen = set()
    result = []
    for q in [question] + variants:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            result.append(q)
    return result


def _generate_variants(question: str) -> List[str]:
    prompt = _EXPAND_PROMPT.format(question=question)

    if LLM_MODEL.startswith("claude"):
        return _expand_claude(prompt)
    return _expand_openai(prompt)


def _expand_claude(prompt: str) -> List[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    return [line.strip() for line in text.splitlines() if line.strip()]


def _expand_openai(prompt: str) -> List[str]:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content or ""
    return [line.strip() for line in text.splitlines() if line.strip()]
