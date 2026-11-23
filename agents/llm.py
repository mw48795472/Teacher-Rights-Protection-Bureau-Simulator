"""Claude 호출 공통부. 구조화 출력(Pydantic)으로 받는다."""
from __future__ import annotations

import os
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    """키가 없거나 호출이 실패해 오프라인 규칙 모드로 내려가야 할 때."""


def llm_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def call_structured(system: str, user: str, schema: type[T], effort: str = "medium",
                    max_tokens: int = 8000) -> T:
    if not llm_enabled():
        raise LLMUnavailable("ANTHROPIC_API_KEY 없음")
    import anthropic

    try:
        resp = _get_client().beta.messages.parse(
            model=model_name(),
            max_tokens=max_tokens,
            system=system,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
    except anthropic.RateLimitError as e:
        raise LLMUnavailable(f"요청 한도 초과: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(f"API 오류 {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable(f"연결 실패: {e}") from e
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("모델이 응답을 거절함")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise LLMUnavailable("응답이 잘렸거나 형식이 맞지 않음")
    return resp.parsed_output
