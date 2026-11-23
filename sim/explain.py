"""시뮬레이션 결과 설명.

ANTHROPIC_API_KEY 가 있으면 Claude가 결과표 + 검색된 이론·조문을 근거로 발표용 설명을 쓴다.
없으면 숫자로 만든 규칙 기반 요약을 돌려준다.
"""
from __future__ import annotations

import os

import pandas as pd

from .metrics import METRICS

SYSTEM = """너는 조직이론 수업 팀 발표를 돕는 분석가다. 경기도교육청 교권보호단을 다룬 시뮬레이션 결과를 설명한다.
규칙:
- 한국어로, 발표에서 바로 말할 수 있는 문장으로 쓴다.
- 숫자는 결과표에 있는 값만 쓴다.
- 이론과 조문은 '근거 자료'에 있는 것만 인용하고, 문장 끝에 [1]처럼 자료 번호를 단다.
- 수업 개념 두 가지(① 조직환경: 개방체계·상황이론, ② 분업과 조정)에 묶어 설명한다.
- 처리시간·확률 대부분이 가정값이라는 점, 시뮬레이션은 실제 운영 효과의 증거가 아니라 이론의 논리를 보여주는 사고실험이라는 점을 마지막에 한 문장으로 밝힌다.
- '팀 요약' 표시 자료를 인용하면 원문 확인이 필요하다고 짧게 덧붙인다.
형식: ## 핵심 결과 (3줄 이내) / ## 왜 이런 차이가 나는가 (개념①·②) / ## 실효성 조건과 연결 / ## 한계"""

THEORY_QUERIES = [
    "분화와 통합 조정 부족", "교호적 상호의존 지속적 의사소통 상호조정",
    "비일상적 과업 전문가 판단 협의", "분업 조정 위계 구조적 통합",
    "환경 구조 적합성", "기계적 조직 유기적 조직",
    "업무 중복 연계절차", "업무매뉴얼", "비상근 전담관", "교육감 직속",
]


def gather_evidence(retriever, extra_queries: list[str] = ()) -> list:
    seen, hits = set(), []
    for q in [*THEORY_QUERIES, *extra_queries]:
        for h in retriever.search(q, k=1):
            if h.doc.id not in seen:
                seen.add(h.doc.id)
                hits.append(h)
    return hits


def table_text(summary: pd.DataFrame) -> str:
    cols = [c for c in METRICS if c in summary.columns]
    t = summary[cols].rename(columns={k: METRICS[k][0] for k in cols})
    return t.to_markdown() if hasattr(t, "to_markdown") else t.to_string()


def rule_based(summary: pd.DataFrame, base: str, target: str) -> str:
    a, b = summary.loc[base], summary.loc[target]

    def pct(x, y):
        return f"{(1 - y / x) * 100:.0f}%" if x else "-"

    lines = [
        "## 핵심 결과 (규칙 기반 요약, Claude 키 없음)",
        f"- 종결까지 평균 {a.closure_days:.1f}일 → {b.closure_days:.1f}일 ({pct(a.closure_days, b.closure_days)} 단축)",
        f"- 교사가 접촉한 기관 {a.contacts:.1f}곳 → {b.contacts:.1f}곳, 반복 진술 {a.repeats:.1f}회 → {b.repeats:.1f}회",
        f"- 대신 조정 메시지는 {a.coordination:.1f} → {b.coordination:.1f}건으로, 조정 부담이 교사에서 전담관으로 옮겨감",
        "",
        "## 해석 포인트",
        "- 개념② 분업과 조정: 분화된 기관을 연결하는 주 담당(전담관)이 생기면서 교사가 하던 조정을 조직이 맡음 (Gulick, Lawrence & Lorsch)",
        "- 교호적 상호의존 사안일수록 차이가 커지는지 '이론별 분석' 탭에서 확인 (Thompson, Perrow)",
    ]
    if b.duplicates > 0.05:
        lines.append(f"- 업무 중복이 사안당 {b.duplicates:.2f}건 남아 있음 → 조례 제17조 연계절차 조건")
    if b.handoffs > 0.05:
        lines.append(f"- 담당자 공백이 사안당 {b.handoffs:.2f}회 → 비상근 중심 운영의 연속성 한계")
    lines += ["", "## 한계", "- 처리시간·확률 대부분이 가정값이며, 결과는 실제 운영 효과의 증거가 아니라 이론의 논리를 보여주는 사고실험입니다."]
    return "\n".join(lines)


def explain(summary: pd.DataFrame, base: str, target: str, retriever, context: str = "") -> tuple[str, list, bool]:
    """(설명 마크다운, 근거 hits, LLM 사용 여부)"""
    hits = gather_evidence(retriever)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return rule_based(summary, base, target), hits, False
    import anthropic

    evidence = "\n".join(
        f"[{i}] {h.doc.title} (신뢰도 {h.doc.reliability}{'' if h.doc.verified else ', 팀 요약'}): {h.doc.text}"
        for i, h in enumerate(hits, 1)
    )
    prompt = (
        f"비교 기준 구조: {base}\n비교 대상 구조: {target}\n{context}\n\n"
        f"결과표 (사안당 평균):\n{table_text(summary)}\n\n근거 자료:\n{evidence}"
    )
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            max_tokens=6000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        return f"> Claude 호출 실패: {type(e).__name__}. 규칙 기반 요약으로 대신합니다.\n\n" + rule_based(summary, base, target), hits, False
    if resp.stop_reason == "refusal":
        return rule_based(summary, base, target), hits, False
    return "".join(b.text for b in resp.content if b.type == "text"), hits, True


def narrate_case(trace: list[dict], case_label: str, structure: str, retriever) -> tuple[str, bool]:
    """사안 1건의 처리 로그를 발표용 이야기로 풀어 쓴다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "", False
    import anthropic

    docs = {d.id: d for d in retriever.docs}
    lines = []
    for e in trace:
        cite = docs.get(e["cite"])
        ref = f" (근거: {cite.title})" if cite else ""
        lines.append(f"{e['day']:.1f}일차 · {e['actor']}: {e['action']}{ref}")
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            max_tokens=3000,
            system="로그에 있는 사실만으로, 피해 교사의 시점에서 사안이 어떻게 처리됐는지 한국어 5~7문장으로 풀어 써라. 조직이론 개념(통합, 조정, 상호의존)을 한두 번 자연스럽게 연결하라. 숫자를 지어내지 마라.",
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": f"구조: {structure}\n사안: {case_label}\n\n로그:\n" + "\n".join(lines)}],
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        return "", False
    if resp.stop_reason == "refusal":
        return "", False
    return "".join(b.text for b in resp.content if b.type == "text"), True
