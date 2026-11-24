from agents import digest
from agents.runner import run_agents
from tests.test_agents import SPEC, _r


def _runs(monkeypatch, keys=("integrated", "distributed", "drama")):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return {k: run_agents(SPEC, k, _r(), 26) for k in keys}


def test_key_moments_are_short_and_keep_blocks(monkeypatch):
    runs = _runs(monkeypatch)
    for run in runs.values():
        ms = digest.key_moments(run)
        moments = [m for m in ms if isinstance(m, digest.Moment)]
        assert len(moments) < len(run.turns)          # 줄어든다
        assert all(len(m.what) <= 48 for m in moments)
    blocked = [m for m in digest.key_moments(runs["drama"]) if isinstance(m, digest.Moment) and m.badge == "차단"]
    assert {m.intent for m in blocked} >= {"물리적제지", "사실조사"}


def test_theory_rows_match_hypotheses_offline(monkeypatch):
    rows = {r["가설"]: r for r in digest.theory_rows(_runs(monkeypatch))}
    assert rows["H6"]["판정"] == "부합"
    assert rows["H1"]["판정"] == "부합"
    assert rows["H1 보조"]["판정"] == "부합"
    assert "조정 장치" in digest.takeaway(list(rows.values()))


def test_theory_rows_without_distributed_skip_h1(monkeypatch):
    rows = digest.theory_rows(_runs(monkeypatch, ("integrated", "drama")))
    assert [r["가설"] for r in rows] == ["H6"]
    assert "H1" in digest.takeaway(rows)
