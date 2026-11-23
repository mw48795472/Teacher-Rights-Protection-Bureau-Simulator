"""행위자 에이전트. 역할의 성향대로 다음 행동 하나를 제안한다."""
from __future__ import annotations

from .llm import LLMUnavailable, call_structured
from .models import INTENTS, Action
from .roles import ROLES, AgentStructure

SYSTEM_TMPL = """너는 교권보호 사안 시뮬레이션 속 '{role}' 역할을 맡은 에이전트다.
성향: {persona}

규칙:
- 이 역할이 지금 시점에 현실적으로 할 법한 행동 하나만 고른다. 정답처럼 행동하지 말고 성향대로 행동한다.
- 네가 하려는 행동은 실행 전에 컴플라이언스 심사를 받는다. 이전에 차단된 행동과 그 이유를 참고하라.
- notify에는 이 행동 뒤에 움직여야 할 역할을 '등장 역할' 목록에서만 고른다.
- 할 일이 끝났다고 판단되면 intent를 "사안종결"로 한다 (주 담당 역할일 때만).
- line에는 이 장면에서 이 인물이 실제로 할 법한 대사 한 마디를 인물의 말투로 쓴다 (드라마 대본에 그대로 들어간다).
- 한국어로 짧게."""


class ActorAgent:
    def __init__(self, role: str, structure: AgentStructure):
        self.role = role
        self.structure = structure

    def decide(self, case_text: str, history: list[str], hints: list[str], turn: int) -> tuple[Action, str]:
        try:
            return self._llm(case_text, history, hints), "llm"
        except LLMUnavailable:
            return scripted_action(self.role, self.structure, history, turn), "offline"

    def _llm(self, case_text, history, hints) -> Action:
        system = SYSTEM_TMPL.format(role=self.role, persona=ROLES[self.role].persona)
        others = [r for r in self.structure.roles if r != self.role]
        user = (
            f"## 조직 구조\n{self.structure.name}: {self.structure.description}\n"
            f"주 담당 역할: {self.structure.lead}\n\n## 사안\n{case_text}\n\n"
            "## 지금까지의 진행\n" + ("\n".join(history[-14:]) or "(아직 없음)") +
            ("\n\n## 너에게 온 요청·심사 결과\n" + "\n".join(hints) if hints else "") +
            f"\n\n## 등장 역할\n{', '.join(others)}\n\n## 고를 수 있는 행동 유형\n{', '.join(INTENTS)}"
        )
        a = call_structured(system, user, Action, effort="low", max_tokens=4000)
        a.notify = [n for n in a.notify if n in self.structure.roles and n != self.role]
        return a


# ── 오프라인 예시 스크립트 (키가 없을 때 흐름 확인용) ──

def _done(history: list[str], role: str, intent: str) -> bool:
    return any(h.startswith(f"{role}:") and f"[{intent}]" in h for h in history)


def scripted_action(role: str, s: AgentStructure, history: list[str], turn: int) -> Action:
    def A(intent, desc, notify=(), target=""):
        return Action(intent=intent, description=desc, target=target,
                      notify=[n for n in notify if n in s.roles], rationale="오프라인 예시 스크립트")

    if role == "학부모":
        if not _done(history, role, "민원제기"):
            return A("민원제기", "담임 교사의 다툼 중재가 편파적이었다며 학교에 항의 민원을 넣는다.", ["학교장", "피해 교원"], "학교")
        if not _done(history, role, "폭언·위협"):
            return A("폭언·위협", "교사에게 전화로 '가만두지 않겠다'며 폭언하고 반복 민원을 예고한다.", ["피해 교원"], "피해 교원")
        if not _done(history, role, "분쟁조정신청"):
            return A("분쟁조정신청", "교사와의 갈등을 조정해 달라며 학교에 분쟁조정 신청서(서식 5)를 낸다.",
                     ["지역교권보호위원회"], "피해 교원")
        return A("소송제기", "교사를 상대로 민사 소송을 제기한다.", ["피해 교원"], "피해 교원")
    if role == "피해 교원":
        if s.key == "distributed":
            for target, intent in (("학교장", "지원요청"), ("지역교권보호지원센터", "지원요청"),
                                   ("교육지원청 담당자", "지원요청"), ("지역교권보호위원회", "위원회심의요청")):
                if not any(h.startswith("피해 교원:") and target in h for h in history):
                    return A(intent, f"{target}에 직접 찾아가 상황을 처음부터 설명하고 도움을 요청한다.", [target], target)
            return A("사안종결", "더 요청할 곳이 없어 혼자 대응을 이어간다.")
        if not _done(history, role, "지원요청"):
            nxt = "교권보호국 요원" if s.key == "drama" else "교권보호 119"
            return A("지원요청", f"{nxt}에 연락해 피해 사실을 알린다.", [nxt], nxt)
        if s.key == "integrated" and _done(history, "교육지원청 담당자", "사안조사") and not _done(history, role, "의견서제출"):
            return A("의견서제출", "전담관과 함께 서면 의견서(서식 11-1)를 써서 위원회에 낸다.", ["지역교권보호위원회"],
                     "지역교권보호위원회")
        return A("기타", "수업을 이어가며 전담관 안내를 기다린다.")
    if role == "학교장":
        office = ["교육지원청 담당자"]
        if not _done(history, role, "분리조치"):
            return A("분리조치", "피해 교원의 분리 의사를 확인(서식 2)하고 가해 학생을 즉시 분리한다.", ["학교장"], "학생")
        if not _done(history, role, "참고인진술"):
            return A("참고인진술", "관련 학생·보호자 의견서(서식 3)와 목격한 교사·학생의 참고인 진술서(서식 4)를 받고 "
                     "발생보고서(서식 6)를 교육지원청에 낸다.", office, "교육지원청")
        return A("학부모면담", "학부모를 만나 진정시키려 하고, 교사에게는 상위 기관 문의를 권한다.", ["피해 교원"], "학부모")
    if role == "교권보호 119":
        return A("사안접수", "사안을 접수해 중대 사안으로 분류하고 상근 전담관에게 배정한다.", ["상근 전담관", "교육감"])
    if role == "상근 전담관":
        steps = [("초기상담", "피해 교원과 1:1 초기 상담을 하고 필요한 지원을 확인한다.", ["피해 교원"]),
                 ("지원계획수립", "법률·상담 지원이 필요하다고 보고 비상근 전문가를 연결한다.",
                  ["비상근 전담관(법률)", "비상근 전담관(상담)"]),
                 ("위원회심의요청", "침해 여부 심의를 위해 위원회에 자료를 제출한다.", ["지역교권보호위원회"]),
                 ("사후관리", "교원의 회복과 교육활동 복귀를 점검한다.", ["피해 교원"]),
                 ("사안종결", "지원을 마치고 사후 관리 단계로 넘긴다.", [])]
        for intent, desc, notify in steps:
            if not _done(history, role, intent):
                return A(intent, desc, notify)
        return A("사안종결", "지원을 마치고 사후 관리 단계로 넘긴다.")
    if role == "비상근 전담관(법률)":
        return A("법률자문", "소송 대응 방향과 형사 고발 가능성을 자문한다.", ["상근 전담관"], "피해 교원")
    if role in ("비상근 전담관(상담)", "지역교권보호지원센터"):
        return A("심리상담", "피해 교원의 심리 상태를 점검하고 상담을 시작한다.", [], "피해 교원")
    if role == "교육지원청 담당자":
        if not _done(history, role, "사안조사"):
            return A("사안조사", "발생보고서를 바탕으로 사안을 조사해 조사보고서(서식 10)를 만들고, 당사자에게 위원회 "
                     "출석통지서(서식 11)를 보낸다.", ["지역교권보호위원회", "피해 교원"], "피해 교원")
        return A("행정절차처리", "민원 처리 절차를 안내하고 서류 제출을 요청한다.", [], "피해 교원")
    if role == "교육감":
        if not _done(history, role, "수사기관고발"):
            return A("수사기관고발", "중대 사안으로 지정하고 교육청 명의로 학부모를 고발한다.", ["수사기관"], "학부모")
        return A("기타", "진행 상황을 보고받는다.")
    if role == "지역교권보호위원회":
        if any("[분쟁조정신청]" in h for h in history) and not _done(history, role, "분쟁조정"):
            return A("분쟁조정", "학부모의 분쟁조정 신청을 받아 양측 의견을 듣고 조정안을 제시한다.", ["피해 교원"], "학부모")
        return A("위원회심의·조치", "교육활동 침해로 인정하고 보호자에게 특별교육 이수 조치를 의결한다.", ["피해 교원"], "학부모")
    if role == "수사기관":
        return A("수사착수", "고발 사건을 접수해 수사를 시작한다.", [])
    if role == "교권보호국 요원":
        if not _done(history, role, "현장출동"):
            return A("현장출동", "학교로 즉시 출동한다.", [], "학교")
        if not _done(history, role, "물리적제지"):
            return A("물리적제지", "학부모를 교무실에서 강제로 끌어내고 학생을 위압적으로 훈계한다.", [], "학부모")
        if not _done(history, role, "사실조사"):
            return A("사실조사", "학부모와 학생을 따로 불러 직접 진술을 받아 침해 여부를 가리려 한다.", [], "학부모")
        return A("사안종결", "상황이 정리됐다고 보고 철수한다.")
    return A("기타", "상황을 지켜본다.")
