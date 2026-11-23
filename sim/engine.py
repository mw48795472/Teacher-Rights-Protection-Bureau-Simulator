"""이산사건 시뮬레이션 엔진 (SimPy).

시간 단위는 근무시간(h)이고 하루는 8시간이다. 모든 처리시간·확률은 '가정'이며
대시보드에서 바꿀 수 있다. 실제 수치로 맞춘 값은 사안 유입량(하루 약 3건:
8.24 실무 투입 후 10.8까지 140건 이상 [아시아뉴스통신 10.8])뿐이다.

조직 구조는 두 종류다.
- distributed: 교사가 창구를 하나씩 직접 찾아간다. 기관 사이 정보는 교사를 거친다.
- integrated : 접수 → 상근 전담관(주 담당) 배정 → 필요한 전문가를 병렬로 연결한다.
               기관 사이 정보는 주 담당이 조정한다.
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import simpy
import yaml

from .cases import Case, random_case, scenario_case

HOURS_PER_DAY = 8
ROOT = Path(__file__).resolve().parent
STRUCTURES_DIR = ROOT / "structures"

# 업무별 처리시간 중앙값(근무시간, 가정)
WORK_MEDIAN = {"상담": 4.0, "법률": 10.0, "행정": 3.0, "수사연계": 2.0, "갈등조정": 6.0}
POLICE_DELAY_MEDIAN = 24.0      # 수사기관 접수·처리 대기 (가정, 3근무일)
NONREGULAR_MIX = {"법률": 0.25, "상담": 0.3, "수사연계": 0.15, "갈등조정": 0.15, "행정": 0.15}

# 각 행동의 근거를 찾을 검색어. 실제 조문이 수집되면 그 원문이 인용된다.
CITE_QUERIES = {
    "escalation": "교육감 직속 교권보호단 단장 총괄",
    "assign": "전담관 배정 긴급성 전문성 공동 지원",
    "officer_duty": "전담관 업무 초기 상담 지원계획 전문기관 연계",
    "guard": "전담관 조사권 수사권 심의 의결권 없음 최종 판단",
    "linkage": "기존 지원체계 업무 중복 연계절차",
    "manual": "업무매뉴얼 통일적 사안 접수 배정",
    "committee": "지역교권보호위원회 침해 심의 조치 분쟁 조정",
    "committee_rare": "교권보호위원회 개최 연 1회 분쟁 조정 거의 없음",
    "distributed": "업무 부서별 분산 피해 교사 절차 직접",
    "team": "상근 전담관 주 담당 비상근 센터 담당 함께 배치",
    "nonregular": "전담관 대부분 비상근",
}


def list_structures() -> dict[str, dict]:
    out = {}
    for p in sorted(STRUCTURES_DIR.glob("*.yaml")):
        out[p.stem] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return out


@dataclass
class SimConfig:
    structure: dict
    days: int = 60
    arrivals_per_day: float = 3.0
    seed: int = 7
    surge_day: int | None = None        # 언론 보도 등 환경 압력이 생기는 날
    surge_multiplier: float = 2.0
    surge_days: int = 7
    overrides: dict = field(default_factory=dict)
    # 지도 모드: 교육지원청별 사안 비중 {이름: 가중치}. 주어지면 위원회가 교육지원청마다 따로 열린다.
    offices: dict | None = None
    committee_capacity: int = 6         # 위원회 1회 심의 건수 (가정)

    @property
    def params(self) -> dict:
        return {**self.structure["params"], **self.overrides}


class Citer:
    """행동 → 근거 문서. Retriever가 없으면 빈 인용."""

    def __init__(self, retriever=None):
        self.r = retriever
        self.cache: dict[str, str] = {}

    def __call__(self, key: str) -> str:
        if self.r is None:
            return ""
        if key not in self.cache:
            hits = self.r.search(CITE_QUERIES[key], k=1)
            self.cache[key] = hits[0].doc.id if hits else ""
        return self.cache[key]


class Simulation:
    def __init__(self, cfg: SimConfig, retriever=None):
        self.cfg = cfg
        self.p = cfg.params
        # 공통 난수: 사안 도착·속성은 구조와 무관하게 같은 흐름을 쓴다 (공정한 비교)
        self.arr_rng = random.Random(cfg.seed)
        self.rng = random.Random(cfg.seed + 10_000)
        self.env = simpy.Environment()
        self.cite = Citer(retriever)
        self.cases: list[Case] = []
        self._ids = itertools.count(1)
        self._scenario_ids = itertools.count(9001)
        self.geo_rng = random.Random(cfg.seed + 20_000)
        self.office_names = list(cfg.offices or {})
        self.office_w = [cfg.offices[k] for k in self.office_names] if cfg.offices else []
        self.slots: dict[str, dict[int, int]] = {k: {} for k in self.office_names}
        kind = cfg.structure["kind"]
        self.kind = kind
        if kind == "distributed":
            self.units = {
                "상담": simpy.Resource(self.env, self.p["center_staff"]),
                "갈등조정": None,  # 별도 조직이 없어 센터가 떠맡는다
                "법률": simpy.Resource(self.env, self.p["legal_staff"]),
                "행정": simpy.Resource(self.env, self.p["admin_staff"]),
                "수사연계": None,
            }
            self.units["갈등조정"] = self.units["상담"]
        else:
            self.leads = simpy.PriorityResource(
                self.env, max(1, self.p["regular_officers"] * self.p["caseload_per_regular"]))
            self.center = simpy.Resource(self.env, self.p["center_staff"])
            self.pools = {s: simpy.Resource(self.env, max(1, round(self.p["nonregular_officers"] * f)))
                          for s, f in NONREGULAR_MIX.items()}

    # ── 공통 ──
    def work(self, service: str, factor: float = 1.0) -> float:
        manual = self.p.get("manual", False)
        sigma = 0.3 if manual else 0.6  # 매뉴얼이 있으면 처리 편차가 작다 (공식화)
        return WORK_MEDIAN[service] * factor * math.exp(self.rng.gauss(0, sigma))

    def next_committee(self) -> float:
        interval = self.p["committee_interval_days"] * HOURS_PER_DAY
        return interval - (self.env.now % interval)

    def committee_wait(self, c: Case) -> float:
        """다음 위원회까지 기다릴 시간. 지도 모드에서는 관할 교육지원청 위원회가 정원만큼만 심의하고
        넘치는 사안은 다음 회의로 밀린다. 교육지원청마다 개최일이 다르다."""
        if not c.office:
            c.committee_wait = self.next_committee()
            return c.committee_wait
        interval = self.p["committee_interval_days"] * HOURS_PER_DAY
        offset = (self.office_names.index(c.office) / len(self.office_names)) * interval
        k = max(0, math.floor((self.env.now - offset) / interval) + 1)
        used = self.slots[c.office]
        while used.get(k, 0) >= self.cfg.committee_capacity:
            k += 1
        used[k] = used.get(k, 0) + 1
        wait = offset + k * interval - self.env.now
        c.committee_wait = wait
        return wait

    def police(self) -> float:
        return POLICE_DELAY_MEDIAN * math.exp(self.rng.gauss(0, 0.5))

    def needs_committee(self, c: Case) -> bool:
        return c.severity >= 2 and "소송" not in c.type and c.type != "단순 상담"

    # ── 사안 도착 ──
    def arrivals(self):
        end = self.cfg.days * HOURS_PER_DAY
        while True:
            rate = self.cfg.arrivals_per_day
            day = self.env.now / HOURS_PER_DAY
            if self.cfg.surge_day is not None and self.cfg.surge_day <= day < self.cfg.surge_day + self.cfg.surge_days:
                rate *= self.cfg.surge_multiplier
            yield self.env.timeout(self.arr_rng.expovariate(rate / HOURS_PER_DAY))
            if self.env.now >= end:
                return
            self.start(random_case(self.arr_rng, self.env.now, next(self._ids)))

    def start(self, case: Case):
        if self.office_names and not case.office:
            case.office = self.geo_rng.choices(self.office_names, weights=self.office_w)[0]
        self.cases.append(case)
        proc = self.distributed if self.kind == "distributed" else self.integrated
        self.env.process(proc(case))

    def inject(self, spec: dict, day: float):
        def _later():
            yield self.env.timeout(day * HOURS_PER_DAY)
            self.start(scenario_case(spec, self.env.now, next(self._scenario_ids)))
        self.env.process(_later())

    # ── A. 분산 구조 ──
    def distributed(self, c: Case):
        env, p = self.env, self.p
        c.log(env.now, "피해 교원", f"사안 발생: {c.type} (심각도 {c.severity})")
        c.contacts += 1
        c.repeats += 1
        yield env.timeout(self.rng.uniform(1, 4))
        c.log(env.now, "학교 관리자", "1차 대응 후 '해당 부서에 문의하라'고 안내", self.cite("distributed"))
        prev = None
        for s in c.needs:
            # 어느 창구로 가야 하는지 교사가 직접 찾는다 (정보 비대칭)
            yield env.timeout(self.rng.uniform(2, 8))
            if self.rng.random() < p["misroute_prob"]:
                c.misroutes += 1
                c.contacts += 1
                c.repeats += 1
                c.log(env.now, "피해 교원", f"[{s}] 엉뚱한 창구에 문의해 다시 안내받음")
                yield env.timeout(4)
            c.contacts += 1
            c.repeats += 1
            if s == "수사연계":
                c.log(env.now, "피해 교원", "직접 경찰에 신고·고소 진행")
                if c.first_response is None:
                    c.first_response = env.now
                yield env.timeout(self.police())
            else:
                unit = self.units[s]
                factor = 1.5 if s == "갈등조정" else 1.0  # 전문 인력이 없어 센터가 떠맡음
                with unit.request() as req:
                    yield req
                    if c.first_response is None:
                        c.first_response = env.now
                    label = "지원센터(갈등조정 겸임)" if s == "갈등조정" else {"상담": "지원센터", "법률": "법률지원 부서", "행정": "교육지원청"}[s]
                    c.log(env.now, label, f"[{s}] 처리 시작 (교사가 처음부터 다시 설명)")
                    yield env.timeout(self.work(s, factor))
            # 앞 기관의 결과가 다음 기관에 필요하면 교사가 직접 전달한다 (조정자 부재)
            if prev and (c.interdependence != "집합적") and self.rng.random() < p["relay_prob"]:
                c.contacts += 1
                c.repeats += 1
                c.log(env.now, "피해 교원", f"[{prev}]→[{s}] 서류·결과를 직접 전달")
                yield env.timeout(self.rng.uniform(2, 6))
            prev = s
        if c.interdependence == "교호적":
            # 여러 기관이 서로의 판단에 영향을 주는데 이를 묶는 사람이 없다 → 재작업
            for a, b in itertools.combinations(c.needs, 2):
                if self.rng.random() < p["relay_prob"] / 2:
                    c.contacts += 1
                    c.repeats += 1
                    c.log(env.now, "피해 교원", f"[{a}]·[{b}] 판단이 엇갈려 다시 조율 요청")
                    yield env.timeout(4)
        if self.needs_committee(c):
            c.contacts += 1
            c.repeats += 1
            c.log(env.now, "피해 교원", "지역교권보호위원회 심의 직접 신청", self.cite("committee"))
            yield env.timeout(self.committee_wait(c))
            c.log(env.now, f"{c.office + ' ' if c.office else ''}지역교권보호위원회", "심의·조치", self.cite("committee_rare"))
        c.closed = env.now
        c.log(env.now, "피해 교원", "사안 종결 (사후 관리는 교사 몫)")

    # ── B/C. 통합 구조 ──
    def integrated(self, c: Case):
        env, p = self.env, self.p
        c.log(env.now, "피해 교원", f"사안 발생: {c.type} (심각도 {c.severity})")
        c.contacts += 1
        c.repeats += 1
        yield env.timeout(self.rng.uniform(0.5, 2))
        c.log(env.now, "교권보호 119 접수", "접수·분류")
        misroute = 0.05 if p["manual"] else 0.2
        if self.rng.random() < misroute:
            c.misroutes += 1
            c.repeats += 1
            c.log(env.now, "교권보호 119 접수", "분류 착오로 재배정 (매뉴얼 부재)", self.cite("manual"))
            yield env.timeout(8)
        if not p["linkage_procedure"] and self.rng.random() < 0.5:
            # 연계절차가 없으면 센터도 따로 접수해 같은 내용을 다시 묻는다
            c.duplicates += 1
            c.contacts += 1
            c.repeats += 1
            c.log(env.now, "지역교권보호지원센터", "별도 접수·상담 진행 (업무 중복)", self.cite("linkage"))
            with self.center.request() as req:
                yield req
                yield env.timeout(2)

        escalate = p["escalation"] and c.severity == 3
        priority = 0 if escalate else 4 - c.severity
        with self.leads.request(priority=priority) as lead:
            yield lead
            c.first_response = env.now
            c.log(env.now, "상근 전담관", "주 담당 배정, 1:1 초기 상담·지원계획 수립", self.cite("assign"))
            c.coordination += 1
            yield env.timeout(2)
            if escalate:
                c.log(env.now, "교육감(단장)", "중대 사안 지정, 필요 시 고발 결정", self.cite("escalation"))
                c.coordination += 1
                yield env.timeout(4)
            # 전담관은 침해 여부를 직접 판단하지 않는다 → 위원회로 넘긴다 (근거 조문)
            if self.needs_committee(c):
                c.guard_blocks += 1
                c.log(env.now, "상근 전담관", "침해 여부 판단은 권한 밖 → 위원회 심의 요청 서류 대리 준비", self.cite("guard"))
            # 필요한 전문가를 병렬로 연결 (행정은 교육전문직인 주 담당이 직접)
            jobs = [env.process(self.specialist(c, s)) for s in c.needs if s != "행정"]
            if "행정" in c.needs:
                yield env.timeout(self.work("행정"))
                c.log(env.now, "상근 전담관", "[행정] 절차 직접 처리", self.cite("officer_duty"))
            if jobs:
                yield simpy.AllOf(env, jobs)
            if c.interdependence == "교호적":
                n = len(c.needs)
                c.coordination += n * (n - 1) // 2
                c.log(env.now, "상근 전담관", f"사안 회의로 전문가 {n}명 판단 조율 (교사 참여 불필요)", self.cite("team"))
                yield env.timeout(2)
            if self.needs_committee(c):
                c.coordination += 1
                yield env.timeout(self.committee_wait(c))
                c.log(env.now, f"{c.office + ' ' if c.office else ''}지역교권보호위원회", "심의·조치 (전담관이 자료 제출)", self.cite("committee"))
            c.closed = env.now
            c.log(env.now, "상근 전담관", "사안 종결 → 사후 관리로 전환", self.cite("officer_duty"))

    def specialist(self, c: Case, s: str):
        env, p = self.env, self.p
        if s == "상담" and p["linkage_procedure"]:
            with self.center.request() as req:
                yield req
                c.coordination += 2
                c.log(env.now, "지역교권보호지원센터", "[상담] 연계절차로 사안팀 합류 (재진술 없음)", self.cite("linkage"))
                yield env.timeout(self.work(s))
            return
        a = p["nonregular_availability"]
        with self.pools[s].request() as req:
            yield req
            # 비상근은 본업이 있어 일정을 맞출 때까지 기다린다
            wait = self.rng.expovariate(1 / (HOURS_PER_DAY * (1 - a) / a)) if a < 1 else 0
            yield env.timeout(wait)
            c.coordination += 2
            c.log(env.now, "비상근 전담관", f"[{s}] 합류 (일정 조율 {wait / HOURS_PER_DAY:.1f}일)", self.cite("nonregular"))
            t = self.work(s)
            if s == "수사연계":
                t += self.police()
            if t > HOURS_PER_DAY and self.rng.random() < (1 - a) * 0.5:
                c.handoffs += 1
                c.coordination += 1
                c.log(env.now, "비상근 전담관", f"[{s}] 담당자 일정 공백으로 인수인계")
                t += 2 + self.rng.expovariate(1 / HOURS_PER_DAY)
            yield env.timeout(t)

    def run(self, scenarios: list[tuple[dict, float]] = ()) -> list[Case]:
        self.env.process(self.arrivals())
        for spec, day in scenarios:
            self.inject(spec, day)
        self.env.run()
        return self.cases


def run(cfg: SimConfig, retriever=None, scenarios=()) -> list[Case]:
    return Simulation(cfg, retriever).run(scenarios)
