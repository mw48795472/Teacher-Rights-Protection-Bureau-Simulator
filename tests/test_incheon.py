"""인천형(C): 인천 학교·교육지원청·조직 데이터가 들어가는지."""
from geo import incheon
from geo.regions import module, region_of
from sim.calibration import region_case_scale
from sim.engine import SimConfig, list_structures, run
from sim.metrics import to_frame


def test_incheon_schools_and_offices():
    s = incheon.load_schools()
    assert len(s) == 550
    assert s["level"].value_counts().to_dict() == {"초등학교": 274, "중학교": 147, "고등학교": 129}
    assert set(s["office"]) == {o.key for o in incheon.OFFICES} == {"남부", "동부", "북부", "서부", "강화"}
    # 좌표가 인천(옹진군 섬 포함) 안에 있다
    assert s["lat"].between(37.0, 38.0).all() and s["lon"].between(124.5, 126.9).all()
    w = incheon.office_weights(s)
    assert w["동부"] == 147 and w["강화"] == 37


def test_incheon_hierarchy_and_org():
    h = incheon.hierarchy(incheon.load_schools())
    assert (h["label"] == "지역교권보호위원회").sum() == 5
    assert "교육활동보호담당관" in set(h["label"])
    assert incheon.org_headcount() == 20   # 구성현황 표: 담당관 1 + 대응팀 6 + 센터 8 + 법률지원팀 5


def test_c_structure_uses_incheon_region():
    S = list_structures()
    assert region_of(S["C_incheon"]) == "인천" and region_of(S["B_gyeonggi"]) == "경기"
    assert module("인천") is incheon
    p = S["C_incheon"]["params"]
    assert p["nonregular_officers"] == sum(v for v in p["nonregular_pool"].values() if not isinstance(v, str)) == 43
    assert 0.2 < region_case_scale("인천") < 0.3 and region_case_scale("경기") == 1.0


def test_resident_lawyers_join_without_scheduling():
    s = list_structures()["C_incheon"]
    w = incheon.office_weights(incheon.load_schools())
    cases = run(SimConfig(s, days=60, arrivals_per_day=0.8, offices=w))
    actors = {e["actor"] for c in cases for e in c.trace}
    assert "법률지원팀 상주 변호사" in actors and "대응 장학사" in actors
    assert set(to_frame(cases, "C")["office"]) <= set(w)


def test_gyeonggi_scenario_office_is_remapped_in_incheon():
    s = list_structures()["C_incheon"]
    w = incheon.office_weights(incheon.load_schools())
    spec = {"name": "t", "type": "악성민원", "severity": 2, "needs": ["상담", "법률"], "office": "의정부"}
    cases = run(SimConfig(s, days=20, arrivals_per_day=0.5, offices=w), scenarios=[(spec, 2.0)])
    c = next(c for c in cases if c.label == "t")
    assert c.office in w
