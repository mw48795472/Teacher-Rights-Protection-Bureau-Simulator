import io

import pandas as pd

from geo.gyeonggi import OFFICES, hierarchy, load_schools, office_key, office_weights
from sim.engine import SimConfig, list_structures, run
from sim.metrics import to_frame

CSV = """학교ID,학교명,학교급구분,운영상태,소재지도로명주소,시도교육청명,교육지원청명,위도,경도
1,가나초등학교,초등학교,운영,경기도 수원시 1,경기도교육청,경기도수원교육지원청,37.26,127.03
2,다라중학교,중학교,운영,경기도 부천시 2,경기도교육청,경기도부천교육지원청,37.50,126.77
3,마바고등학교,고등학교,운영,경기도 안양시 3,경기도교육청,경기도안양과천교육지원청,37.39,126.95
4,사아초등학교,초등학교,폐교,경기도 수원시 4,경기도교육청,경기도수원교육지원청,37.27,127.02
5,서울초등학교,초등학교,운영,서울시 5,서울특별시교육청,서울특별시강남서초교육지원청,37.49,127.03
6,자차특수학교,특수학교,운영,경기도 수원시 6,경기도교육청,경기도수원교육지원청,37.28,127.01
"""


def test_office_key():
    assert office_key("경기도수원교육지원청") == "수원"
    assert office_key("경기도 안양과천교육지원청") == "안양과천"
    assert office_key("서울특별시강남서초교육지원청") is None
    assert len(OFFICES) == 25


def test_load_schools_filters_gyeonggi_open_k12():
    df = load_schools(io.BytesIO(CSV.encode("cp949")))
    assert sorted(df["name"]) == ["가나초등학교", "다라중학교", "마바고등학교"]
    assert set(df["office"]) == {"수원", "부천", "안양과천"}
    assert office_weights(df) == {"수원": 1.0, "안양과천": 1.0, "부천": 1.0}


def test_no_csv_falls_back_to_offices():
    empty = pd.DataFrame(columns=["name", "level", "office", "lat", "lon", "addr"])
    assert len(office_weights(empty)) == 25
    h = hierarchy(empty)
    assert (h["label"] == "지역교권보호위원회").sum() == 25


def test_office_committees_have_capacity():
    s = list_structures()["B_gyeonggi"]
    w = {"수원": 10.0, "연천": 1.0}
    big = to_frame(run(SimConfig(s, days=60, arrivals_per_day=6, offices=w, committee_capacity=50)), "B")
    small = to_frame(run(SimConfig(s, days=60, arrivals_per_day=6, offices=w, committee_capacity=2)), "B")
    assert set(big["office"]) == {"수원", "연천"}
    # 정원이 작으면 사안이 많은 교육지원청 위원회에서 대기가 길어진다
    suwon = lambda df: df[df.office == "수원"].committee_wait_days.mean()
    assert suwon(small) > suwon(big)


def _neis_client(pages, total):
    import httpx

    def handler(req):
        i = int(req.url.params["pIndex"]) - 1
        if req.url.params["KEY"] == "bad":
            return httpx.Response(200, json={"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}})
        return httpx.Response(200, json={"schoolInfo": [
            {"head": [{"list_total_count": total}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}}]},
            {"row": pages[i]}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_neis_fetch_paginates_and_reconciles():
    import pytest

    from geo import neis
    row = lambda n, kind, org: {"SCHUL_NM": n, "SCHUL_KND_SC_NM": kind, "JU_ORG_NM": org, "SD_SCHUL_CODE": n,
                                "ORG_TELNO": "031", "HMPG_ADRES": "http://x", "ORG_RDNMA": "주소"}
    pages = [[row("가나초등학교", "초등학교", "경기도수원교육지원청"), row("특수학교", "특수학교", "경기도수원교육지원청")],
             [row("새로중학교", "중학교", "경기도부천교육지원청"), row("마바고등학교", "고등학교", "경기도교육청")]]
    got = neis.fetch_schools("k", client=_neis_client(pages, 4))
    assert sorted(got["name"]) == ["가나초등학교", "마바고등학교", "새로중학교"]
    schools = load_schools(io.BytesIO(CSV.encode("cp949")))
    merged, stats = neis.reconcile(schools, got)
    assert stats["일치"] == 2 and stats["NEIS에만"] == 1 and stats["위치데이터에만"] == 1
    assert merged.loc[merged.name == "가나초등학교", "phone"].item() == "031"
    with pytest.raises(neis.NeisError, match="ERROR-290"):
        neis.fetch_schools("bad", client=_neis_client(pages, 4))
