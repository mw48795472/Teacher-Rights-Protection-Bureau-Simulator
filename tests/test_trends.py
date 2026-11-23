import sys
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
    assert list(t["학년도"]) == [2019, 2020, 2021, 2022, 2023, 2024]
    assert "보도" in t.loc[t["학년도"] == 2024, "출처"].iloc[0]


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
    assert len(at.tabs) == 5
