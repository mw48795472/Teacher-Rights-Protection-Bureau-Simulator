import pandas as pd

from sim import empirical as E
from sim.engine import SimConfig, list_structures, run
from sim.metrics import to_frame

S = list_structures()


def _df(src="measured", k="A_distributed"):
    return to_frame(run(SimConfig(S[k], days=60, arrivals_per_day=E.default_rate(), case_source=src)), k)


def test_measured_cases_follow_measured_mix():
    d = _df()
    tc = E.type_counts()
    top = max(tc, key=tc.get)
    assert top == "모욕·명예훼손"
    assert abs((d["type"] == top).mean() - tc[top] / sum(tc.values())) < 0.08
    assert set(d["actor"]) == {"학생", "보호자"}
    # 교보위 유형은 모두 위원회로, 아동학대 신고는 위원회로 가지 않는다
    assert d.loc[d["type"] != E.ABUSE, "committee"].all()
    assert not d.loc[d["type"] == E.ABUSE, "committee"].any()
    assert set(E.TYPE_PROFILE) >= set(tc)


def test_assumed_mode_unchanged_and_common_random_numbers():
    a = _df("assumed")
    assert set(a["actor"]) == {""}
    m1, m2 = _df(), _df(k="B_gyeonggi")
    assert list(m1.sort_values("id")["type"]) == list(m2.sort_values("id")["type"])


def test_default_rate_and_reproduction():
    assert 4.0 < E.default_rate() < 5.5
    rep = E.reproduction(_df(), E.default_rate())
    assert {"입력 확인", "보정 기준", "독립 비교"} == set(rep["점검"])
    cal = rep[rep["점검"] == "보정 기준"].iloc[0]
    assert abs(cal["시뮬레이션"] - cal["실측"]) / cal["실측"] < 0.25
    assert isinstance(rep, pd.DataFrame) and rep["차이"].notna().all()
