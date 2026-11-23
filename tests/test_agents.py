import yaml

from agents import actors, compliance
from agents.models import Action, Verdict
from agents.runner import route_trigger, run_agents
from agents.roles import STRUCTURES
from collector.pipeline import load_seed
from rag.retriever import Retriever

SPEC = yaml.safe_load(open("config/scenarios.yaml", encoding="utf-8"))["scenarios"][0]


def _r():
    return Retriever(load_seed())


def test_offline_drama_model_is_blocked_on_physical_force_and_investigation(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = run_agents(SPEC, "drama", _r(), 20)
    blocked = {t.review.action.intent: t.review.verdict for t in run.turns if t.review.verdict.decision == "차단"}
    assert {"물리적제지", "사실조사"} <= set(blocked)
    assert "ord-15" in blocked["사실조사"].cited_ids
    assert run.mode == "offline"


def test_distributed_structure_leaves_protection_unhandled(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = run_agents(SPEC, "distributed", _r(), 20)
    assert run.metrics["교육활동 침해 탐지"] >= 1
    assert run.metrics["처리 주체 없는 후속 절차"] >= 1
    integrated = run_agents(SPEC, "integrated", _r(), 20)
    assert integrated.metrics["처리 주체 없는 후속 절차"] == 0


def test_trigger_routing():
    assert route_trigger("위원회", STRUCTURES["integrated"]) == "상근 전담관"
    assert route_trigger("보호조치", STRUCTURES["distributed"]) is None
    assert route_trigger("수사기관", STRUCTURES["drama"]) == "교육감"


def test_llm_mode_block_reroutes_to_alternative_actor(monkeypatch):
    """LLM 응답을 대신 넣어 실행기 배선을 확인한다 (실제 API 호출 없음)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    calls = []

    def fake(system, user, schema, effort="medium", max_tokens=8000):
        calls.append(schema.__name__)
        if schema is Verdict:
            if "상근 전담관" in user.split("## 심사할 행동")[1][:40]:
                return Verdict(decision="차단", category="권한 초과", cited_ids=["ord-15", "없는-id"],
                               reason="조사권 없음", condition="", alternative_intent="위원회심의요청",
                               alternative_actor="상근 전담관", triggers=["위원회"])
            return Verdict(decision="허용", category="적법", cited_ids=[], reason="ok", condition="",
                           alternative_intent="", alternative_actor="", triggers=[])
        role = system.split("'")[1]
        if role == "상근 전담관":
            return Action(intent="사실조사", description="학부모 진술을 받는다", target="학부모",
                          notify=["외부인"], rationale="")
        return Action(intent="지원요청", description="도움 요청", target="",
                      notify=["상근 전담관"], rationale="")

    monkeypatch.setattr(compliance, "call_structured", fake)
    monkeypatch.setattr(actors, "call_structured", fake)
    run = run_agents(SPEC, "integrated", _r(), 5)
    assert run.mode == "llm"
    lead_turns = [t for t in run.turns if t.actor == "상근 전담관"]
    assert lead_turns and lead_turns[0].review.verdict.cited_ids == ["ord-15"]  # 없는 id는 걸러짐
    assert all(n != "외부인" for t in run.turns for n in t.review.action.notify)
    # 차단되면 대안 역할(상근 전담관)이 바로 다음 차례를 받는다
    i = run.turns.index(lead_turns[0])
    assert run.turns[i + 1].actor == "상근 전담관"
    assert {"Action", "Verdict"} <= set(calls)
