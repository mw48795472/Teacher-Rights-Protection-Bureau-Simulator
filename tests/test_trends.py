import sys

import pandas as pd
from pathlib import Path

from sim import calibration as cal
from sim import trends as tr

ROOT = Path(__file__).resolve().parent.parent


def test_types_by_year_match_yearly_totals():
    ty = tr.types_by_year()
    tot = ty.groupby("학년도")["건수"].sum().to_dict()
    assert tot[2020] == 1197 and tot[2021] == 2269 and tot[2022] == 3035
    assert tot[2023] == sum(cal.load()["committee_types_2023"]["counts"].values())
    shares = ty.groupby("학년도")["비율(%)"].sum()
    assert ((shares - 100).abs() < 0.5).all()


def test_committee_totals_marks_2024_as_report():
    t = tr.committee_totals()
    assert list(t["학년도"]) == [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    assert "보도" in t.loc[t["학년도"] == 2024, "출처"].iloc[0]
    assert t.loc[t["학년도"] == 2025, "건수"].iloc[0] == 4034


def test_law5_compare_has_new_type():
    c = tr.law5_compare().set_index("유형")
    assert c.loc["교육활동 방해", "2022 건수"] == 0
    assert c.loc["교육활동 방해", "2023 건수"] > 0


def test_abuse_compare_rows_sum_to_100():
    c = tr.abuse_compare().set_index("구분")
    assert ((c.sum(axis=1) - 100).abs() < 1).all()
    assert c.iloc[1]["불기소·종결(%)"] > c.iloc[0]["불기소·종결(%)"]


def test_placeholders_empty_without_files():
    if not tr.SIDO_TEACHERS.exists():
        assert tr.sido_teachers().empty
    if not tr.GG_CASES.exists():
        assert tr.launch_effect().empty


def test_launch_effect_with_claim_file(tmp_path, monkeypatch):
    p = tmp_path / "cases.csv"
    p.write_text("접수일,종결일\n2026-05-01,2026-06-10\n2026-09-01,2026-09-21\n", encoding="utf-8")
    monkeypatch.setattr(tr, "GG_CASES", p)
    le = tr.launch_effect()
    assert len(le) == 2


def test_analysis_page_renders(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.syspath_prepend(str(ROOT / "app"))
    sys.modules.pop("common", None)
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "5_실측_분석.py"), default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs) == 6


def test_kosis_teachers_table_and_no_key(monkeypatch):
    from collector import kosis
    rows = [{"C1_NM": "경기도", "PRD_DE": "2024", "DT": "130000", "ITM_NM": "교원수"},
            {"C1_NM": "전라북도", "PRD_DE": "2024", "DT": "20000", "ITM_NM": "교원수"},
            {"C1_NM": "전국", "PRD_DE": "2024", "DT": "500000", "ITM_NM": "교원수"},
            {"C1_NM": "경기도", "PRD_DE": "2024", "DT": "999", "ITM_NM": "학생수"}]
    t = kosis.teachers_table(rows, "교원").set_index("시도")
    assert t.loc["경기", "교원수"] == 130000 and t.loc["전북", "교원수"] == 20000 and "전국" not in t.index
    monkeypatch.delenv("KOSIS_KEY", raising=False)
    import pytest
    with pytest.raises(kosis.KosisError):
        kosis.search("교원")


def test_edufin_parsing_and_keyword(monkeypatch):
    from collector import edufin
    payload = {"opclTotal": [{"head": [{"list_total_count": 3}]},
                             {"row": [{"EDU_NM": "경기도교육청", "SBJ_NM": "교육활동보호 지원", "AMT": 100},
                                      {"EDU_NM": "경기도교육청", "SBJ_NM": "학교시설", "AMT": 900},
                                      {"EDU_NM": "인천광역시교육청", "SBJ_NM": "교원치유 지원", "AMT": 50}]}]}
    rows = edufin._rows(payload)
    assert len(rows) == 3
    hit = edufin.keyword_rows(pd.DataFrame(rows), ["교권", "교육활동보호", "교원치유"])
    assert len(hit) == 2
    assert edufin._error({"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}})
    monkeypatch.delenv("EDUFIN_KEY", raising=False)
    assert edufin.check()["ok"] is False
    assert tr.edufin_budget(fetch=False)[1] in ("no_key", "ok", "no_keyword")


def test_kosis_finds_table_by_search(monkeypatch):
    from collector import kosis
    monkeypatch.setenv("KOSIS_KEY", "x")

    def fake(path, client=None, **p):
        if path == "statisticsSearch.do":
            return [{"ORG_ID": "334", "TBL_ID": "DT_A", "TBL_NM": "시도별 교원수"},
                    {"ORG_ID": "101", "TBL_ID": "DT_B", "TBL_NM": "시도별 교원수"}]
        assert p["tblId"] == "DT_A"
        return [{"C1_NM": n, "PRD_DE": "2024", "DT": "100", "ITM_NM": "교원수"} for n in kosis.SIDO]
    monkeypatch.setattr(kosis, "_get", fake)
    df = kosis.fetch_teachers({"teachers": {"orgId": "334", "item": "교원"}})
    assert df["시도"].nunique() == 17 and "DT_A" in df.attrs["table"]


def test_edufin_parse_body_xml_and_html():
    import pytest
    from collector import edufin
    xml = ("<opclTotal><head><RESULT><CODE>INFO-000</CODE><MESSAGE>정상</MESSAGE></RESULT></head>"
           "<row><EDU_NM>경기도교육청</EDU_NM><AMT>1</AMT></row><row><EDU_NM>인천</EDU_NM><AMT>2</AMT></row></opclTotal>")
    p = edufin.parse_body(xml)
    assert len(p["rows"]) == 2 and edufin._error(p) is None and len(edufin._rows(p)) == 2
    err = edufin.parse_body("<RESULT><CODE>ERROR-290</CODE><MESSAGE>인증키 오류</MESSAGE></RESULT>")
    assert "ERROR-290" in edufin._error(err)
    with pytest.raises(edufin.EdufinError, match="\\*\\*\\*"):
        edufin.parse_body("<html>잘못된 키 SECRETKEY 입니다", key="SECRETKEY")


def _edufin_client(handler):
    import httpx
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_edufin_probe_finds_working_year_format(monkeypatch):
    import httpx
    from collector import edufin
    monkeypatch.setenv("EDUFIN_KEY", "k")
    rows = [{"EDU_NM": f"교육청{i}", "SBJ_NM": "교권보호 지원" if i == 0 else "시설"} for i in range(8)]

    def handler(req):
        ymq = req.url.params.get("YMQ")
        if ymq == "2024":          # 연도 4자리일 때만 자료가 온다
            return httpx.Response(200, json={"opclTotal": [{"head": []}, {"row": rows}]})
        return httpx.Response(200, json={"opclTotal": [{"head": []}, {"row": []}]})
    c = _edufin_client(handler)
    pr = edufin.probe("opclTotal", [2024, 2023], client=c)
    assert pr["ok"] and pr["params"] == {"YMQ": "2024"} and pr["year"] == 2024
    assert edufin.check({"services": [{"requestType": "opclTotal"}], "years": [2024]}, client=c)["ok"]


def test_edufin_probe_flags_key_problem(monkeypatch):
    import httpx
    from collector import edufin
    monkeypatch.setenv("EDUFIN_KEY", "k")
    c = _edufin_client(lambda req: httpx.Response(200, json={"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}}))
    r = edufin.check({"services": [{"requestType": "opclTotal"}], "years": [2024]}, client=c)
    assert not r["ok"] and "키 문제" in r["reason"]


def test_edufin_info_code_is_not_error(monkeypatch):
    import httpx
    from collector import edufin
    monkeypatch.setenv("EDUFIN_KEY", "k")
    rows = [{"ATPT_OFCDC_NM": f"교육청{i}", "AMT": i} for i in range(10)]
    c = _edufin_client(lambda req: httpx.Response(200, json={"RESULT": {"CODE": "INFO", "MESSAGE": "정상 처리되었습니다."},
                                                              "list": rows}))
    pr = edufin.probe("opclTotal", [2024], client=c)
    assert pr["ok"] and len(pr["df"]) == 10


def test_edufin_frame_and_committee_join():
    raw = pd.DataFrame({"회계연도": [2024] * 17 + [2023] * 17,
                        "ATPT_OFCDC_NM": [f"{s}교육청" for s in tr.SIDO_SHORT] * 2,
                        "ITEM": ["세출"] * 34, "IDX": list(range(34)),
                        "AMT": [f"{(i + 1) * 1_000_000_000_000:,}" for i in range(34)]})
    fd, meta = tr.edufin_frame(raw)
    assert meta["sido"] == "ATPT_OFCDC_NM" and meta["nums"] == ["AMT"] and fd["시도"].nunique() == 17
    fis = tr.edufin_by_sido(fd, "AMT")
    cv = tr.committee_vs_fiscal(fis, "AMT")
    assert len(cv) == 17 and (cv["재정 기준 연도"] == 2024).all() and cv["심의 건수 / 재정 1조"].notna().all()


def test_fiscal_regression():
    cv = pd.DataFrame({"시도": list(tr.SIDO_SHORT), "AMT": [(i + 1) * 1e12 for i in range(17)],
                       "심의 건수 (2024.3.28~6.30)": [10 + 5 * (i + 1) + (i % 3) for i in range(17)]})
    reg, rt = tr.fiscal_regression(cv, "AMT")
    assert reg["n"] == 17 and 4.5 < reg["slope"] < 5.5 and reg["r2"] > 0.9 and reg["p"] < 0.001
    assert "잔차 (실제−예측)" in rt and len(rt) == 17


def test_kosis_url_and_relaxed_search(monkeypatch):
    from collector import kosis
    assert kosis.candidate_tables({"url": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1YL20711"})[0]["TBL_ID"] == "DT_1YL20711"
    monkeypatch.setenv("KOSIS_KEY", "x")
    monkeypatch.setattr(kosis, "_get", lambda path, client=None, **p: [
        {"ORG_ID": "101", "TBL_ID": "DT_X", "TBL_NM": "시·도별 학교급별 교원수"},
        {"ORG_ID": "334", "TBL_ID": "DT_Y", "TBL_NM": "학교급별 학생수"}])
    c = kosis.candidate_tables({"orgId": "334"})
    assert [r["TBL_ID"] for r in c] == ["DT_X"] and "DT_Y" in kosis.hits_summary()
