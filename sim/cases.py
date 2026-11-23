"""교권침해 사안 생성기. 이론 개념(Perrow, Thompson)을 사안 속성으로 둔다."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SERVICES = ("상담", "법률", "행정", "수사연계", "갈등조정")

# 사안 유형별 필요한 지원 (팀 자료의 사례를 바탕으로 한 가정).
# weight 는 팀 가정 비율이다. 실제 추출 비율은 sim/calibration.case_weights() 가 정하며,
# config/measured.yaml 의 use.case_mix 가 true 면 실측(교보위 유형·교육감 의견 제출) 기반 비율을 쓴다.
CASE_TYPES = {
    "악성민원": {"needs": ("상담", "갈등조정", "법률"), "weight": 0.35},
    "무고성 아동학대 신고": {"needs": ("법률", "상담", "행정", "수사연계"), "weight": 0.25},
    "폭언·폭행": {"needs": ("상담", "수사연계", "행정"), "weight": 0.2},
    "민·형사 소송": {"needs": ("법률", "상담"), "weight": 0.1},
    "단순 상담": {"needs": ("상담",), "weight": 0.1},
}

PERROW = {  # (과업다양성 높음?, 분석가능성 높음?) -> 기술 유형
    (False, True): "일상적",
    (False, False): "장인",
    (True, True): "공학적",
    (True, False): "비일상적",
}

@dataclass
class Case:
    id: int
    type: str
    severity: int                 # 1 경미, 2 보통, 3 중대
    needs: tuple[str, ...]
    analyzable: bool              # 해결 절차가 명확한가 (Perrow 분석가능성)
    arrival: float = 0.0          # 근무시간(h)
    label: str = ""               # 시나리오 사안 이름
    office: str = ""              # 관할 교육지원청 (지도 모드)
    committee_wait: float = 0.0   # 위원회 심의까지 기다린 시간(h)
    # 결과 기록
    first_response: float | None = None
    closed: float | None = None
    contacts: int = 0             # 교사가 직접 접촉한 기관 수
    repeats: int = 0              # 같은 내용을 반복 진술한 횟수
    coordination: int = 0         # 기관·담당자 간 조정 메시지 수
    duplicates: int = 0           # 같은 업무를 두 기관이 중복 수행
    handoffs: int = 0             # 담당자 공백·교체
    misroutes: int = 0            # 잘못된 창구로 안내
    guard_blocks: int = 0         # 권한 밖 행동을 근거 조문으로 막은 횟수
    trace: list = field(default_factory=list)

    @property
    def variety_high(self) -> bool:
        return len(self.needs) >= 3

    @property
    def perrow(self) -> str:
        return PERROW[(self.variety_high, self.analyzable)]

    @property
    def interdependence(self) -> str:
        n = len(self.needs)
        if n >= 3:
            return "교호적"
        return "순차적" if n == 2 else "집합적"

    def log(self, t: float, actor: str, action: str, cite: str = "") -> None:
        self.trace.append({"t": round(t, 2), "day": round(t / 8, 2), "actor": actor,
                           "action": action, "cite": cite})


def random_case(rng: random.Random, arrival: float, case_id: int) -> Case:
    from .calibration import case_weights
    types = list(CASE_TYPES)
    w = case_weights()
    t = rng.choices(types, weights=[w[k] for k in types])[0]
    needs = list(CASE_TYPES[t]["needs"])
    # 일부 사안은 다른 유형이 겹친 복합 사안이 된다.
    if rng.random() < 0.15:
        extra = CASE_TYPES[rng.choice(types)]["needs"]
        needs += [n for n in extra if n not in needs]
        t = f"{t} (복합)"
    sev = rng.choices([1, 2, 3], weights=[0.45, 0.4, 0.15])[0]
    analyzable = rng.random() < (0.7 if len(needs) <= 2 else 0.35)
    return Case(case_id, t, sev, tuple(needs), analyzable, arrival)


def scenario_case(spec: dict, arrival: float, case_id: int) -> Case:
    return Case(case_id, spec["type"], int(spec["severity"]), tuple(spec["needs"]),
                bool(spec.get("analyzable", False)), arrival, label=spec["name"],
                office=spec.get("office", ""))
