"""Home의 가설(H1~H5)을 기본 설정 시뮬레이션 결과로 판정한다 (규칙 기반).

판정은 '지지 / 부분 지지 / 지지 안 됨' 세 가지다. 숫자는 가정값 위의 결과라서
구조 간 차이의 방향을 보는 용도로 쓴다.
"""
from __future__ import annotations

import pandas as pd

SUPPORT, PARTIAL, NOT = "지지", "부분 지지", "지지 안 됨"


def _drop(new: float, old: float) -> float:
    return (old - new) / old * 100 if old else 0.0


def h1(a: pd.DataFrame, b: pd.DataFrame) -> tuple[str, str]:
    c = _drop(b.contacts.mean(), a.contacts.mean())
    r = _drop(b.repeats.mean(), a.repeats.mean())
    v = SUPPORT if c >= 30 and r >= 30 else PARTIAL if c > 0 or r > 0 else NOT
    return v, (f"접촉 기관 {a.contacts.mean():.1f}→{b.contacts.mean():.1f}곳 ({c:.0f}% 감소), "
               f"반복 진술 {a.repeats.mean():.1f}→{b.repeats.mean():.1f}번 ({r:.0f}% 감소)")


def h2(a: pd.DataFrame, b: pd.DataFrame) -> tuple[str, str]:
    """위원회 대기를 뺀 처리 기간으로 본다. 기본 가정에서 지원 1~2개 사안은 위원회로 가지 않아,
    종결 기간을 쓰면 위원회 개최 간격(A 60일, B 30일) 차이가 교호적 사안에만 얹혀 효과가 부풀려진다."""
    col = "process_days" if "process_days" in a and "process_days" in b else "closure_days"
    ga = a.groupby("interdependence")[col].mean()
    gb = b.groupby("interdependence")[col].mean()
    gap = (ga - gb).dropna()
    if not {"교호적", "집합적"} <= set(gap.index):
        return PARTIAL, "비교할 사안 유형이 부족합니다."
    hi, lo = gap["교호적"], gap["집합적"]
    v = SUPPORT if hi > lo and hi > 0 else PARTIAL if hi > 0 else NOT
    ev = f"A와 B의 처리 기간(위원회 대기 제외) 차이: 교호적 사안 {hi:.1f}일, 집합적 사안 {lo:.1f}일"
    if col == "process_days":
        tot = (a.groupby("interdependence")["closure_days"].mean() - b.groupby("interdependence")["closure_days"].mean())
        t = tot.get("교호적", float("nan"))
        if pd.notna(t) and t > hi:
            ev += f" (위원회 대기를 포함하면 교호적 {t:.1f}일이며, 그중 {(t - hi) / t * 100:.0f}%는 위원회 개최 간격 차이)"
    return v, ev


def surge_ratio(df: pd.DataFrame, day: int, days: int = 7) -> float:
    before = df[df.arrival_day < day].closure_days.mean()
    during = df[(df.arrival_day >= day) & (df.arrival_day < day + days)].closure_days.mean()
    return during / before if before else float("nan")


def h3(a_s: pd.DataFrame, b_s: pd.DataFrame, day: int) -> tuple[str, str]:
    ra, rb = surge_ratio(a_s, day), surge_ratio(b_s, day)
    v = SUPPORT if rb < ra else NOT
    return v, f"급증 구간 종결 기간이 평소의 A {ra:.2f}배, B {rb:.2f}배"


def h4(b0: pd.DataFrame, b: pd.DataFrame) -> tuple[str, str]:
    d0, d1 = b0.duplicates.mean(), b.duplicates.mean()
    m0, m1 = b0.misroutes.mean(), b.misroutes.mean()
    v = SUPPORT if d1 < d0 and m1 < m0 else PARTIAL if d1 < d0 or m1 < m0 else NOT
    return v, f"업무 중복 {d0:.2f}→{d1:.2f}건, 창구 착오 {m0:.2f}→{m1:.2f}건 (사안당)"


def h5(b: pd.DataFrame, c: pd.DataFrame) -> tuple[str, str]:
    hb, hc = b.handoffs.mean(), c.handoffs.mean()
    cb, cc = b.closure_days.mean(), c.closure_days.mean()
    v = SUPPORT if hc < hb and cc <= cb else PARTIAL if hc < hb else NOT
    return v, f"인수인계 {hb:.2f}→{hc:.2f}건, 종결 {cb:.1f}→{cc:.1f}일"
