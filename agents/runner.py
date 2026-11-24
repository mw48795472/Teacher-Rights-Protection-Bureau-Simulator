"""에이전트 시뮬레이션 실행기.

행위자 에이전트가 행동을 제안 → 컴플라이언스 에이전트가 심사 → 허용된 행동만 실행되고,
차단되면 대안 행동을 할 역할에게 이유와 함께 차례가 넘어간다.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from rag.retriever import Retriever

from .actors import ActorAgent
from .compliance import ComplianceAgent, Review
from .roles import STRUCTURES


@dataclass
class Turn:
    n: int
    actor: str
    review: Review
    actor_mode: str
    unhandled: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        v, a = self.review.verdict, self.review.action
        return {
            "turn": self.n, "actor": self.actor, "actor_mode": self.actor_mode,
            "compliance_mode": self.review.mode,
            "action": a.model_dump(), "verdict": v.model_dump(),
            "evidence": [{"id": h.doc.id, "title": h.doc.title} for h in self.review.evidence],
            "unhandled_triggers": self.unhandled,
        }


@dataclass
class AgentRun:
    structure: str
    case_text: str
    turns: list[Turn]
    closed: bool

    @property
    def metrics(self) -> dict:
        vs = [t.review.verdict for t in self.turns]
        return {
            "행동 수": len(self.turns),
            "차단": sum(v.decision == "차단" for v in vs),
            "조건부 허용": sum(v.decision == "조건부 허용" for v in vs),
            "교육활동 침해 탐지": sum(v.category == "교육활동 침해 해당" for v in vs),
            "권한 초과": sum(v.category == "권한 초과" for v in vs),
            "근거 불충분": sum(v.category == "근거 불충분" for v in vs),
            "피해 교원이 직접 한 행동": sum(t.actor == "피해 교원" for t in self.turns),
            "처리 주체 없는 후속 절차": sum(len(t.unhandled) for t in self.turns),
            "종결": self.closed,
        }

    @property
    def mode(self) -> str:
        modes = ({t.review.mode for t in self.turns} | {t.actor_mode for t in self.turns}) - {"rule"}
        return "llm" if modes == {"llm"} else ("offline" if modes == {"offline"} else "mixed")

    def to_dict(self) -> dict:
        return {"structure": self.structure, "case": self.case_text, "closed": self.closed,
                "metrics": self.metrics, "turns": [t.to_dict() for t in self.turns]}


MAX_COUNTERPART_TURNS = 4


def route_trigger(trig: str, s) -> str | None:
    """후속 절차를 챙길 역할. 조정자가 없는 구조(주 담당 = 피해 교원)에서는 아무도 챙기지 않는다."""
    coordinator = s.lead if s.lead != "피해 교원" else None
    if trig in ("위원회", "보호조치"):
        return coordinator
    if trig in ("교육감", "수사기관"):
        return "교육감" if "교육감" in s.roles else coordinator
    return None


def case_text(spec: dict) -> str:
    return f"{spec['name']}: {spec.get('description', '')} (유형 {spec['type']}, 심각도 {spec['severity']})"


def run_agents(spec: dict, structure_key: str, retriever: Retriever, max_turns: int = 16,
               on_turn=None) -> AgentRun:
    s = STRUCTURES[structure_key]
    text = case_text(spec)
    compliance = ComplianceAgent(retriever)
    agents = {r: ActorAgent(r, s) for r in s.roles}
    queue: deque[str] = deque(s.entry)
    hints: dict[str, list[str]] = defaultdict(list)
    history: list[str] = []
    turns: list[Turn] = []
    closed = False

    def enqueue(role: str, front: bool = False):
        if role not in s.roles:
            return
        if role in queue:
            if not front:
                return  # 이미 차례를 기다리는 중이면 순서를 뒤로 밀지 않는다
            queue.remove(role)
        queue.appendleft(role) if front else queue.append(role)

    n, steps = 0, 0
    while n < max_turns and steps < max_turns * 2:
        steps += 1
        if not queue:
            queue.append(s.lead)
        actor = queue.popleft()
        action, amode = agents[actor].decide(text, history, hints.pop(actor, []), n + 1)
        if action.intent == "기타" and actor != s.lead:
            continue   # '지켜본다'·'기다린다' 같은 대기는 장면으로 치지 않고 심사도 하지 않는다 (실행 시간 단축)
        n += 1
        review = compliance.review(actor, action, text, history)
        v = review.verdict
        unhandled: list[str] = []

        if v.decision == "차단":
            history.append(f"{actor}: [{action.intent}] {action.description} → 차단({v.category})")
            alt = v.alternative_actor if v.alternative_actor in s.roles else actor
            hints[alt].append(f"컴플라이언스 차단: {actor}의 '{action.intent}'은(는) 할 수 없음. 이유: {v.reason}"
                              + (f" 대신 '{v.alternative_intent}'을(를) 검토하라." if v.alternative_intent else ""))
            enqueue(alt, front=True)
        else:
            tag = "" if v.decision == "허용" else f" (조건: {v.condition})"
            history.append(f"{actor}: [{action.intent}] {action.description}{tag}")
            for r in action.notify:
                enqueue(r)
            if action.intent == "사안종결" and actor == s.lead:
                closed = True
        for trig in v.triggers:
            role = route_trigger(trig, s)
            if role:
                hints[role].append(f"후속 절차 필요: {trig} (사유: {actor}의 {action.intent}). "
                                   "필요하면 권한 있는 기관에 요청하라.")
                enqueue(role)
            else:
                unhandled.append(trig)

        # 상대방(학부모)은 위원회 조치나 수사가 시작되기 전까지 계속 움직일 수 있다
        if actor == "학부모" and not any(k in h for h in history for k in ("[위원회심의·조치]", "[수사착수]")) \
                and sum(t.actor == "학부모" for t in turns) < MAX_COUNTERPART_TURNS - 1:
            enqueue("학부모")

        turn = Turn(n, actor, review, amode, unhandled)
        turns.append(turn)
        if on_turn:
            on_turn(turn)
        if closed:
            break
    return AgentRun(structure_key, text, turns, closed)
