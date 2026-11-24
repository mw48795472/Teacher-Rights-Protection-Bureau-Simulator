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
    assert "전담관" in digest.takeaway(list(rows.values()))


def test_theory_rows_without_distributed_skip_h1(monkeypatch):
    rows = digest.theory_rows(_runs(monkeypatch, ("integrated", "drama")))
    assert [r["가설"] for r in rows] == ["H6"]
    assert "H1" in digest.takeaway(rows)


def test_relmap_svg_has_every_role_and_run_counts(monkeypatch):
    from agents import relmap
    from agents.roles import STRUCTURES
    runs = _runs(monkeypatch)
    for k, run in runs.items():
        static = relmap.svg(k)
        assert static.startswith("<svg") and static.endswith("</svg>")
        for role in relmap.LAYOUT[k]["pos"]:
            assert (role in STRUCTURES[k].roles or role in relmap.STUDENTS) and relmap.NODE[role][2] in static
        assert ">5<" in relmap.svg("distributed", runs["distributed"])  # 선생님이 5번 움직임
    assert "✕" in relmap.svg("drama") and "7 5" not in relmap.svg("integrated")


def test_relmap_shows_students():
    from agents import relmap
    for k in relmap.LAYOUT:
        out = relmap.svg(k)
        assert "학생 A" in out and "학생 B" in out and "다툼" in out and "내 아이" in out
