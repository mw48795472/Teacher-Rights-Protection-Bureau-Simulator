import pandas as pd

from sim import hypotheses as H
from sim import insights
from sim import typeffects as TE
from sim.engine import SimConfig, list_structures, run
from sim.metrics import to_frame

S = list_structures()


def _df(keys=("A_distributed", "B_gyeonggi"), **kw):
    df = pd.concat([to_frame(run(SimConfig(S[k], days=60, **kw)), k) for k in keys], ignore_index=True)
    df["구조"] = df["structure"]
    return df


def test_paired_uses_same_cases():
    df = _df()
    p = TE.paired(df, "process_days", "A_distributed", "B_gyeonggi")
    a = df[df.structure == "A_distributed"]
    assert len(p) == len(a) and set(p["id"]) == set(a["id"])
    assert (p["diff"] == p["base"] - p["target"]).all()


def test_process_days_excludes_committee_wait():
    df = _df(("A_distributed",))
    assert (df["process_days"] <= df["closure_days"] + 1e-9).all()
    assert (df.loc[~df.committee, "committee_wait_days"] == 0).all()


def test_analyzability_now_matters():
    """분석가능성이 낮은 사안에서 A→B 격차가 더 커야 한다 (예전엔 이름표일 뿐이었음)."""
    df = _df(seed=7)
    p = TE.paired(df, "process_days", "A_distributed", "B_gyeonggi")
    reg = TE.regression(p).set_index("항")
    assert reg.at["low_analyz", "계수"] > 0
    assert reg.at["n_needs", "계수"] > 0
    lines = insights.theory(p, TE.regression(p), "A", "B", "처리 기간", "일")
    assert any("Thompson" in x for x in lines) and any("H2 판정" in x for x in lines)


def test_cells_trend_gap():
    df = _df()
    c = TE.cells(df, "interdependence", "process_days")
    assert {"n", "mean", "ci"} <= set(c.columns)
    t = TE.trend(df, "n_needs", "process_days").set_index("구조")
    assert t.at["A_distributed", "기울기"] > t.at["B_gyeonggi", "기울기"]
    g = TE.gap_by(TE.paired(df, "process_days", "A_distributed", "B_gyeonggi"), ["variety_high", "analyzable"])
    assert len(g) == 4


def test_h2_uses_process_days():
    df = _df()
    a, b = df[df.structure == "A_distributed"], df[df.structure == "B_gyeonggi"]
    v, ev = H.h2(a, b)
    assert v == H.SUPPORT and "위원회 대기 제외" in ev
