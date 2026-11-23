import pandas as pd

from sim import insights
from sim.engine import SimConfig, list_structures, run
from sim.metrics import summarize, to_frame


def _df():
    S = list_structures()
    df = pd.concat([to_frame(run(SimConfig(S[k], days=40, offices={"수원": 3.0, "연천": 1.0})), k) for k in S])
    short = {k: s.get("short", k) for k, s in S.items()}
    df["구조"] = df["structure"].map(short)
    return df, short


def test_overview_and_type_and_surge():
    df, short = _df()
    ov = insights.overview(summarize(df, "structure"), short)
    assert ov[0].startswith("**가장 빨리 종결한 구조")
    assert any("Lawrence & Lorsch" in x for x in ov)
    assert insights.by_type(df, "perrow", "closure_days", "종결")
    sr = insights.surge(df, 10)
    assert sr and "배" in sr[0]


def test_offices_skip_zero_wait():
    per = pd.DataFrame({"구조": ["A"] * 4, "office": ["수원", "연천", "가평", "부천"],
                        "사안": [10, 1, 2, 5], "위원회_대기일": [20.0, 0.0, 5.0, 12.0], "종결일": [1.0] * 4})
    text = " ".join(insights.offices(per, "A"))
    assert "연천(0.0일)" not in text and "수원(20.0일" in text


def test_agent_runs():
    m = {"행동 수": 6, "차단": 2, "조건부 허용": 1, "교육활동 침해 탐지": 1, "권한 초과": 2, "근거 불충분": 3,
         "피해 교원이 직접 한 행동": 1, "처리 주체 없는 후속 절차": 0, "종결": False}
    out = insights.agent_runs({"드라마식": m})
    assert "차단 2개" in out[0] and any("근거 불충분" in x for x in out) and any("권한 초과로" in x for x in out)
