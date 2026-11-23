"""경기도 학교·교육지원청 데이터와 감독 구조.

학교 위치는 공공데이터포털 '전국초중등학교위치표준데이터' CSV를 읽는다.
(https://www.data.go.kr 에서 '전국초중등학교위치표준데이터' 검색 → CSV 내려받기, 키 불필요)
CSV가 없으면 25개 교육지원청만으로 구조와 지도를 그린다.

교육지원청 좌표는 해당 시청 부근의 대략 위치다 (지도 표시용, 실제 청사 주소 아님).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "schools" / "gyeonggi_schools.csv"


@dataclass(frozen=True)
class Office:
    key: str      # 짧은 이름 (예: 수원)
    lat: float
    lon: float

    @property
    def name(self) -> str:
        return f"경기도{self.key}교육지원청"


# 경기도교육청 산하 25개 교육지원청 (좌표는 대략 위치)
OFFICES = [Office(*o) for o in [
    ("수원", 37.263, 127.029), ("성남", 37.420, 127.127), ("의정부", 37.738, 127.034),
    ("부천", 37.503, 126.766), ("광명", 37.479, 126.865), ("안양과천", 37.394, 126.957),
    ("동두천양주", 37.810, 127.050), ("고양", 37.658, 126.832), ("구리남양주", 37.620, 127.180),
    ("안산", 37.322, 126.831), ("평택", 36.992, 127.113), ("화성오산", 37.180, 126.950),
    ("시흥", 37.380, 126.803), ("군포의왕", 37.362, 126.935), ("용인", 37.241, 127.178),
    ("이천", 37.272, 127.435), ("광주하남", 37.470, 127.230), ("여주", 37.298, 127.637),
    ("양평", 37.492, 127.488), ("김포", 37.615, 126.716), ("파주", 37.760, 126.780),
    ("안성", 37.008, 127.280), ("연천", 38.096, 127.075), ("가평", 37.831, 127.510),
    ("포천", 37.895, 127.200),
]]
OFFICE_BY_KEY = {o.key: o for o in OFFICES}

LEVELS = ("초등학교", "중학교", "고등학교")

# 표준데이터 열 이름 (기관마다 조금씩 달라 후보를 둔다)
COLS = {
    "name": ("학교명",),
    "level": ("학교급구분", "학교급"),
    "edu": ("시도교육청명",),
    "office": ("교육지원청명",),
    "lat": ("위도",),
    "lon": ("경도",),
    "status": ("운영상태",),
    "addr": ("소재지도로명주소", "소재지지번주소"),
}


def office_key(name: str) -> str | None:
    """'경기도수원교육지원청' → '수원'. 매칭이 안 되면 None."""
    s = re.sub(r"\s", "", str(name))
    s = s.replace("경기도", "").replace("교육지원청", "")
    if s in OFFICE_BY_KEY:
        return s
    for o in OFFICES:  # '안양·과천' 같은 표기 차이
        if re.sub(r"[·ㆍ\-]", "", s) == o.key:
            return o.key
    return None


def _read_csv(src) -> pd.DataFrame:
    raw = src.read() if hasattr(src, "read") else Path(src).read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 읽지 못했습니다 (UTF-8 또는 CP949여야 합니다).")


def _pick(df: pd.DataFrame, key: str) -> str | None:
    return next((c for c in COLS[key] if c in df.columns), None)


def load_schools(src=None) -> pd.DataFrame:
    """경기도 초·중·고 학교 표. 열: name, level, office, lat, lon, addr.

    src는 파일 경로나 업로드된 파일 객체. None이면 data/schools/gyeonggi_schools.csv를 찾고,
    없으면 빈 표를 돌려준다.
    """
    empty = pd.DataFrame(columns=["name", "level", "office", "lat", "lon", "addr"])
    if src is None:
        if not DEFAULT_CSV.exists():
            return empty
        src = DEFAULT_CSV
    df = _read_csv(src)
    need = {k: _pick(df, k) for k in COLS}
    missing = [COLS[k][0] for k in ("name", "level", "office", "lat", "lon") if need[k] is None]
    if missing:
        raise ValueError(f"표준데이터 형식이 아닙니다. 없는 열: {', '.join(missing)}")
    if need["edu"]:
        df = df[df[need["edu"]].fillna("").str.contains("경기")]
    if need["status"]:
        df = df[~df[need["status"]].fillna("").str.contains("폐교|휴교")]
    out = pd.DataFrame({
        "name": df[need["name"]],
        "level": df[need["level"]].fillna(""),
        "office": df[need["office"]].map(office_key),
        "lat": pd.to_numeric(df[need["lat"]], errors="coerce"),
        "lon": pd.to_numeric(df[need["lon"]], errors="coerce"),
        "addr": df[need["addr"]] if need["addr"] else "",
    })
    out = out[out["level"].isin(LEVELS) & out["office"].notna()].dropna(subset=["lat", "lon"])
    return out.reset_index(drop=True)


def office_weights(schools: pd.DataFrame) -> dict[str, float]:
    """사안이 어느 교육지원청 관할 학교에서 생길지의 비중. 학교 수에 비례, 데이터가 없으면 균등."""
    if schools.empty:
        return {o.key: 1.0 for o in OFFICES}
    counts = schools["office"].value_counts()
    return {o.key: float(counts.get(o.key, 0)) for o in OFFICES if counts.get(o.key, 0) > 0}


def hierarchy(schools: pd.DataFrame) -> pd.DataFrame:
    """감독 구조 트리 (sunburst용). 열: id, parent, label, value, role."""
    rows = [
        ("교육부", "", "교육부", "국가: 교원지위법·교육활동 보호 정책"),
        ("경기도교육청", "교육부", "경기도교육청", "교육감: 시도 교육행정 총괄"),
        ("교권보호단", "경기도교육청", "교권보호단", "교육감 직속. 교권보호 119 접수, 상근·비상근 전담관 (조례)"),
        ("교권보호 119", "교권보호단", "교권보호 119", "사안 접수·분류"),
        ("전담관", "교권보호단", "상근·비상근 전담관", "주 담당 배정, 전문가 연계 (조사·심의 권한 없음)"),
    ]
    counts = schools.groupby(["office", "level"]).size() if not schools.empty else None
    for o in OFFICES:
        oid = f"o:{o.key}"
        rows.append((oid, "경기도교육청", o.key, f"{o.name}: 관할 학교 지도·감독"))
        rows.append((f"c:{o.key}", oid, "지역교권보호위원회", "침해 여부 심의·조치, 분쟁 조정 (원문 확인 필요)"))
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
