"""인천 학교·교육지원청 데이터와 교육활동 보호 조직 (인천형 C 구조용).

학교 위치: 공공데이터포털 '전국초중등학교위치표준데이터'(한국교육시설안전원, 2026.10.1. 기준)에서
인천광역시교육청 학교 550곳(초 274, 중 147, 고 129)만 골라 data/schools/incheon_schools.csv 에 담았다.
열: 학교ID, 학교명, 학교급구분, 교육지원청명(짧은 이름), 위도, 경도 (좌표는 소수 5자리).

교육지원청 5곳과 관할 (2026.7. 인천 행정체제 개편 후 구 이름, 학교 주소 기준):
  남부 = 제물포구·영종구·미추홀구·옹진군, 동부 = 남동구·연수구, 북부 = 부평구·계양구,
  서부 = 서해구·검단구, 강화 = 강화군.
교육지원청 좌표는 관할 학교 좌표의 중앙값이다 (지도 표시용, 실제 청사 주소 아님).

조직 인원은 인천광역시교육청 '교육활동보호담당관 구성현황'(2026.6.30. 갱신) 원문에서 옮겼다. ORG 참고.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .gyeonggi import LEVELS, Office

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "schools" / "incheon_schools.csv"


class IncheonOffice(Office):
    @property
    def name(self) -> str:
        return f"인천광역시{self.key}교육지원청"


# 인천광역시교육청 산하 5개 교육지원청 (좌표: 관할 학교 좌표 중앙값)
OFFICES = [IncheonOffice(*o) for o in [
    ("남부", 37.471, 126.637), ("동부", 37.421, 126.697), ("북부", 37.512, 126.730),
    ("서부", 37.548, 126.672), ("강화", 37.715, 126.423),
]]
OFFICE_BY_KEY = {o.key: o for o in OFFICES}
JURISDICTION = {"남부": "제물포구·영종구·미추홀구·옹진군", "동부": "남동구·연수구", "북부": "부평구·계양구",
                "서부": "서해구·검단구", "강화": "강화군"}
MAP_VIEW = {"zoom": 9.6, "center": {"lat": 37.52, "lon": 126.60}}

# 교육활동보호담당관 구성현황 (인천광역시교육청 누리집, 2026.6.30. 갱신) — 실측 인원
ORG_URL = "https://hbm.ice.go.kr/ice/cm/cntnts/cntntsView.do?mi=11821&cntntsId=857"
ORG = {
    "교육활동보호담당관": {"담당관": 1},
    "교육활동보호대응팀": {"팀장": 1, "장학사": 4, "행정실무사": 1},
    "교육활동보호센터": {"장학사": 4, "전문상담사": 4},
    "법률지원팀": {"팀장": 1, "주무관": 2, "변호사": 2},
    "교육지원청 교육활동 보호 담당": {o.key: 1 for o in OFFICES},   # 지원청마다 장학사 1명
}
# 교육활동보호 지원단 2기 (2025.12.3. 위촉, 비상근) — 내외일보 2025-12-04 보도
SUPPORT_CORPS = {"법률지원단": 33, "의료지원단": 5, "교육전문가": 5}
SUPPORT_CORPS_URL = "https://www.naewoeilbo.com/news/articleView.html?idxno=2259385"


def org_headcount() -> int:
    """담당관실 상주 인원 (교육지원청 담당 제외)."""
    return sum(sum(v.values()) for k, v in ORG.items() if k != "교육지원청 교육활동 보호 담당")


def load_schools(src=None) -> pd.DataFrame:
    """인천 초·중·고 학교 표. 열: name, level, office, lat, lon, addr, date, provider."""
    cols = ["name", "level", "office", "lat", "lon", "addr", "date", "provider"]
    src = DEFAULT_CSV if src is None else src
    if not hasattr(src, "read") and not Path(src).exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(src, dtype=str, encoding="utf-8-sig")
    out = pd.DataFrame({
        "name": df["학교명"], "level": df["학교급구분"], "office": df["교육지원청명"],
        "lat": pd.to_numeric(df["위도"], errors="coerce"), "lon": pd.to_numeric(df["경도"], errors="coerce"),
        "addr": "", "date": "2026-10-01", "provider": "한국교육시설안전원",
    })
    out = out[out["level"].isin(LEVELS) & out["office"].isin(OFFICE_BY_KEY)].dropna(subset=["lat", "lon"])
    return out[cols].reset_index(drop=True)


def office_weights(schools: pd.DataFrame) -> dict[str, float]:
    """사안이 어느 교육지원청 관할에서 생길지의 비중. 학교 수 비례 (지원청별 교원 수 자료는 아직 없음)."""
    if schools.empty:
        return {o.key: 1.0 for o in OFFICES}
    counts = schools["office"].value_counts()
    return {o.key: float(counts.get(o.key, 0)) for o in OFFICES if counts.get(o.key, 0) > 0}


def hierarchy(schools: pd.DataFrame) -> pd.DataFrame:
    """감독 구조 트리 (sunburst용). 열: id, parent, label, value, role."""
    rows = [
        ("교육부", "", "교육부", "국가: 교원지위법·교육활동 보호 정책"),
        ("인천광역시교육청", "교육부", "인천광역시교육청", "교육감: 시도 교육행정 총괄"),
        ("담당관", "인천광역시교육청", "교육활동보호담당관", "교육감 직속 (2024.1.), 상주 20명, 1395 접수"),
        ("대응팀", "담당관", "교육활동보호대응팀", "팀장 1·장학사 4·행정실무사 1: 사안 접수·대응"),
        ("센터", "담당관", "교육활동보호센터", "장학사 4·전문상담사 4: 심리 상담·치유"),
        ("법률", "담당관", "법률지원팀", "팀장 1·주무관 2·변호사 2 상주 + 위촉 법률지원단 33명"),
    ]
    counts = schools.groupby(["office", "level"]).size() if not schools.empty else None
    for o in OFFICES:
        oid = f"o:{o.key}"
        rows.append((oid, "인천광역시교육청", o.key, f"{o.name} ({JURISDICTION[o.key]}): 교육활동 보호 담당 장학사 1명"))
        rows.append((f"c:{o.key}", oid, "지역교권보호위원회", "침해 여부 심의·조치, 분쟁 조정"))
        if counts is not None:
            for lv in LEVELS:
                n = int(counts.get((o.key, lv), 0))
                if n:
                    rows.append((f"s:{o.key}:{lv}", oid, f"{lv} {n}곳", "관할 학교"))
    df = pd.DataFrame(rows, columns=["id", "parent", "label", "role"])
    df["value"] = 1
    if counts is not None:
        for (off, lv), n in counts.items():
            df.loc[df["id"] == f"s:{off}:{lv}", "value"] = int(n)
    return df
