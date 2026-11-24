"""에이전트 실행 기록을 '핵심 장면 + 이론과의 대응'으로 줄인다.

전체 대본은 장면이 20개를 넘어 읽기 길다. 여기서는
1) 판정이 의미 있는 장면(차단·조건부·침해 탐지·흘러간 절차·교사가 직접 찾아감·결말)만 한 줄로 남기고
   나머지 허용 절차는 흐름 한 줄로 접으며,
2) 이 실행이 이론 탭의 가설(H1·H6, Gulick 조정)을 어떻게 보여 주는지 표로 정리한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .runner import AgentRun, Turn

# 피해 교원이 도움을 받으려고 직접 찾아가는 행동 (H1: 찾아가는 창구 수)
SEEK = {"지원요청", "위원회심의요청", "분쟁조정신청", "행정절차처리"}
# 결말을 만드는 행동
MILESTONE = {"위원회심의·조치", "수사기관고발", "사안종결"}


def short(text: str, n: int = 48) -> str:
    """첫 문장만, n자 넘으면 자른다."""
    t = (text or "").strip()
    for sep in (". ", "다. ", "요. "):
        if sep in t:
            t = t.split(sep)[0] + sep.strip()
            break
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


@dataclass
class Moment:
    no: int
    actor: str
    intent: str
    what: str          # 한 줄 요점
    badge: str         # 허용 / 조건부 허용 / 차단 / 침해 / 흘러감
    why: str = ""      # 판정 요지 한 줄 (필요할 때만)


@dataclass
class Flow:
    """핵심 장면 사이에 지나간 허용 절차 묶음."""
    steps: list[str] = field(default_factory=list)


def _is_key(t: Turn, seek_seen: int) -> bool:
    a, v = t.review.action, t.review.verdict
    return (v.decision != "허용" and v.category != "근거 불충분") or v.category in ("교육활동 침해 해당", "권한 초과") \
        or bool(t.unhandled) or a.intent in MILESTONE or (t.actor == "피해 교원" and a.intent in SEEK and seek_seen > 1)


def _moment(t: Turn, seek_seen: int) -> Moment:
    a, v = t.review.action, t.review.verdict
    what = short(a.description)
    why = ""
    if v.decision == "차단":
        badge = "차단"
        alt = f" → 대신 {v.alternative_actor or t.actor}의 '{v.alternative_intent}'(으)로" if v.alternative_intent else ""
        why = f"법에 막혔어요 ({v.category}){alt}"
    elif v.category == "교육활동 침해 해당":
        badge, why = "침해", "교육활동 침해예요 → 보호 조치와 위원회가 필요해요"
    elif v.decision == "조건부 허용":
        badge, why = "조건부", short(v.condition or v.category, 40)
    else:
        badge = "허용"
    if t.unhandled:
        badge = "흘러감" if badge == "허용" else badge
        why = (why + " · " if why else "") + f"그런데 {', '.join(t.unhandled)}을(를) 챙길 사람이 없어요"
    if t.actor == "피해 교원" and a.intent in SEEK and seek_seen > 1:
        why = (why + " · " if why else "") + f"선생님이 직접 찾아간 {seek_seen}번째 곳"
    return Moment(t.n, t.actor, a.intent, what, badge, why)


def key_moments(run: AgentRun) -> list[Moment | Flow]:
    out: list[Moment | Flow] = []
    seek = 0
    for t in run.turns:
        if t.actor == "피해 교원" and t.review.action.intent in SEEK:
            seek += 1
        if _is_key(t, seek):
            out.append(_moment(t, seek))
        elif t.review.action.intent != "기타":
            if not out or not isinstance(out[-1], Flow):
                out.append(Flow())
            out[-1].steps.append(t.review.action.intent)
    return out


def teacher_seeks(run: AgentRun) -> int:
    return sum(t.actor == "피해 교원" and t.review.action.intent in SEEK for t in run.turns)


def bottom_line(run: AgentRun) -> str:
    """구조별 결말 한 문장."""
    m = run.metrics
    parts = [f"{m['행동 수']}장면", f"선생님이 직접 찾아간 곳 {teacher_seeks(run)}곳"]
    if m["권한 초과"]:
        parts.append(f"법에 막힌 행동 {m['권한 초과']}번")
    if m["처리 주체 없는 후속 절차"]:
        parts.append(f"놓친 절차 {m['처리 주체 없는 후속 절차']}건")
    return " · ".join(parts) + (" · 사건 마무리 ✔" if run.closed else " · 아직 진행 중")


# ── 이론과의 대응 ──

VERDICT_TEXT = {"부합": "✅ 이론대로", "부분 부합": "⚠️ 절반쯤", "불일치": "❌ 이론과 달라요", "해당 없음": "– 비교 불가"}


def theory_rows(runs: dict[str, AgentRun]) -> list[dict]:
    """{구조 key: run} → 가설별 행. 비교할 구조가 없으면 그 행은 뺀다.
    키: 가설, 이론, 질문(q), 예측, 이번 실행, 한 줄 설명(say), 판정."""
    rows = []
    I, D, X = runs.get("integrated"), runs.get("distributed"), runs.get("drama")

    if X or I:
        xb = X.metrics["권한 초과"] if X else None
        ib = I.metrics["권한 초과"] if I else None
        obs = " · ".join(s for s in [f"드라마식 {xb}번" if X else "", f"교권보호단 {ib}번" if I else ""] if s)
        if X and I:
            v = "부합" if xb > 0 and ib == 0 else ("부분 부합" if xb > ib else "불일치")
            say = f"요원이 직접 제압·조사하려던 행동은 {xb}번 법에 막혔고, 교권보호단은 {ib}번 막혔어요."
        elif X:
            v = "부합" if xb > 0 else "불일치"
            say = f"요원이 직접 제압·조사하려던 행동이 {xb}번 법에 막혔어요."
        else:
            v = "부합" if ib == 0 else "불일치"
            say = f"교권보호단은 법에 막힌 행동이 {ib}번이었어요."
        rows.append({"가설": "H6", "이론": "법적 권한과 공식 구조", "q": "드라마처럼 밀어붙이면 통할까?",
                     "예측": "드라마식 강제 개입(제압·직접 조사)은 권한 초과로 막히고, 조정 중심 구조는 막히지 않는다",
                     "이번 실행": f"권한 초과 차단: {obs}", "say": say, "판정": v})

    if I and D:
        ni, nd = teacher_seeks(I), teacher_seeks(D)
        rows.append({"가설": "H1", "이론": "Lawrence & Lorsch · Gulick (통합)",
                     "q": "전담관이 있으면 선생님이 덜 뛰어다닐까?",
                     "예측": "주 담당 전담관이 있으면 교사가 직접 찾아가는 창구가 줄어든다",
                     "이번 실행": f"교사가 찾아간 창구: 분산 {nd}곳 → 교권보호단 {ni}곳",
                     "say": f"선생님이 직접 찾아간 곳이 {nd}곳에서 {ni}곳으로 줄었어요.",
                     "판정": "부합" if ni < nd else "불일치"})
        ui, ud = I.metrics["처리 주체 없는 후속 절차"], D.metrics["처리 주체 없는 후속 절차"]
        rows.append({"가설": "H1 보조", "이론": "Gulick (분업과 조정)", "q": "챙겨 줄 사람이 없으면 어떻게 될까?",
                     "예측": "조정자가 없으면 침해 뒤 보호조치·위원회 회부를 챙길 주체가 없다",
                     "이번 실행": f"흘러간 후속 절차: 분산 {ud}건 → 교권보호단 {ui}건",
                     "say": f"보호조치·위원회 회부처럼 놓친 절차가 분산 구조 {ud}건, 교권보호단 {ui}건이었어요.",
                     "판정": "부합" if ud > ui else ("해당 없음" if ud == ui == 0 else "불일치")})
    return rows


def takeaway(rows: list[dict]) -> str:
    """한 문장 결론."""
    if not rows:
        return "구조를 둘 이상(예: 교권보호단과 드라마식) 고르면 이론과 비교해 볼 수 있어요."
    ok = [r["가설"] for r in rows if r["판정"] == "부합"]
    bad = [r["가설"] for r in rows if r["판정"] in ("불일치", "부분 부합")]
    s = ""
    if bad:
        s += f"{', '.join(bad)}은(는) 이번엔 예측과 다르게 나왔어요. 한 번 더 돌려 보면 좋겠어요. "
    if ok and not bad:
        s = ("결국 선생님을 지켜 준 건 요원의 힘이 아니라, 사안을 한데 묶어 주는 전담관이었어요. "
             "이론 탭의 결론(통합·조정 장치가 실효성을 만든다)과 같은 이야기예요. ") + s
    return s.strip()
