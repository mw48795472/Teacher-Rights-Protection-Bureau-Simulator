import random
from pathlib import Path

import pandas as pd
import pytest

from collector.documents import extract_text
from collector.measured import CITY_TO_OFFICE, build_office_table, read_kr_csv
from geo.gyeonggi import OFFICES
from sim import calibration as cal
from sim.cases import CASE_TYPES, random_case

ROOT = Path(__file__).resolve().parent.parent
M = cal.load()


def test_transcribed_totals_match_source_tables():
    assert sum(M["committee_types_2023"]["counts"].values()) == 5050
    assert sum(M["committee_levels_2023"]["counts"].values()) == 5050
    assert M["committee_cases"]["by_year"][2023] == 5050
    assert sum(M["committee_outcomes"]["school_2023"].values()) == 5050
    assert sum(M["committee_outcomes"]["office_first_month_2024"].values()) == 286
    assert sum(M["superintendent_opinions"]["opinions"].values()) == 385
    assert sum(M["superintendent_opinions"]["closed_outcomes"].values()) == 148
    assert sum(M["hotline_1395"]["by_type"].values()) == 501
    assert sum(M["guardian_measures"]["2023"].values()) == 354
    # 2023 센터 이용 합계 76,578 (원자료 표의 '이용 건수')
    assert sum(M["center_usage"]["by_year"][2023].values()) == 76578


def test_numbers_appear_in_raw_files():
    kbw = extract_text((ROOT / cal.source("kbw")["file"]).read_bytes(), "x.hwpx")
    for n in ("5,050", "1,147", "2,227", "3,108"):
        assert n in kbw
    pdf = extract_text((ROOT / cal.source("followup")["file"]).read_bytes(), "x.pdf")
    for n in ("385건", "4,953", "501"):
        assert n in pdf


def test_mapping_covers_every_committee_type_once():
    used = [c for r in M["case_mix_mapping"].values() if isinstance(r, list) for c in r]
    assert sorted(used) == sorted(M["committee_types_2023"]["counts"])
    assert set(M["case_mix_mapping"]) == set(CASE_TYPES)


def test_measured_case_mix_sums_to_one_and_keeps_unmeasured_assumption():
    mix = cal.measured_case_mix()
    assert list(mix) == list(CASE_TYPES)
    assert sum(mix.values()) == pytest.approx(1.0)
    assert mix["민·형사 소송"] == pytest.approx(CASE_TYPES["민·형사 소송"]["weight"])
    assert mix["폭언·폭행"] > mix["단순 상담"] > mix["무고성 아동학대 신고"] > mix["악성민원"]


def test_random_case_uses_active_weights(monkeypatch):
    monkeypatch.setattr(cal, "case_weights", lambda: {k: (1.0 if k == "악성민원" else 0.0) for k in CASE_TYPES})
    rng = random.Random(1)
    types = {random_case(rng, 0.0, i).type.replace(" (복합)", "") for i in range(30)}
    assert types == {"악성민원"}


def test_office_table_covers_all_25_offices():
    t = cal.office_table()
    assert sorted(t.office) == sorted(o.key for o in OFFICES)
    assert t.teachers.sum() > 100_000
    w = cal.office_teacher_weights()
    assert set(w) == {o.key for o in OFFICES}
    assert set(CITY_TO_OFFICE.values()) == {o.key for o in OFFICES}


def _sheet(rows, value_col, n_cols):
    head = [[None] * n_cols for _ in range(4)]
    body = []
    for r in rows:
        line = [None] * n_cols
        line[0], line[2], line[3], line[4], line[6] = "경기", r[0], r[1], r[2], r[3]
        line[value_col] = r[4]
        body.append(line)
    return pd.DataFrame(head + body)


def test_build_office_table_maps_province_schools_by_city(tmp_path):
    rows_t = [("수원", "수원시", "초등학교", "가초", 50), ("경기", "과천시", "고등학교", "나고", 70),
              ("안양·과천", "안양시", "중학교", "다중", 30), ("경기", "과천시", "평생교육시설학교", "라", 9)]
    rows_s = [(a, b, c, d, v * 10) for a, b, c, d, v in rows_t]
    p = tmp_path / "s.xlsx"
    with pd.ExcelWriter(p) as w:
        _sheet(rows_t, 8, 20).to_excel(w, sheet_name="교원수", header=False, index=False)
        _sheet(rows_s, 9, 20).to_excel(w, sheet_name="학급 구분별 학급 및 학생수", header=False, index=False)
    t = build_office_table(p).set_index("office")
    assert t.loc["안양과천", "teachers"] == 100 and t.loc["안양과천", "schools"] == 2
    assert t.loc["수원", "students"] == 500
    assert "라" not in t.index


def test_read_kr_csv_cp949_and_trailing_spaces(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("연도,검거건수_건\n2023,13015 \n".encode("cp949"))
    df = read_kr_csv(p)
    assert df.loc[0, "검거건수_건"] == 13015
    ab = cal.child_abuse_gyeonggi()
    assert not ab.empty and 2024 in set(ab["연도"])


def test_assumption_table_marks_measured_and_assumed():
    t = cal.assumption_table()
    assert {"반영", "가정 유지 (정보공개청구 필요)"} <= set(t["시뮬레이터"])
    assert t["출처"].str.contains("교육부").any()


def test_evidence_page_renders_with_sources_and_key_status(monkeypatch):
    import sys
    from streamlit.testing.v1 import AppTest
    for k in ("GG_DATA_KEY", "ASSEMBLY_KEY", "NEIS_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.syspath_prepend(str(ROOT / "app"))
    sys.modules.pop("common", None)
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "3_근거_자료.py"), default_timeout=60).run()
    assert not at.exception
    assert any(e.label == "API 키 연결 상태" for e in at.expander)


def test_evidence_example_question_fills_search(monkeypatch):
    import sys
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.syspath_prepend(str(ROOT / "app"))
    sys.modules.pop("common", None)
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "3_근거_자료.py"), default_timeout=60).run()
    btn = next(b for b in at.button if b.label.startswith("지역교권보호위원회"))
    btn.click().run()
    assert not at.exception
    assert at.text_input(key="evidence_q").value == btn.label


def test_evidence_page_recovers_from_stale_calibration_module(monkeypatch):
    """배포 앱에 예전 sim.calibration 이 남아 있어도(함수 없음) 근거 자료 화면이 열린다."""
    import sys
    from streamlit.testing.v1 import AppTest
    monkeypatch.delattr(cal, "data_sources_table")
    monkeypatch.syspath_prepend(str(ROOT / "app"))
    sys.modules.pop("common", None)
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "3_근거_자료.py"), default_timeout=60).run()
    assert not at.exception
