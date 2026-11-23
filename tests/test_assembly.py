import httpx
import pytest

from collector import assembly as asm
from collector import pipeline
from sim import calibration as cal

BILL = {"BILL_ID": "PRC_X", "BILL_NO": "2222748", "BILL_NAME": "교원의 지위 향상 및 교육활동 보호를 위한 특별법 일부개정법률안",
        "COMMITTEE": "교육위원회", "PROPOSE_DT": "2026-11-12", "PROC_RESULT": None, "AGE": "22",
        "DETAIL_LINK": "http://likms.assembly.go.kr/bill/billDetail.do?billId=PRC_X", "PROPOSER": "임이자의원 등 11인",
        "RST_PROPOSER": "임이자", "COMMITTEE_DT": "2026-11-13", "CMT_PRESENT_DT": None, "CMT_PROC_DT": None}
SUMMARY = "제안이유 및 주요내용\n\n 현행법은 교원의 정당한 교육활동과 관련된 ... 무고성ㆍ보복성 고소 ..."


def _page(service, rows, total=None):
    return {service: [{"head": [{"list_total_count": total if total is not None else len(rows)},
                                {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}]}, {"row": rows}]}


def _client(bills, summaries):
    def h(req):
        svc = req.url.path.rsplit("/", 1)[-1]
        if svc == asm.BILLS:
            name = req.url.params["BILL_NAME"]
            return httpx.Response(200, json=_page(svc, [b for b in bills if name in b["BILL_NAME"]]))
        no = req.url.params["BILL_NO"]
        return httpx.Response(200, json=_page(svc, [{"BILL_NO": no, "SUMMARY": summaries.get(no, "")}]))
    return httpx.Client(transport=httpx.MockTransport(h))


def test_collect_bills_dedupes_filters_and_builds_documents():
    other = dict(BILL, BILL_NO="2220001", BILL_NAME="초ㆍ중등교육법 일부개정법률안", PROPOSE_DT="2026-10-01")
    old = dict(BILL, BILL_NO="2100001", PROPOSE_DT="2023-01-01")
    cfg = {"since": "2024-05-30", "queries": [{"name": "교원의 지위"}, {"name": "교육활동"},
                                              {"name": "중등교육법", "must_contain": ["교원"]}]}
    docs = asm.collect_bills(cfg, key="k", client=_client([BILL, other, old], {"2222748": SUMMARY, "2220001": "급식 관련"}),
                             delay=0, log=lambda *_: None)
    assert [d.id for d in docs] == ["bill-2222748"]           # 중복 제거, 기간·must_contain 필터
    d = docs[0]
    assert d.source_type == "bill" and d.reliability == "A" and d.verified
    assert "무고성" in d.text and "의안번호 2222748" in d.text and d.meta["stage"] == "소관위 회부"
    assert d.url.startswith("http://likms.assembly.go.kr")


def test_no_key_skips(monkeypatch):
    monkeypatch.delenv("ASSEMBLY_KEY", raising=False)
    assert asm.collect_bills({"queries": [{"name": "교권"}]}, log=lambda *_: None) == []
    assert asm.check_key() == {"ok": False, "reason": "ASSEMBLY_KEY 없음"}


def test_check_key_hides_key_and_rejects_sample():
    def bad(req):
        return httpx.Response(200, json={"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}})
    st = asm.check_key("SECRET9", client=httpx.Client(transport=httpx.MockTransport(bad)))
    assert not st["ok"] and "SECRET9" not in st["reason"]
    sample = _client([dict(BILL, BILL_NO=str(i), BILL_NAME="교육 x") for i in range(5)], {})
    assert not asm.check_key("k", client=sample)["ok"]
    full = _client([dict(BILL, BILL_NO=str(i), BILL_NAME="교육 x") for i in range(8)], {})
    assert asm.check_key("k", client=full)["ok"]


@pytest.mark.parametrize("b,expected", [
    ({"PROC_RESULT": "원안가결"}, "본회의 원안가결"),
    ({"CMT_PROC_DT": "2026-01-01", "CMT_PROC_RESULT_CD": "대안반영폐기"}, "소관위 대안반영폐기"),
    ({"CMT_PRESENT_DT": "2026-01-01"}, "소관위 상정"),
    ({}, "접수"),
])
def test_stage(b, expected):
    assert asm.stage(b) == expected


def test_cached_bills_uses_cache_and_survives_failure(tmp_path, monkeypatch):
    p = tmp_path / "b.jsonl"
    monkeypatch.delenv("ASSEMBLY_KEY", raising=False)
    assert asm.cached_bills({}, path=p) == []
    monkeypatch.setenv("ASSEMBLY_KEY", "k")
    doc = asm.bill_document(BILL, SUMMARY)
    monkeypatch.setattr(asm, "collect_bills", lambda *a, **k: [doc])
    assert [d.id for d in asm.cached_bills({}, path=p)] == ["bill-2222748"] and p.exists()

    def boom(*a, **k):
        raise RuntimeError("network")
    monkeypatch.setattr(asm, "collect_bills", boom)
    assert [d.id for d in asm.cached_bills({}, path=p, ttl=0)] == ["bill-2222748"]


def test_pipeline_lists_bills_and_snapshots_them(monkeypatch):
    assert "bills" in pipeline.COLLECTORS and pipeline.KEYS["bills"] == "ASSEMBLY_KEY"
    assert pipeline.snapshot_docs([asm.bill_document(BILL, SUMMARY)])
    monkeypatch.delenv("ASSEMBLY_KEY", raising=False)
    assert not any(d.source_type == "bill" for d in pipeline.load_corpus())


def test_data_sources_table_lists_every_key():
    t = cal.data_sources_table()
    assert {"LAW_OC", "ASSEMBLY_KEY", "GG_DATA_KEY", "NEIS_KEY", "ANTHROPIC_API_KEY", "GOOGLE_TRANSLATE_API_KEY"} <= set(t["키"])
    for s in cal.load()["sources"].values():   # measured.yaml 의 원자료는 모두 출처 표에 있다
        assert s["url"] in set(t["링크"]), s["title"]


def test_cached_law_docs_and_load_corpus_replace_seed(tmp_path, monkeypatch):
    from collector.schema import Document
    law = Document(id="ord-live-6", source_type="ordinance", title="조례 제6조", text="x" * 200, article_no="제6조",
                   url="https://www.law.go.kr/x", reliability="A", verified=True)
    p = tmp_path / "law.jsonl"
    monkeypatch.delenv("LAW_OC", raising=False)
    assert pipeline.cached_law_docs(path=p) == []
    monkeypatch.setenv("LAW_OC", "k")
    monkeypatch.setattr(pipeline, "_collect_law_api", lambda *a: [law])
    assert [d.id for d in pipeline.cached_law_docs(path=p)] == ["ord-live-6"] and p.exists()
    monkeypatch.setattr(pipeline, "_collect_law_api", lambda *a: (_ for _ in ()).throw(RuntimeError("down")))
    assert [d.id for d in pipeline.cached_law_docs(path=p, ttl=0)] == ["ord-live-6"]

    monkeypatch.setattr(pipeline, "cached_law_docs", lambda: [law])
    monkeypatch.setattr(pipeline, "OUT", tmp_path / "none.jsonl")
    docs = pipeline.load_corpus(path=pipeline.OUT, live_bills=False)
    ids = {d.id for d in docs}
    assert "ord-live-6" in ids and "ord-06" not in ids   # 같은 조문번호 시드 요약이 빠짐


def test_check_key_survives_foreign_error_class(monkeypatch):
    """배포 앱이 gg_data 를 다시 읽으면 GgDataError 클래스가 바뀐다. 그래도 check_key 는 예외를 내지 않는다."""
    from collector import assembly

    class OtherError(RuntimeError):
        pass

    def boom(*a, **k):
        raise OtherError("nzmimeepazxkubdpn 요청 실패 (ConnectTimeout)")
    monkeypatch.setattr(assembly, "fetch_rows", boom)
    r = assembly.check_key(key="x")
    assert r["ok"] is False and "연결 실패" in r["reason"]


def test_evidence_page_survives_assembly_failure(monkeypatch):
    import sys
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from collector import assembly, gg_data
    root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("ASSEMBLY_KEY", "x")
    monkeypatch.setenv("GG_DATA_KEY", "x")

    def boom(*a, **k):
        raise ValueError("unexpected")
    monkeypatch.setattr(assembly, "check_key", boom)
    monkeypatch.setattr(gg_data, "check_key", boom)
    monkeypatch.syspath_prepend(str(root / "app"))
    sys.modules.pop("common", None)
    at = AppTest.from_file(str(root / "app" / "pages" / "3_근거_자료.py"), default_timeout=60).run()
    assert not at.exception
