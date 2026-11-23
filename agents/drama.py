"""에이전트 실행 기록을 한 편의 드라마 대본으로 엮는다.

장면(S#)마다 장소·지문·대사를 두고, 컴플라이언스 판정은 화면 자막으로 넣는다.
행위자 에이전트가 대사(line)를 썼으면 그대로 쓰고, 오프라인 예시 모드처럼 대사가 없으면
행동 유형별 연출용 예시 대사를 쓴다. 사건의 흐름(누가 무엇을 했고 무엇이 막혔는지)은 실행 기록 그대로다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .roles import ROLES, STRUCTURES
from .runner import AgentRun

# 인물이 주로 있는 곳 (장면 머리말)
PLACE = {
    "학부모": "학부모의 집 / 전화", "피해 교원": "교실, 방과 후", "학교장": "교장실",
    "교권보호 119": "교권보호단 접수실", "상근 전담관": "교권보호단 사무실",
    "비상근 전담관(법률)": "법률사무소", "비상근 전담관(상담)": "상담실", "교육감": "교육감실",
    "지역교권보호위원회": "교육지원청 회의실", "수사기관": "경찰서", "지역교권보호지원센터": "교권보호지원센터",
    "교육지원청 담당자": "교육지원청 사무실", "교권보호국 요원": "학교 복도",
}

# 행동 유형별 연출용 예시 대사 (대사가 없을 때만)
LINES = {
    "민원제기": "우리 애만 혼났다면서요? 이게 공정한 중재예요? 교장 선생님 나오라고 하세요.",
    "폭언·위협": "선생님, 이 일 그냥 안 넘어갑니다. 가만두지 않을 거예요.",
    "아동학대신고": "아동학대로 신고하겠습니다. 증거는 충분해요.",
    "소송제기": "법대로 하죠. 소장 보내겠습니다.",
    "분쟁조정신청": "위원회에서 제대로 따져 봤으면 합니다. 조정 신청할게요.",
    "지원요청": "어디에 말해야 할지 모르겠어요. 도와주실 수 있나요?",
    "의견서제출": "제가 겪은 일을 있는 그대로 적었습니다.",
    "사안접수": "접수했습니다. 중대 사안으로 분류해 바로 담당 전담관을 붙이겠습니다.",
    "초기상담": "선생님 혼자 감당하실 일 아닙니다. 지금부터 제가 끝까지 같이 갑니다.",
    "지원계획수립": "법률은 변호사님이, 마음 회복은 상담 선생님이 맡습니다. 연락은 제가 다 챙길게요.",
    "전문가연계": "필요한 분들 바로 연결해 드리겠습니다.",
    "법률자문": "소송은 이렇게 대응하시면 됩니다. 고발 여부도 함께 검토하죠.",
    "심리상담": "많이 지치셨죠. 오늘은 선생님 이야기부터 들을게요.",
    "갈등조정": "두 분 이야기를 차례로 들어 보겠습니다.",
    "행정절차처리": "서류는 이쪽에 내시면 됩니다. 처리 절차를 안내해 드릴게요.",
    "분리조치": "선생님 뜻을 확인했습니다. 오늘부터 해당 학생과 바로 분리하겠습니다.",
    "참고인진술": "그날 본 것을 있는 그대로 적어 주세요. 관련 학생과 보호자 의견도 받겠습니다.",
    "사안조사": "조사보고서 정리했습니다. 위원회 출석 통지 나갑니다.",
    "위원회심의요청": "침해 여부 판단은 위원회 몫입니다. 심의를 요청하고 자료는 제가 제출하겠습니다.",
    "위원회심의·조치": "교육활동 침해로 인정합니다. 보호자에게 특별교육 이수를 의결합니다.",
    "분쟁조정": "양측 의견을 들었습니다. 조정안을 제시하겠습니다.",
    "수사기관고발": "이번 사안은 1호 사안으로 지정합니다. 교육청 이름으로 고발하겠습니다.",
    "수사착수": "고발장 접수됐습니다. 수사 시작합니다.",
    "학부모면담": "어머님, 일단 진정하시고 말씀 나눠 보시죠.",
    "현장출동": "지금 바로 학교로 간다.",
    "물리적제지": "여기서 나가 주십시오. 지금 당장.",
    "사실조사": "한 명씩 들어와. 그날 무슨 일이 있었는지 내가 직접 듣겠다.",
    "침해여부판정": "이건 명백한 교권 침해다. 내가 판단하겠다.",
    "사후관리": "요즘 수업은 어떠세요? 복귀하시고 불편한 점 없으신지 확인하러 왔습니다.",
    "사안종결": "오늘로 사안은 종결합니다. 사후 관리는 계속 이어집니다.",
    "기타": "…….",
}

# 인물에 따라 다르게 말하는 경우
ROLE_LINES = {
    ("교권보호국 요원", "사안종결"): "상황 끝. 철수한다.",
    ("피해 교원", "사안종결"): "결국 제가 다 알아서 해야 하는 거네요.",
    ("피해 교원", "위원회심의요청"): "위원회 심의를 신청하려고 왔습니다. 서류는 제가 다 챙겨 왔어요.",
    ("지역교권보호지원센터", "심리상담"): "상담은 해 드릴 수 있는데, 법률 쪽은 따로 알아보셔야 해요.",
}
REPEAT_LINES = {
    "지원요청": "처음부터 다시 말씀드려야 하나요? …네, 그날 다툼을 말리고 나서부터요.",
}

ACTS = [  # (막 이름, 이 막을 여는 행동 유형)
    ("제1막 · 발단", set()),
    ("제2막 · 전개", {"지원요청", "사안접수", "초기상담", "분리조치", "현장출동"}),
    ("제3막 · 위기", {"사안조사", "참고인진술", "위원회심의요청", "분쟁조정신청", "물리적제지", "사실조사", "소송제기"}),
    ("제4막 · 결말", {"위원회심의·조치", "분쟁조정", "수사착수", "사후관리", "사안종결"}),
]


@dataclass
class Scene:
    no: int
    place: str
    actor: str
    direction: str          # 지문
    line: str               # 대사
    example_line: bool      # 연출용 예시 대사인가
    caption: str            # 판정 자막
    decision: str
    cites: list[str] = field(default_factory=list)
    unhandled: list[str] = field(default_factory=list)


@dataclass
class Script:
    title: str
    logline: str
    cast: list[tuple[str, str]]
    acts: list[tuple[str, list[Scene]]]
    ending: str


def _caption(t) -> str:
    v = t.review.verdict
    if v.decision == "차단":
        alt = f" → {v.alternative_actor or t.actor}의 '{v.alternative_intent}'(으)로" if v.alternative_intent else ""
        return f"컴플라이언스: 차단 ({v.category}){alt}"
    if v.category == "교육활동 침해 해당":
        return "컴플라이언스: 교육활동 침해에 해당 (보호 조치 필요)"
    if v.decision == "조건부 허용":
        return f"컴플라이언스: 조건부 허용 ({v.condition or v.category})"
    return ""


def build_script(run: AgentRun, scenario_name: str) -> Script:
    s = STRUCTURES[run.structure]
    acts: list[tuple[str, list[Scene]]] = [(ACTS[0][0], [])]
    level = 0
    seen: dict[tuple[str, str], int] = {}
    for t in run.turns:
        a, v = t.review.action, t.review.verdict
        for i in range(level + 1, len(ACTS)):
            if a.intent in ACTS[i][1]:
                level = i
                acts.append((ACTS[i][0], []))
                break
        line = (a.line or "").strip().strip('"“”')
        k = (t.actor, a.intent)
        seen[k] = seen.get(k, 0) + 1
        example = ROLE_LINES.get(k) or (REPEAT_LINES.get(a.intent) if seen[k] > 1 else None) \
            or LINES.get(a.intent, LINES["기타"])
        direction = a.description + (" 그러나 실행되지 못한다." if v.decision == "차단" else "")
        acts[-1][1].append(Scene(
            no=t.n, place=PLACE.get(t.actor, "학교"), actor=t.actor, direction=direction,
            line=line or example, example_line=not line,
            caption=_caption(t), decision=v.decision, cites=list(v.cited_ids), unhandled=list(t.unhandled)))
    acts = [(n, sc) for n, sc in acts if sc]
    m = run.metrics
    ending = (f"사안은 {'종결됐다' if run.closed else '아직 끝나지 않았다'}. 행동 {m['행동 수']}번 중 "
              f"{m['차단']}번이 법령·조례에 막혔고")
    ending += (f", 챙기는 사람이 없어 흘러간 후속 절차가 {m['처리 주체 없는 후속 절차']}건 남았다."
               if m["처리 주체 없는 후속 절차"] else ", 후속 절차는 모두 누군가 챙겼다.")
    ending += f" 피해 교원이 직접 움직인 장면은 {m['피해 교원이 직접 한 행동']}번이다."
    cast = [(r, ROLES[r].persona) for r in s.roles if any(t.actor == r for t in run.turns)]
    return Script(title=f"{scenario_name} — {s.name} 편", logline=s.description, cast=cast, acts=acts,
                  ending=ending)


def script_text(sc: Script) -> str:
    """내려받기·Claude 각색용 평문 대본."""
    out = [f"# {sc.title}", sc.logline, "", "## 등장인물"]
    out += [f"- {n}: {p}" for n, p in sc.cast]
    for act, scenes in sc.acts:
        out += ["", f"## {act}"]
        for x in scenes:
            out += [f"S#{x.no}. {x.place}", f"({x.direction})", f"{x.actor}: {x.line}"]
            if x.caption:
                out.append(f"[자막] {x.caption}")
            if x.unhandled:
                out.append(f"[자막] 아무도 챙기지 않은 절차: {', '.join(x.unhandled)}")
    out += ["", "## 에필로그", sc.ending]
    return "\n".join(out)


ADAPT_SYSTEM = """너는 한국 TV 드라마 작가다. 주어진 대본 초안을 한 편의 짧은 드라마 대본으로 각색한다.
규칙:
- 사건의 순서, 누가 무엇을 했는지, 무엇이 막혔는지(자막)는 초안 그대로 둔다. 새 사건·인물·이름·숫자를 지어내지 않는다.
- 장면 머리말(S#번호. 장소), 지문(괄호), 대사(인물: 대사) 형식을 지킨다. 대사는 인물의 성향대로 자연스럽게 다듬고, 장면당 2~4줄까지 늘려도 된다.
- [자막] 줄은 그대로 남긴다. 법적 판정은 자막으로만 보여 준다.
- 마지막에 '에필로그'를 두고, 이 구조에서 교사가 겪은 일을 조직이론(통합, 조정, 권한) 관점에서 두세 문장으로 맺는다.
- 한국어로."""


def adapt(text: str) -> tuple[str, bool]:
    """Claude로 대본 초안을 각색한다. 키가 없거나 실패하면 ("", False)."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "", False
    import anthropic

    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            max_tokens=8000,
            system=ADAPT_SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": text}],
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        return "", False
    if resp.stop_reason == "refusal":
        return "", False
    return "".join(b.text for b in resp.content if b.type == "text"), True
