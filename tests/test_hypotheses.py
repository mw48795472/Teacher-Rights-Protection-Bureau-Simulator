import yaml

from sim import hypotheses as H
from sim.engine import SimConfig, list_structures, run
from sim.metrics import to_frame

S = list_structures()


def _f(k, **kw):
    return to_frame(run(SimConfig(S[k], **kw)), k)


def test_theory_file_links_every_hypothesis():
    t = yaml.safe_load(open("config/theory.yaml", encoding="utf-8"))
    ids = {h["id"] for h in t["hypotheses"]}
    used = {th["hyp"] for c in t["concepts"] for th in c["theories"] if th.get("hyp")}
    assert used <= ids and {"H1", "H2", "H3", "H4", "H5", "H6"} == ids
    assert all("num" in c and "title" in c for c in t["concepts"])


def test_default_run_verdicts():
    a, b0, b, c = (_f(k) for k in S)
    assert H.h1(a, b)[0] == H.SUPPORT
    assert H.h2(a, b)[0] == H.SUPPORT
    assert H.h4(b0, b)[0] == H.SUPPORT
    assert H.h5(b, c)[0] in (H.SUPPORT, H.PARTIAL)
    v, ev = H.h3(_f("A_distributed", surge_day=20, surge_multiplier=2.0),
                 _f("B_gyeonggi", surge_day=20, surge_multiplier=2.0), 20)
    assert v in (H.SUPPORT, H.NOT) and "배" in ev
