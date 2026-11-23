import yaml

from agents.drama import build_script, script_text
from agents.runner import run_agents
from collector.pipeline import load_seed
from rag.retriever import Retriever

SPEC = yaml.safe_load(open("config/scenarios.yaml", encoding="utf-8"))["scenarios"][0]


def test_script_follows_run_and_shows_blocks_as_captions(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = run_agents(SPEC, "drama", Retriever(load_seed()), 20)
    sc = build_script(run, SPEC["name"])
    scenes = [x for _, xs in sc.acts for x in xs]
    assert [x.no for x in scenes] == [t.n for t in run.turns]
    assert sc.acts[0][0].startswith("제1막")
    blocked = [x for x in scenes if x.decision == "차단"]
    assert blocked and all("차단" in x.caption and "실행되지 못한다" in x.direction for x in blocked)
    assert all(x.line for x in scenes)
    text = script_text(sc)
    assert "S#1." in text and "[자막]" in text and "에필로그" in text
