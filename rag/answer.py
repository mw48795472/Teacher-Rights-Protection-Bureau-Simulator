"""근거 기반 답변. ANTHROPIC_API_KEY 가 있으면 Claude로 답을 쓰고, 없으면 발췌만 돌려준다."""
from __future__ import annotations

import os

from .retriever import Hit

SYSTEM = (
    "너는 경기도교육청 교권보호단 관련 법규·정책 자료를 설명하는 조교다. "
    "주어진 자료 안의 내용으로만 한국어로 답하고, 문장마다 근거 자료 번호를 [1]처럼 붙여라. "
    "자료에 없는 내용은 '자료에서 확인되지 않습니다'라고 말하라. "
    "'원문 확인 필요' 표시가 붙은 자료를 인용할 때만 원문 확인이 필요하다고 덧붙여라. "
    "'요약·원문 링크' 자료는 원문 링크가 있는 출처이므로 그런 경고를 붙이지 마라."
)


def extractive(question: str, hits: list[Hit]) -> str:
    if not hits:
        return "관련 자료를 찾지 못했습니다."
    lines = [f"**[{i}] {h.doc.title}**\n\n{h.doc.text}" for i, h in enumerate(hits, 1)]
    return "\n\n".join(lines)


def answer(question: str, hits: list[Hit]) -> tuple[str, bool]:
    """(답변, LLM 사용 여부)"""
    if not os.environ.get("ANTHROPIC_API_KEY") or not hits:
        return extractive(question, hits), False
    import anthropic

    context = "\n\n".join(
        f"[{i}] {h.doc.title} (신뢰도 {h.doc.reliability}{', ' + h.doc.source_tag if h.doc.source_tag else ''})\n{h.doc.text}"
        for i, h in enumerate(hits, 1)
    )
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"자료:\n{context}\n\n질문: {question}"}],
        )
    except anthropic.APIStatusError as e:
        return f"Claude 호출 실패({e.status_code}). 검색 결과만 보여드립니다.\n\n" + extractive(question, hits), False
    except anthropic.APIConnectionError:
        return "Claude에 연결하지 못했습니다. 검색 결과만 보여드립니다.\n\n" + extractive(question, hits), False
    if resp.stop_reason == "refusal":
        return "모델이 답변을 거절했습니다. 검색 결과만 보여드립니다.\n\n" + extractive(question, hits), False
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, True
