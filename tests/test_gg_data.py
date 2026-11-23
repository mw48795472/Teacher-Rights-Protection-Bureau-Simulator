import json

import httpx
import pytest

from collector import gg_data as gg

POLICE_ROW = {"SIGUN_NM": "수원시", "SIGUN_CD": "41110", "LOCAL_INST_NM": "경기남부청", "POLCSTTN_NM": "수원장안",
              "GOVOFC_NM": "장안", "DIV_NM": "지구대", "DATA_STD_DE": "20251231",
              "REFINE_LOTNO_ADDR": "", "REFINE_ROADNM_ADDR": "경기도 수원시 장안구 송정로 113",
              "REFINE_WGS84_LOGT": 127.0095593, "REFINE_WGS84_LAT": 37.2958093}


def _page(service, rows, total):
    return {service: [{"head": [{"list_total_count": total},
                                {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}},
                                {"api_version": "1.0"}]}, {"row": rows}]}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_rows_pages_until_total():
    seen = []

    def h(req):
        seen.append(dict(req.url.params))
        n = int(req.url.params["pIndex"])
        rows = [dict(POLICE_ROW, GOVOFC_NM=f"관서{n}-{i}") for i in range(3 if n < 3 else 1)]
        return httpx.Response(200, json=_page("Ptrldvsnsubpolcstus", rows, 7))

    rows = gg.fetch_rows("Ptrldvsnsubpolcstus", "k", page_size=3, client=_client(h))
    assert len(rows) == 7 and len(seen) == 3
    assert seen[0]["KEY"] == "k" and seen[0]["Type"] == "json"


def test_invalid_key_error_does_not_leak_key():
    def h(req):
        return httpx.Response(200, json={"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}})

    st = gg.check_key("SECRET123", client=_client(h))
    assert not st["ok"] and "ERROR-290" in st["reason"] and "SECRET123" not in st["reason"]

    def boom(req):
        raise httpx.ConnectError("fail " + str(req.url))
    st = gg.check_key("SECRET123", client=_client(boom))
    assert not st["ok"] and "SECRET123" not in st["reason"]


def test_sample_only_response_is_not_ok():
    def h(req):
        return httpx.Response(200, json=_page("Ptrldvsnsubpolcstus", [POLICE_ROW] * 5, 357))
    assert not gg.check_key("k", client=_client(h))["ok"]

    def full(req):
        return httpx.Response(200, json=_page("Ptrldvsnsubpolcstus", [POLICE_ROW] * 20, 357))
    assert gg.check_key("k", client=_client(full))["ok"]


def test_no_key(monkeypatch):
    monkeypatch.delenv("GG_DATA_KEY", raising=False)
    assert gg.check_key() == {"ok": False, "reason": "GG_DATA_KEY 없음"}
    with pytest.raises(gg.GgDataError):
        gg.fetch_table("police")


def test_tables_map_to_offices():
    rows = [POLICE_ROW, dict(POLICE_ROW, SIGUN_NM="과천시", REFINE_ROADNM_ADDR="경기도 과천시 x"),
            dict(POLICE_ROW, SIGUN_NM="오산시"), dict(POLICE_ROW, SIGUN_NM="", REFINE_ROADNM_ADDR="경기도 하남시 y")]
    t = gg.police_table(rows)
    assert list(t.office) == ["수원", "안양과천", "화성오산", "광주하남"]
    assert gg.by_office(t).set_index("office")["count"].sum() == 4
    s = gg.schools_table([{"SCHOOL_DIV_NM": "초등학교", "PLVTINST_DIV_NM": "공립", "FACLT_NM": "가평초등학교",
                           "REFINE_LOTNO_ADDR": "", "REFINE_ROADNM_ADDR": "경기도 가평군 가평읍 향교로 23",
                           "REFINE_WGS84_LOGT": 127.5, "REFINE_WGS84_LAT": 37.8}])
    assert s.loc[0, "office"] == "가평" and s.loc[0, "lat"] == pytest.approx(37.8)


def test_no_data_code_returns_empty():
    rows, total = gg.parse_openapi({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}, "X")
    assert rows == [] and total == 0
