from collector.law_api import parse_law_xml
from collector.html_page import parse_html
from collector.pipeline import load_seed, merge
from collector.schema import Document
from rag.retriever import Retriever
from sim.engine import SimConfig, list_structures, run
from sim.explain import rule_based
from sim.metrics import summarize, to_frame

LAW_XML = """<법령><기본정보><법령명_한글>교원지위법</법령명_한글></기본정보><조문>
<조문단위 조문키="0001000"><조문번호>1</조문번호><조문여부>조문</조문여부><조문제목>목적</조문제목>
<조문내용>제1조(목적) 이 법은 교원의 지위를 향상시킨다.</조문내용></조문단위>
<조문단위 조문키="0002000"><조문번호>2</조문번호><조문여부>전문</조문여부><조문내용>제2장 보호</조문내용></조문단위>
<조문단위 조문키="0015000"><조문번호>15</조문번호><조문여부>조문</조문여부><조문제목>보호</조문제목>
<조문내용>제15조(보호)</조문내용><항><항내용>① 교육감은 교원을 보호한다.</항내용></항></조문단위>
</조문></법령>"""

ORD_XML = """<LawService><자치법규기본정보><자치법규명>경기도교육청 교권보호전담관 운영 조례</자치법규명></자치법규기본정보>
<조문><조 조문번호="001500"><조제목>권한의 한계</조제목><조내용>제15조(권한의 한계) 전담관은 조사권이 없다.</조내용></조></조문></LawService>"""


def test_parse_law_xml_skips_chapter_headings_and_keeps_paragraphs():
    docs = parse_law_xml(LAW_XML, source_type="law", url="u", doc_prefix="law0")
    assert [d.article_no for d in docs] == ["제1조", "제15조"]
    assert "교육감은 교원을 보호한다" in docs[1].text
    assert docs[0].verified and docs[0].reliability == "A"


def test_parse_ordinance_six_digit_article_number():
    docs = parse_law_xml(ORD_XML, source_type="ordinance", url="u", doc_prefix="ord0")
    assert docs[0].article_no == "제15조"
    assert "조사권이 없다" in docs[0].text


def test_merge_replaces_seed_summary_with_collected_article():
    seed = load_seed()
    live = [Document("x", "ordinance", "조례 제15조", "원문", article_no="제15조", verified=True)]
    merged = merge(seed, live)
    fifteen = [d for d in merged if d.source_type == "ordinance" and d.article_no == "제15조"]
    assert len(fifteen) == 1 and fifteen[0].verified


def test_parse_html_extracts_title_date_text():
    html = """<html><head><meta property="og:title" content="교권보호단 출범"></head><body>
    <article><p>2026.8.22 발대식을 열고 8월 24일부터 실무에 투입했다고 밝혔다.</p><p>짧음</p></article></body></html>"""
    d = parse_html(html, "https://example.com/a", "C")
    assert d.title == "교권보호단 출범" and d.meta["date"] == "2026-08-22"
    assert "짧음" not in d.text


def test_retriever_finds_authority_limit_article():
    r = Retriever(load_seed())
    ids = [h.doc.id for h in r.search("전담관 조사권 심의 의결권", k=3)]
    assert "ord-15" in ids


def _run(key, **kw):
    s = list_structures()[key]
    return run(SimConfig(s, days=40, seed=3, **kw), Retriever(load_seed()))


def test_same_case_stream_across_structures():
    a = [(c.id, c.type, round(c.arrival, 3)) for c in _run("A_distributed")]
    b = [(c.id, c.type, round(c.arrival, 3)) for c in _run("B_gyeonggi")]
    assert sorted(a) == sorted(b)


def test_integration_reduces_teacher_burden():
    import pandas as pd
    df = pd.concat([to_frame(_run("A_distributed"), "A"), to_frame(_run("B_gyeonggi"), "B")])
    s = summarize(df)
    assert s.loc["B", "contacts"] < s.loc["A", "contacts"]
    assert s.loc["B", "repeats"] < s.loc["A", "repeats"]
    assert s.loc["B", "coordination"] > s.loc["A", "coordination"]


def test_linkage_and_manual_conditions_matter():
    import pandas as pd
    on = to_frame(_run("B_gyeonggi"), "on")
    off = to_frame(_run("B_gyeonggi", overrides={"linkage_procedure": False, "manual": False}), "off")
    s = summarize(pd.concat([on, off]))
    assert s.loc["on", "duplicates"] == 0 and s.loc["off", "duplicates"] > 0
    assert s.loc["off", "misroutes"] > s.loc["on", "misroutes"]


def test_scenario_case_is_traced_with_citations():
    spec = {"name": "1호", "type": "악성민원", "severity": 3,
            "needs": ["상담", "법률", "수사연계"], "analyzable": False}
    s = list_structures()["B_gyeonggi"]
    cases = run(SimConfig(s, days=30, seed=1), Retriever(load_seed()), [(spec, 5.0)])
    c = next(c for c in cases if c.label == "1호")
    assert c.closed is not None
    actors = {e["actor"] for e in c.trace}
    assert "교육감(단장)" in actors
    assert any(e["cite"] == "ord-15" for e in c.trace)


def test_rule_based_explanation_without_api_key():
    import pandas as pd
    df = pd.concat([to_frame(_run("A_distributed"), "A"), to_frame(_run("B_gyeonggi"), "B")])
    text = rule_based(summarize(df), "A", "B")
    assert "핵심 결과" in text and "사고실험" in text
