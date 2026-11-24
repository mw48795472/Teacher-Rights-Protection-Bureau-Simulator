"""규제 컴플라이언스 에이전트.

행위자가 제안한 행동을 실행 전에 심사한다.
1) RAG로 관련 법령·조례·정책을 찾고
2) Claude가 그 자료만 근거로 허용 / 조건부 허용 / 차단을 판정하며 조문을 인용한다.
3) 사인(학부모 등)의 행동은 '교육활동 침해에 해당하는가'를, 공적 주체의 행동은
   '권한 안의 행동인가, 절차를 지켰는가'를 본다.

키가 없으면 오프라인 규칙 모드로 동작한다 (예시용, 판정 범위가 좁다).
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.labels import tag_suffix
from rag.retriever import Hit, Retriever

from .llm import LLMUnavailable, call_structured
from .models import Action, Verdict
from .roles import ROLES

SYSTEM = """너는 교육청의 규제 컴플라이언스 심사관이다. 교권보호 사안에서 각 주체가 하려는 행동을 실행 전에 심사한다.

원칙:
- 오직 '근거 자료'에 있는 내용으로만 판단한다. 자료에 없는 법 조항을 지어내지 않는다.
- 관련 근거가 자료에 없으면 category를 "근거 불충분"으로 두고, 행동이 명백히 위험하지 않으면 "조건부 허용"으로 판정하며 condition에 "원문 법령 확인 필요"를 적는다.
- 공적 주체(전담관, 교육감, 위원회 등)의 행동: 그 주체에게 권한이 있는지, 정해진 절차·연계 경로를 따랐는지 본다. 권한 밖이면 "차단"하고 권한 있는 주체와 대안 행동을 alternative_actor / alternative_intent로 제시한다.
- 사인(학부모, 피해 교원)의 행동: 행동 자체는 막지 않는다("허용"). 다만 교육활동 침해에 해당할 소지가 있으면 category를 "교육활동 침해 해당"으로 두고 triggers에 "보호조치"와 필요 시 "위원회"를 넣는다. 정당한 민원·신고·소송 제기 권리는 존중한다.
- 물리력이나 위압으로 학생·보호자를 통제하는 행동은 법적 근거가 없으면 차단한다.
- 당사자 몰래 하는 감시·미행·SNS 뒷조사·정보원 활용(비공개조사)은 사실상 조사·수사다. 근거 자료에 그 주체의 조사권·수사권이 없으면 "권한 초과"로 차단하고, 대상이 학생이면 개인정보와 아동 보호 문제도 reason에 짚는다.
- cited_ids에는 판단에 실제로 쓴 자료 id만 넣는다.
- 한국어로, reason은 핵심만 1~2문장."""


@dataclass
class Review:
    action: Action
    actor: str
    verdict: Verdict
    evidence: list[Hit]
    mode: str          # "llm" | "offline"
    note: str = ""


class ComplianceAgent:
    def __init__(self, retriever: Retriever, k: int = 6):
        self.r = retriever
        self.k = k

    def evidence(self, actor: str, action: Action) -> list[Hit]:
        queries = [
            f"{actor} {action.intent} {action.description}",
            f"{action.intent} 권한 절차",
        ]
        if actor in ROLES and not ROLES[actor].is_official:
            queries.append(f"교육활동 침해 {action.intent}")
        seen, out = set(), []
        for q in queries:
            for h in self.r.search(q, k=self.k):
                if h.doc.id not in seen:
                    seen.add(h.doc.id)
                    out.append(h)
        out.sort(key=lambda h: -h.score)
        return out[: self.k + 2]

    def review(self, actor: str, action: Action, case_text: str, history: list[str]) -> Review:
        hits = self.evidence(actor, action)
        try:
            v = self._llm(actor, action, case_text, history, hits)
            mode, note = "llm", ""
        except LLMUnavailable as e:
            v = offline_verdict(actor, action, history, self.r)
            mode, note = "offline", str(e)
            hits = [h for h in hits if h.doc.id in v.cited_ids] or hits[:2]
        valid = {h.doc.id for h in hits} | {d.id for d in self.r.docs}
        v.cited_ids = [c for c in v.cited_ids if c in valid]
        return Review(action, actor, v, hits, mode, note)

    def _llm(self, actor, action, case_text, history, hits) -> Verdict:
        role = ROLES.get(actor)
        kind = "공적 주체" if (role is None or role.is_official) else "사인(私人)"
        evidence = "\n\n".join(
            f"[{h.doc.id}] {h.doc.title} (신뢰도 {h.doc.reliability}"
            f"{tag_suffix(h.doc)})\n{h.doc.text}"
            for h in hits
        )
        user = (
            f"## 사안\n{case_text}\n\n## 지금까지 실행된 행동\n" + ("\n".join(history[-10:]) or "(없음)") +
            f"\n\n## 심사할 행동\n주체: {actor} ({kind})\n행동 유형: {action.intent}\n내용: {action.description}\n"
            f"상대방: {action.target or '-'}\n\n## 근거 자료\n{evidence}"
        )
        return call_structured(SYSTEM, user, Verdict, effort="medium")


# ── 오프라인 규칙 모드 (키가 없을 때 예시용) ──

OFFICIAL_OVERREACH = {"사실조사", "침해여부판정"}
PRIVATE_INFRINGEMENT = {"폭언·위협"}


def _cite(r: Retriever, query: str) -> list[str]:
    hits = r.search(query, k=1)
    return [hits[0].doc.id] if hits else []


def offline_verdict(actor: str, action: Action, history: list[str], r: Retriever) -> Verdict:
    role = ROLES.get(actor)
    official = role is None or role.is_official
    base = dict(condition="", alternative_intent="", alternative_actor="", triggers=[])
    if official and action.intent in OFFICIAL_OVERREACH and actor != "지역교권보호위원회":
        return Verdict(decision="차단", category="권한 초과",
                       cited_ids=_cite(r, "전담관 조사권 수사권 심의 의결권 없음 최종 판단"),
                       reason="교육활동 침해 여부 판단과 조사는 이 주체의 권한이 아니다. 침해 여부 심의는 지역교권보호위원회가 맡는다.",
                       **{**base, "alternative_intent": "위원회심의요청", "alternative_actor": actor, "triggers": ["위원회"]})
    if official and action.intent == "비공개조사":
        return Verdict(decision="차단", category="권한 초과",
                       cited_ids=_cite(r, "전담관 조사권 수사권 심의 의결권 없음 최종 판단"),
                       reason="당사자 몰래 하는 관찰·미행·정보 수집은 사실상 조사·수사인데, 교권보호 조직에는 조사권·수사권이 없다. "
                              "대상이 학생이면 개인정보와 아동 보호 문제까지 생긴다 (관련 법령 원문 확인 필요).",
                       **{**base, "alternative_intent": "위원회심의요청", "alternative_actor": actor, "triggers": ["위원회"]})
    if action.intent == "물리적제지":
        return Verdict(decision="차단", category="권한 초과",
                       cited_ids=_cite(r, "위압 물리력 학생 통제 법적 근거 없음"),
                       reason="위압이나 물리력으로 학생·보호자를 통제할 법적 근거가 없고 형사·민사 책임 분쟁을 부를 수 있다.",
                       **{**base, "alternative_intent": "수사기관고발", "alternative_actor": "교육감", "triggers": ["교육감"]})
    if not official:
        repeated = sum(1 for h in history if h.startswith(f"{actor}:") and "민원제기" in h)
        if action.intent in PRIVATE_INFRINGEMENT or (action.intent == "민원제기" and repeated >= 1):
            return Verdict(decision="허용", category="교육활동 침해 해당",
                           cited_ids=_cite(r, "악성 민원 교육활동 침해 보호"),
                           reason="반복적이거나 위협적인 민원은 교육활동 침해에 해당할 소지가 있어 보호 조치와 위원회 심의가 필요하다.",
                           **{**base, "triggers": ["보호조치", "위원회"]})
        return Verdict(decision="허용", category="적법", cited_ids=[],
                       reason="정당한 민원·신고·소송 제기 권리에 해당한다.", **base)
    if action.intent == "분쟁조정" and actor == "지역교권보호위원회":
        return Verdict(decision="허용", category="적법", cited_ids=_cite(r, "지역교권보호위원회 침해 심의 조치 분쟁 조정"),
                       reason="교원과 관련된 분쟁 조정은 지역교권보호위원회의 심의 사항이다.", **base)
    if action.intent == "위원회심의·조치" and actor == "지역교권보호위원회":
        return Verdict(decision="허용", category="적법", cited_ids=_cite(r, "지역교권보호위원회 침해 심의 조치"),
                       reason="교육활동 침해 여부 심의와 보호자 조치는 위원회의 권한이다.", **base)
    q = OFFLINE_DUTY_QUERY.get(action.intent)
    if q:
        return Verdict(decision="허용", category="적법", cited_ids=_cite(r, q),
                       reason="관련 자료의 업무 범위 안의 행동으로 보인다 (오프라인 규칙).", **base)
    return Verdict(decision="조건부 허용", category="근거 불충분", cited_ids=[],
                   reason="이 행동을 직접 다루는 자료를 찾지 못했다 (오프라인 규칙).",
                   **{**base, "condition": "원문 법령 확인 필요"})


OFFLINE_DUTY_QUERY = {
    "사안접수": "교권보호 119 콜센터 접수 현장 출동",
    "초기상담": "전담관 업무 초기 상담 지원계획 전문기관 연계",
    "지원계획수립": "전담관 업무 초기 상담 지원계획 전문기관 연계",
    "전문가연계": "전담관 배정 긴급성 전문성 공동 지원",
    "법률자문": "전담관 배정 긴급성 전문성 공동 지원",
    "심리상담": "전담관 배정 긴급성 전문성 공동 지원",
    "위원회심의요청": "지역교권보호위원회 침해 심의 조치 분쟁 조정",
    "사후관리": "전담관 업무 사후 관리 교육활동 복귀",
    "사안종결": "전담관 업무 사후 관리 교육활동 복귀",
    "수사기관고발": "교육감 1호 사안 지정 학부모 형사 고발",
    "분리조치": "즉시 분리 의사 확인서 분리",
    "참고인진술": "관련자 의견서 참고인 진술서 발생보고서",
    "사안조사": "사안 조사보고서 출석통지서 서면 의견서",
    "의견서제출": "사안 조사보고서 출석통지서 서면 의견서",
    "분쟁조정신청": "분쟁조정 신청서",
}
