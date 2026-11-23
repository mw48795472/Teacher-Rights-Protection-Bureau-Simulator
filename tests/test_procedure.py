"""위원회 절차 (길라잡이 서식) 단계가 사안 추적과 에이전트 시뮬레이션에 나타나는지."""
import yaml

from agents.runner import run_agents
from collector.pipeline import load_seed
from rag.retriever import Retriever
from sim.cases import Case
from sim.engine import SimConfig, Simulation, list_structures

SPEC = yaml.safe_load(open("config/scenarios.yaml", encoding="utf-8"))["scenarios"][0]


def _trace(key):
    sim = Simulation(SimConfig(list_structures()[key]), Retriever(load_seed()))
    cases = sim.run([(SPEC, 10.0)])
    return [c for c in cases if c.label][0]


def test_scenario_goes_through_committee_procedure():
    a, b = _trace("A_distributed"), _trace("B_gyeonggi")
    for c in (a, b):
        acts = " ".join(e["action"] for e in c.trace)
        for form in ("서식 1", "서식 2", "서식 3", "서식 6", "서식 10", "서식 11", "서식 14", "서식 15"):
            assert form in acts
    assert any("교사가 처음부터 다시 진술" in e["action"] for e in a.trace)
    assert not any("교사가 처음부터 다시 진술" in e["action"] for e in b.trace)
    assert any(e["cite"] == "guide-forms-office" for e in b.trace)


def test_mediation_step_runs_when_requested():
    sim = Simulation(SimConfig(list_structures()["B_gyeonggi"], days=1))
    c = Case(1, "악성민원", 2, ("상담", "갈등조정"), True)
    c.mediation = False
    import sim.engine as eng
    old = eng.MEDIATION_PROB
    eng.MEDIATION_PROB = 1.0
    try:
        sim.env.process(sim.committee_procedure(c, supported=True))
        sim.env.run()
    finally:
        eng.MEDIATION_PROB = old
    assert c.mediation
    assert any("분쟁조정" in e["action"] for e in c.trace)


def test_agents_include_investigation_and_mediation(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = run_agents(SPEC, "integrated", Retriever(load_seed()), 26)
    intents = [t.review.action.intent for t in run.turns]
    for i in ("분리조치", "참고인진술", "사안조사", "의견서제출", "분쟁조정신청", "분쟁조정", "위원회심의·조치"):
        assert i in intents
    assert run.closed
