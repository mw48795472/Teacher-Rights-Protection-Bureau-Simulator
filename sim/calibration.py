"""실측 데이터로 시뮬레이터 가정값을 맞춘다.

config/measured.yaml(원자료 표에서 옮긴 값)과 data/measured/(원자료 파일, 집계표)를 읽어
- 사안 유형 비율: 교권보호위원회 침해 유형(2023) + 교육감 의견 제출(교원 대상 아동학대 신고)
- 교육지원청별 사안 비중: 교원 수 비례 (2025.4.1. 경기도교육청 학교 통계)
를 만든다. 나머지 처리시간·인력 등은 아직 가정값이며 assumption_table() 이 실측/가정을 함께 보여 준다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
MEASURED = ROOT / "config" / "measured.yaml"
OFFICES_CSV = ROOT / "data" / "measured" / "gyeonggi_offices.csv"
RAW = ROOT / "data" / "measured" / "raw"


@lru_cache(maxsize=1)
def load() -> dict:
    if not MEASURED.exists():
        return {}
    return yaml.safe_load(MEASURED.read_text(encoding="utf-8")) or {}


def enabled(key: str) -> bool:
    return bool((load().get("use") or {}).get(key, False))


def source(key: str) -> dict:
    return (load().get("sources") or {}).get(key, {})


def assumed_case_mix() -> dict[str, float]:
    from .cases import CASE_TYPES
    return {k: v["weight"] for k, v in CASE_TYPES.items()}


def opinions_per_year() -> float:
    so = load()["superintendent_opinions"]
    return sum(so["opinions"].values()) / so["months"] * 12


def measured_case_mix() -> dict[str, float]:
    """교보위 유형(연간)과 교육감 의견 제출(연 환산)을 시뮬레이터 사안 유형으로 묶은 비율.

    실측이 없는 유형(민·형사 소송)은 팀 가정 비율을 그대로 두고 나머지를 그 안에서 나눈다.
    """
    m = load()
    counts = m["committee_types_2023"]["counts"]
    mapping = m["case_mix_mapping"]
    assumed = assumed_case_mix()
    raw: dict[str, float] = {}
    fixed: dict[str, float] = {}
    for t, rule in mapping.items():
        if rule == "assumed":
            fixed[t] = assumed[t]
        elif rule == "superintendent_opinions":
            raw[t] = opinions_per_year()
        else:
            raw[t] = float(sum(counts[c] for c in rule))
    rest = 1 - sum(fixed.values())
    total = sum(raw.values())
    out = {t: rest * v / total for t, v in raw.items()} | fixed
    return {t: out.get(t, 0.0) for t in assumed}   # CASE_TYPES 순서 유지


@lru_cache(maxsize=1)
def case_weights() -> dict[str, float]:
    """시뮬레이터가 실제로 쓰는 사안 유형 비율."""
    if enabled("case_mix") and load().get("committee_types_2023"):
        return measured_case_mix()
    return assumed_case_mix()


def office_table() -> pd.DataFrame:
    if not OFFICES_CSV.exists():
        return pd.DataFrame(columns=["office", "schools", "teachers", "students"])
    return pd.read_csv(OFFICES_CSV)


def office_teacher_weights() -> dict[str, float] | None:
    """교육지원청별 사안 비중(교원 수 비례). 끄거나 집계표가 없으면 None."""
    if not enabled("office_weights"):
        return None
    t = office_table()
    if t.empty:
        return None
    return {r.office: float(r.teachers) for r in t.itertuples() if r.teachers > 0}


# ── 대시보드용 표 ────────────────────────────────────────

def _pct(d: dict, key: str) -> float:
    return d[key] / sum(d.values()) * 100


def committee_trend() -> pd.DataFrame:
    by = load()["committee_cases"]["by_year"]
    return pd.DataFrame({"학년도": list(by), "교권보호위원회 심의 건수": list(by.values())})


def center_usage() -> pd.DataFrame:
    rows = [{"연도": y, "유형": k, "건수": v} for y, d in load()["center_usage"]["by_year"].items()
            for k, v in d.items()]
    return pd.DataFrame(rows)


def child_abuse_gyeonggi() -> pd.DataFrame:
    """보건복지부 시도별 아동학대 판단 사례 중 경기 (전체 아동 대상, 교원 대상 아님)."""
    from collector.measured import read_kr_csv
    p = ROOT / source("abuse").get("file", "")
    if not p.is_file():
        return pd.DataFrame()
    df = read_kr_csv(p)
    df = df[df["시도"].astype(str).str.startswith("경기")].copy()
    df.columns = [c.replace("아동학대유형_", "") for c in df.columns]
    return df.drop(columns=["시도"]).reset_index(drop=True)


def police_child_abuse() -> pd.DataFrame:
    from collector.measured import read_kr_csv
    p = ROOT / source("police").get("file", "")
    return read_kr_csv(p) if p.is_file() else pd.DataFrame()


def case_mix_table() -> pd.DataFrame:
    a, m = assumed_case_mix(), measured_case_mix()
    mp = load()["case_mix_mapping"]
    basis = {t: ("교육감 의견 제출 385건(7.2개월) → 연 환산" if r == "superintendent_opinions"
                 else "실측 없음, 팀 가정 유지" if r == "assumed" else "교보위 유형: " + ", ".join(r))
             for t, r in mp.items()}
    return pd.DataFrame([{"사안 유형": t, "팀 가정(%)": round(a[t] * 100, 1),
                          "실측 기반(%)": round(m[t] * 100, 1), "근거": basis.get(t, "")} for t in a])


def assumption_table() -> pd.DataFrame:
    """시뮬레이터 값별로 가정/실측과 출처, 반영 여부."""
    m = load()
    oc = m["committee_outcomes"]
    so = m["superintendent_opinions"]
    hot = m["hotline_1395"]["by_type"]
    cu = m["center_usage"]["by_year"][2023]
    mix_on, office_on = enabled("case_mix"), enabled("office_weights") and not office_table().empty
    t = office_table()
    rows = [
        ("사안 유형 비율", "악성민원 35%, 아동학대 신고 25%, 폭언·폭행 20%, 소송 10%, 단순 상담 10%",
         ", ".join(f"{k} {v * 100:.0f}%" for k, v in measured_case_mix().items()),
         "kbw, followup", "반영" if mix_on else "끔"),
        ("교육지원청별 사안 비중", "학교 수 비례",
         f"교원 수 비례 (25개 지원청, 교원 {int(t.teachers.sum()):,}명)" if not t.empty else "집계표 없음",
         "schools", "반영" if office_on else "끔"),
        ("하루 평균 사안 수", "3건 (보도: 8.24~10.8 140건 이상)",
         f"전국 교보위 2023학년도 {m['committee_cases']['by_year'][2023]:,}건 (월 약 420건), "
         "경기 교권보호단 월별 접수는 미공개", "kbw", "참고 (경기 실측 대기)"),
        ("위원회 침해 인정 비율", "모형에 없음 (심의 후 바로 조치)",
         f"학교 교보위 2023 {_pct(oc['school_2023'], '침해 인정'):.1f}%, "
         f"지역 교보위 이관 후 1개월 {_pct(oc['office_first_month_2024'], '침해 인정'):.1f}%",
         "followup", "참고"),
        ("아동학대 신고 사안의 결론", "모형에 없음 (수사 대기 3근무일만 반영)",
         f"교육감 '정당한 생활지도' 의견 {_pct(so['opinions'], '정당한 생활지도'):.0f}%, "
         f"종결 148건 중 기소 {_pct(so['closed_outcomes'], '기소'):.1f}%", "followup", "참고"),
        ("서비스 수요 구성", "비상근 전담관 분야: 법률 25%, 상담 30%, 수사 15%, 갈등 15%, 행정 15%",
         f"센터 이용 2023: 상담 {cu['상담']:,}, 심리치료 {cu['심리치료']:,}, 법률 {cu['법률지원']:,}건",
         "center", "참고 (전담관 분야 인원은 청구 필요)"),
        ("1395 문의 중 침해 신고", "모형에 없음",
         f"{_pct(hot, '교육활동 침해 신고 상담'):.1f}% (2024.3~4월 {sum(hot.values())}건 중 {hot['교육활동 침해 신고 상담']}건)",
         "followup", "참고"),
        ("서비스별 처리 시간", "상담 4h, 법률 10h, 행정 3h, 수사연계 2h, 갈등조정 6h", "공개 자료 없음", "",
         "가정 유지 (정보공개청구 필요)"),
        ("전담관 인원·가용률", "상근 20, 비상근 280, 가용률 25%", "공개 자료 없음", "",
         "가정 유지 (정보공개청구 필요)"),
        ("위원회 개최 간격", "30일", "공개 자료 없음 (지원청별 개최 일자)", "", "가정 유지 (정보공개청구 필요)"),
    ]
    out = pd.DataFrame(rows, columns=["항목", "팀 가정값", "실측값", "출처", "시뮬레이터"])
    out["출처"] = out["출처"].map(lambda s: ", ".join(source(k).get("title", k) for k in s.split(", ") if k) if s else "")
    return out


DATA_SOURCES = ROOT / "config" / "data_sources.yaml"


def data_sources_table() -> pd.DataFrame:
    """config/data_sources.yaml 의 출처 목록 (README 표)."""
    if not DATA_SOURCES.exists():
        return pd.DataFrame()
    rows = (yaml.safe_load(DATA_SOURCES.read_text(encoding="utf-8")) or {}).get("sources") or []
    cols = {"group": "구분", "provider": "제공기관", "name": "데이터", "date": "기준일", "format": "형식",
            "key": "키", "used_in": "쓰이는 곳", "url": "링크"}
    return pd.DataFrame(rows)[list(cols)].rename(columns=cols)


def committee_by_sido() -> pd.DataFrame:
    """시도별 교보위 심의 건수 (2024.3.28.~6.30. 17개 시도, 2024년 전체 일부 시도). 보도 값."""
    c = load().get("committee_by_sido") or {}
    q, y = c.get("q2024_regional") or {}, c.get("y2024") or {}
    rows = [{"시도": k, "2024.3.28~6.30": v, "2024년": (y.get("counts") or {}).get(k)}
            for k, v in (q.get("counts") or {}).items()]
    return pd.DataFrame(rows).sort_values("2024.3.28~6.30", ascending=False, ignore_index=True)


def gyeonggi_committee_per_day() -> float | None:
    """경기 교보위 심의 건수의 하루 평균 (2024년 전체 기준). 시뮬레이터 유입량(하루 약 3건)과 비교용."""
    y = ((load().get("committee_by_sido") or {}).get("y2024") or {}).get("counts") or {}
    return y["경기"] / 365 if "경기" in y else None
