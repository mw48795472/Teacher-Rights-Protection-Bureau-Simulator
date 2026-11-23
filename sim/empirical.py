"""실측 기반 사안 생성기 (교권보호위원회 통계).

'가정' 모드(sim/cases.random_case)는 학부모 민원 중심의 팀 가정 유형 5개로 사안을 만든다.
'실측' 모드는 config/measured.yaml 의 실제 통계에서 사안 속성을 뽑는다.

실측에서 뽑는 것
- 침해 유형: 2023학년도 교보위 침해 유형별 건수(12종, 합계 5,050) + 교원 대상 아동학대 신고
  (교육감 의견 제출 2023.9~2024.4, 연 환산 약 642건)
- 침해 주체: 학생 89% · 보호자 11% (2024 전국). 아동학대 신고는 모두 보호자.
- 학교급: 2023 교보위 학교급별 건수
- 침해 인정 여부: 2023 학교 교보위 결과(4,953/5,050)
- 위원회 회부: 교보위 유형은 모두 심의를 거친 사안이므로 모두 위원회로 간다.

아직 가정인 것 (유형 → 필요한 지원·심각도 대응표, 아래 TYPE_PROFILE)
- 유형별로 어떤 지원이 필요한지와 심각도는 공개 통계가 없어 팀이 정한 대응표를 쓴다.
- 유형과 침해 주체는 서로 독립이라고 가정한다 (유형×주체 교차표가 공개되지 않음).
reproduction() 이 실측 합계와 시뮬레이션 결과를 나란히 보여 줘 어디가 맞고 어디가 어긋나는지 드러낸다.
"""
from __future__ import annotations

import random

import pandas as pd

from .calibration import load, opinions_per_year
from .cases import Case

ABUSE = "무고성 아동학대 신고"

# 유형 → (기본 지원, 심각도 가중치[경미, 보통, 중대]) — 팀 가정
TYPE_PROFILE: dict[str, tuple[tuple[str, ...], tuple[float, float, float]]] = {
    "상해·폭행": (("상담", "수사연계", "행정"), (0.2, 0.5, 0.3)),
    "협박": (("상담", "수사연계"), (0.3, 0.5, 0.2)),
    "모욕·명예훼손": (("상담", "법률"), (0.5, 0.4, 0.1)),
    "손괴": (("상담", "행정"), (0.6, 0.3, 0.1)),
    "성폭력범죄": (("상담", "수사연계", "법률", "행정"), (0.0, 0.4, 0.6)),
    "불법정보 유통": (("상담", "수사연계", "법률"), (0.3, 0.5, 0.2)),
    "공무 및 업무방해": (("상담", "갈등조정", "행정"), (0.4, 0.5, 0.1)),
    "성적 굴욕감·혐오감": (("상담", "법률"), (0.3, 0.5, 0.2)),
    "교육활동 반복적 부당 간섭": (("상담", "갈등조정", "법률"), (0.3, 0.5, 0.2)),
    "교육활동 방해": (("상담",), (0.7, 0.25, 0.05)),
    "영상 무단 합성·배포": (("상담", "수사연계", "법률"), (0.1, 0.5, 0.4)),
    "기타": (("상담",), (0.7, 0.25, 0.05)),
    ABUSE: (("법률", "상담", "행정", "수사연계"), (0.0, 0.6, 0.4)),
}
GUARDIAN_EXTRA = "갈등조정"   # 보호자가 침해 주체면 민원·분쟁 조정이 붙는다 (가정)


def type_counts() -> dict[str, float]:
    """연간 건수 기준 유형 분포 (교보위 유형 + 아동학대 신고 연 환산)."""
    c = {k: float(v) for k, v in load()["committee_types_2023"]["counts"].items()}
    c[ABUSE] = opinions_per_year()
    return c


def guardian_share() -> float:
    a = load()["committee_by_sido"]["y2024"]["national_actor_share"]
    return a["보호자"] / (a["학생"] + a["보호자"])


def level_counts() -> dict[str, float]:
    return {k: float(v) for k, v in load()["committee_levels_2023"]["counts"].items()}


def recognized_share() -> float:
    o = load()["committee_outcomes"]["school_2023"]
    return o["침해 인정"] / sum(o.values())


def random_case(rng: random.Random, arrival: float, case_id: int) -> Case:
    tc = type_counts()
    t = rng.choices(list(tc), weights=list(tc.values()))[0]
    needs, sev_w = TYPE_PROFILE.get(t, (("상담",), (0.5, 0.4, 0.1)))
    actor = "보호자" if t == ABUSE or rng.random() < guardian_share() else "학생"
    needs = list(needs)
    if actor == "보호자" and GUARDIAN_EXTRA not in needs:
        needs.append(GUARDIAN_EXTRA)
    sev = rng.choices([1, 2, 3], weights=sev_w)[0]
    lv = level_counts()
    level = rng.choices(list(lv), weights=list(lv.values()))[0]
    analyzable = rng.random() < (0.7 if len(needs) <= 2 else 0.35)
    c = Case(case_id, t, sev, tuple(needs), analyzable, arrival)
    c.actor, c.level = actor, level
    c.committee_route = t != ABUSE            # 교보위 유형은 모두 심의를 거친 사안
    c.recognized = rng.random() < recognized_share()
    return c


# ── 재현 점검: 실측 합계 vs 시뮬레이션 ─────────────────────────

WORKDAYS_PER_YEAR = 250


def default_rate() -> float:
    """하루 사안 수 기본값: 경기 2024년 위원회 심의 1,054건을 연 250근무일로 나누고,
    위원회로 가지 않는 아동학대 신고 사안 비중만큼 키운다 (위원회 심의 건수에 맞춘 보정)."""
    y = load()["committee_by_sido"]["y2024"]["counts"]["경기"]
    tc = type_counts()
    committee_share = 1 - tc[ABUSE] / sum(tc.values())
    return y / WORKDAYS_PER_YEAR / committee_share


def reproduction(df: pd.DataFrame, rate: float) -> pd.DataFrame:
    """실측 모드 결과표(구조 하나)에서 실측 합계와 비교할 지표.
    '입력 확인'은 실측 분포에서 뽑은 값이 표본에서도 맞는지, '독립 비교'는 뽑지 않은 실측 값과의 비교다."""
    m = load()
    d = df.drop_duplicates("id")
    if d.empty:
        return pd.DataFrame()
    comm = d[d["committee"]] if "committee" in d else d.iloc[0:0]
    rows = []

    def add(kind, name, real, sim, unit="%", note=""):
        rows.append({"점검": kind, "지표": name, "실측": real, "시뮬레이션": sim, "단위": unit, "비고": note})

    tc = type_counts()
    tot = sum(tc.values())
    top = sorted(tc, key=tc.get, reverse=True)[:3]
    for t in top:
        add("입력 확인", f"유형 비중: {t}", tc[t] / tot * 100, (d["type"] == t).mean() * 100)
    add("입력 확인", "침해 주체 중 보호자", guardian_share() * 100,
        (d.loc[d["type"] != ABUSE, "actor"] == "보호자").mean() * 100, note="아동학대 신고 사안 제외")
    lv = level_counts()
    add("입력 확인", "학교급: 중학교", lv["중학교"] / sum(lv.values()) * 100, (d["level"] == "중학교").mean() * 100)
    q = m["committee_by_sido"]["q2024_regional"]
    wd = q["days"] * 5 / 7
    per_day = len(comm) / max(1, d["arrival_day"].max())
    add("독립 비교", "경기 위원회 심의 건수 (2024.3.28.~6.30.)", q["counts"]["경기"], per_day * wd, "건",
        f"하루 {rate:.1f}건 설정 × 위원회 비율 × {wd:.0f}근무일. 실측은 학교→교육지원청 이관 직후라 밀린 사안이 몰렸을 수 있음")
    y = m["committee_by_sido"]["y2024"]["counts"]["경기"]
    add("보정 기준", "경기 위원회 심의 건수 (2024년)", y, per_day * WORKDAYS_PER_YEAR, "건",
        f"연 {WORKDAYS_PER_YEAR}근무일 기준. 기본 하루 사안 수({default_rate():.1f}건)를 이 값에 맞춤")
    cu = m["center_usage"]["by_year"][2023]
    has = lambda s: d["needs"].map(lambda x: s in x).sum() if "needs" in d else 0  # noqa: E731
    sim_ratio = has("법률") / max(1, has("상담")) * 100
    add("독립 비교", "법률 지원 / 상담 (건수 비)", cu["법률지원"] / cu["상담"] * 100, sim_ratio, "%",
        "실측은 교육활동보호센터 이용 '건수'(상담 회기 포함), 시뮬레이션은 '사안' 수라 단위가 다름")
    out = pd.DataFrame(rows)
    out["차이"] = out["시뮬레이션"] - out["실측"]
    return out
