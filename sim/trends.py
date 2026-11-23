"""실측 추세 분석: 저장소에 있는 원자료만으로 계산한다 (가정값·합성값 없음). sim/empirical.py(실측 기반 사안 생성)와 별개.

1) 교보위 심의 건수·유형 추세 (2019~2024)와 교권5법(2023.9.) 전후 비교
2) 교원 1천 명당 건수 (시도별 교원 수 파일이 있을 때)
3) 2024년 시도 비교 (보도 값)
4) 아동학대 신고 → 검거 → 기소·불기소·보호사건 흐름, 교원 대상 신고와 비교
5) 경기 교권보호단 출범 효과 (정보공개청구 자료가 있을 때)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import calibration as cal

ROOT = Path(__file__).resolve().parent.parent
SIDO_TEACHERS = ROOT / "data" / "measured" / "sido_teachers.csv"        # 열: 시도, 연도, 교원수 (KESS)
GG_CASES = ROOT / "data" / "measured" / "claims" / "gyeonggi_cases.csv"  # 정보공개청구 답변 (사안 1건 1행)

SIDO_SHORT = {"서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주", "대전": "대전",
              "울산": "울산", "세종": "세종", "경기": "경기", "강원": "강원", "충북": "충북", "충남": "충남",
              "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남", "제주": "제주"}


# ── 1. 추세 ──
def committee_totals() -> pd.DataFrame:
    """연도별 교보위 심의 건수. 2019~2023 교육부 원자료(A), 2024~2025는 KEDI 교육정책포럼 수치 보도."""
    m = cal.load()
    rows = [{"학년도": int(y), "건수": int(v), "출처": "교육부 원자료"}
            for y, v in m["committee_cases"]["by_year"].items()]
    recent = (m.get("committee_cases_recent") or {}).get("by_year") or {}
    for y, v in recent.items():
        rows.append({"학년도": int(y), "건수": int(v), "출처": "KEDI 교육정책포럼 (보도)"})
    return pd.DataFrame(rows).sort_values("학년도", ignore_index=True)


def types_by_year() -> pd.DataFrame:
    """연도별 침해 유형 건수·비율 (2020~2023)."""
    m = cal.load()
    by = {int(y): d for y, d in (m.get("committee_types_by_year") or {}).items() if y != "source"}
    by[2023] = m["committee_types_2023"]["counts"]
    rows = []
    for y, d in sorted(by.items()):
        tot = sum(d.values())
        rows += [{"학년도": y, "유형": k, "건수": v, "비율(%)": round(v / tot * 100, 1)} for k, v in d.items()]
    return pd.DataFrame(rows)


def law5_compare() -> pd.DataFrame:
    """2022학년도 대 2023학년도(2023.3.~2024.2., 교권5법 2023.9. 시행이 걸친 해) 유형별 변화.
    연 단위 자료라 9월 전후를 나눌 수 없다는 한계가 있다."""
    t = types_by_year()
    a = t[t["학년도"] == 2022].set_index("유형")
    b = t[t["학년도"] == 2023].set_index("유형")
    out = pd.DataFrame({"2022 건수": a["건수"], "2023 건수": b["건수"],
                        "2022 비율(%)": a["비율(%)"], "2023 비율(%)": b["비율(%)"]}).fillna(0)
    out["증감(건)"] = out["2023 건수"] - out["2022 건수"]
    out["비율 변화(%p)"] = (out["2023 비율(%)"] - out["2022 비율(%)"]).round(1)
    return out.astype({"2022 건수": int, "2023 건수": int, "증감(건)": int}) \
        .sort_values("증감(건)", ascending=False).rename_axis("유형").reset_index()


# ── 2·3. 시도 비교와 교원 1천 명당 ──
def sido_teachers() -> pd.DataFrame:
    """KESS 시도별 교원 수 (data/measured/sido_teachers.csv: 시도, 연도, 교원수).
    파일이 없고 KOSIS_KEY·config/kosis.yaml 통계표 ID가 있으면 KOSIS에서 받아 저장한다. 둘 다 없으면 빈 표."""
    if not SIDO_TEACHERS.exists():
        from collector import kosis
        try:
            df = kosis.fetch_teachers() if kosis.kosis_key() else None
        except Exception:  # 화면을 막지 않는다
            df = None
        if df is None or df.empty:
            return pd.DataFrame(columns=["시도", "연도", "교원수"])
        SIDO_TEACHERS.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(SIDO_TEACHERS, index=False, encoding="utf-8-sig")
    from collector.measured import read_kr_csv
    df = read_kr_csv(SIDO_TEACHERS)
    df["시도"] = df["시도"].astype(str).str[:2].map(SIDO_SHORT)
    return df.dropna(subset=["시도"])


def sido_2024() -> pd.DataFrame:
    """2024년 시도별 심의 건수 (보도 값). 교원 수가 있으면 교원 1천 명당 건수도."""
    t = cal.committee_by_sido()
    tc = sido_teachers()
    if not tc.empty:
        yr = 2024 if 2024 in set(tc["연도"]) else tc["연도"].max()
        t = t.merge(tc[tc["연도"] == yr][["시도", "교원수"]], on="시도", how="left")
        t["1천 명당 (3개월)"] = (t["2024.3.28~6.30"] / t["교원수"] * 1000).round(2)
        t["1천 명당 (2024년)"] = (t["2024년"] / t["교원수"] * 1000).round(2)
    return t


def incheon_actor() -> pd.DataFrame:
    y = (cal.load().get("committee_by_sido") or {}).get("y2024") or {}
    inc, nat = y.get("incheon_by_actor") or {}, y.get("national_actor_share") or {}
    tot = sum(inc.values()) or 1
    return pd.DataFrame([{"침해 주체": k, "인천 건수": v, "인천 비율(%)": round(v / tot * 100, 1),
                          "전국 비율(%)": round(nat.get(k, 0) * 100, 1)} for k, v in inc.items()])


# ── 4. 아동학대 신고 흐름 ──
def abuse_flow() -> pd.DataFrame:
    """경찰청 아동학대 검거 및 조치 (전국, 2016~2023). 처분 = 기소(구속+불구속) + 불기소 + 보호사건."""
    po = cal.police_child_abuse()
    if po.empty:
        return po
    df = pd.DataFrame({"연도": po["연도"].astype(int), "검거 건수": po["검거건수_건"],
                       "기소": po["검거인원_기소_구속_명"] + po["검거인원_기소_불구속_명"],
                       "불기소": po["검거인원_불기소_명"], "보호사건": po["보호사건"]})
    tot = df[["기소", "불기소", "보호사건"]].sum(axis=1)
    for c in ("기소", "불기소", "보호사건"):
        df[f"{c}(%)"] = (df[c] / tot * 100).round(1)
    return df


def abuse_reports_national() -> pd.DataFrame:
    """보건복지부 아동학대 판단 사례, 연도별 전국·경기 합계 (2015~2024)."""
    from collector.measured import read_kr_csv
    p = ROOT / cal.source("abuse").get("file", "")
    if not p.is_file():
        return pd.DataFrame()
    df = read_kr_csv(p)
    val = [c for c in df.columns if c.startswith("아동학대유형_")]
    df["합계"] = df[val].sum(axis=1)
    nat = df.groupby("연도")["합계"].sum().rename("전국")
    gg = df[df["시도"].astype(str).str.startswith("경기")].groupby("연도")["합계"].sum().rename("경기")
    out = pd.concat([nat, gg], axis=1).reset_index()
    out["경기 비중(%)"] = (out["경기"] / out["전국"] * 100).round(1)
    return out


def abuse_compare() -> pd.DataFrame:
    """처분 구성 비교: 전체 아동학대 사건(경찰청 2023, 인원·사건) 대 교원 대상 신고(교육부, 종결 148건).
    단위·기간이 달라 엄밀한 비교가 아니라 방향을 보는 참고값이다."""
    rows = []
    fl = abuse_flow()
    if not fl.empty:
        last = fl.iloc[-1]
        rows.append({"구분": f"전체 아동학대 ({int(last['연도'])}, 경찰청)", "기소(%)": last["기소(%)"],
                     "불기소·종결(%)": last["불기소(%)"], "보호사건(%)": last["보호사건(%)"], "기타(%)": 0.0})
    co = cal.load()["superintendent_opinions"]["closed_outcomes"]
    tot = sum(co.values())
    pct = lambda v: round(v / tot * 100, 1)  # noqa: E731
    rows.append({"구분": "교원 대상 신고 (2023.9~2024.4 종결 148건, 교육부)", "기소(%)": pct(co["기소"]),
                 "불기소·종결(%)": pct(co["불기소"] + co["수사개시 전 종결"]),
                 "보호사건(%)": pct(co["아동보호사건"]), "기타(%)": pct(co["기타"])})
    return pd.DataFrame(rows)


# ── 5. 출범 효과 ──
def launch_cases() -> pd.DataFrame:
    """정보공개청구로 받은 경기 사안 목록 (접수일, 종결일, 주체 ...). 없으면 빈 표."""
    if not GG_CASES.exists():
        return pd.DataFrame()
    from collector.measured import read_kr_csv
    return read_kr_csv(GG_CASES)


def launch_effect(launch: str = "2026-08-24") -> pd.DataFrame:
    """출범 전후 처리 기간(접수일→종결일) 비교. 열: 접수일, 종결일 (YYYY-MM-DD)."""
    df = launch_cases()
    if df.empty or not {"접수일", "종결일"} <= set(df.columns):
        return pd.DataFrame()
    d = df.assign(접수일=pd.to_datetime(df["접수일"], errors="coerce"),
                  종결일=pd.to_datetime(df["종결일"], errors="coerce")).dropna(subset=["접수일"])
    d["처리일수"] = (d["종결일"] - d["접수일"]).dt.days
    d["시기"] = d["접수일"].map(lambda x: "출범 후" if x >= pd.Timestamp(launch) else "출범 전")
    return d.groupby("시기")["처리일수"].describe()[["count", "mean", "50%", "max"]] \
        .rename(columns={"count": "사안 수", "mean": "평균(일)", "50%": "중앙값(일)", "max": "최대(일)"}).reset_index()


def edufin_budget(fetch: bool = True) -> tuple[pd.DataFrame, str]:
    """지방교육재정알리미 공시에서 교권보호 관련 사업 행. (표, 상태 문구).
    저장 파일(data/measured/edufin/*.csv)이 있으면 그것을, 없고 EDUFIN_KEY가 있으면 받아서 쓴다."""
    from collector import edufin
    cfg = edufin.config()
    names = [s.get("name") or s["requestType"] for s in cfg.get("services") or []]
    frames = {n: edufin.saved(n) for n in names}
    if all(f.empty for f in frames.values()):
        if not edufin.edufin_key():
            return pd.DataFrame(), "no_key"
        if not fetch:
            return pd.DataFrame(), "not_fetched"
        try:
            frames = edufin.collect(cfg, log=lambda *_: None)
        except Exception as e:  # 화면을 막지 않는다
            return pd.DataFrame(), f"error: {type(e).__name__}"
        if all(f.empty for f in frames.values()):
            return pd.DataFrame(), "empty"
    allrows = pd.concat([f for f in frames.values() if not f.empty], ignore_index=True)
    hit = edufin.keyword_rows(allrows, cfg.get("keywords") or ["교권"])
    return (hit, "ok") if not hit.empty else (allrows, "no_keyword")


# ── 6. 시도교육청 재정 (지방교육재정알리미 공시) ──
def edufin_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """받은 공시 표에서 시도·연도·숫자 칸을 찾아 정리한다. 칸 이름이 공개되지 않아 값으로 알아본다.
    반환: (정리된 표: 시도, 연도, 구분 칸들, 숫자 칸들), {"sido": 원래 칸, "year": 칸, "nums": [...], "cats": [...]}"""
    from collector.kosis import sido_short
    if df is None or df.empty:
        return pd.DataFrame(), {}
    d = df.copy()
    texts = [c for c in d.columns if d[c].dtype == object or str(d[c].dtype).startswith("str")]
    sido_col = max(texts, key=lambda c: d[c].astype(str).map(sido_short).notna().mean(), default=None)
    if sido_col is None or d[sido_col].astype(str).map(sido_short).notna().mean() < 0.5:
        return pd.DataFrame(), {}
    d["시도"] = d[sido_col].astype(str).map(sido_short)
    year_col = next((c for c in d.columns if str(c) in ("회계연도", "연도", "YMQ", "ymq", "YEAR", "year")), None)
    if year_col is None:
        year_col = next((c for c in d.columns if any(k in str(c).upper() for k in ("YEAR", "YMQ", "YR", "연도"))), None)
    d["연도"] = pd.to_numeric(d[year_col].astype(str).str[:4], errors="coerce") if year_col is not None else pd.NA
    nums = []
    for c in d.columns:
        if c in ("시도", "연도", year_col):
            continue
        v = pd.to_numeric(d[c].astype(str).str.replace(",", "").str.strip(), errors="coerce")
        if v.notna().mean() >= 0.8 and v.nunique() > 5:
            d[c] = v
            nums.append(c)
    cats = [c for c in texts if c != sido_col and c not in nums and 1 < d[c].nunique() <= 300]
    d = d.dropna(subset=["시도"])
    return d, {"sido": sido_col, "year": year_col, "nums": nums, "cats": cats}


def edufin_by_sido(d: pd.DataFrame, value: str, filters: dict | None = None) -> pd.DataFrame:
    """시도×연도 합계 (filters: {구분 칸: 값})."""
    x = d
    for c, v in (filters or {}).items():
        x = x[x[c].astype(str) == str(v)]
    return x.groupby(["시도", "연도"], dropna=False, as_index=False)[value].sum()


def committee_vs_fiscal(fiscal: pd.DataFrame, value: str) -> pd.DataFrame:
    """2024 시도별 위원회 심의 건수(2024.3.28~6.30, 17개 시도)와 가장 최근 연도 재정 값을 잇는다."""
    s = sido_2024()[["시도", "2024.3.28~6.30"]].rename(columns={"2024.3.28~6.30": "심의 건수 (2024.3.28~6.30)"})
    f = fiscal.dropna(subset=["연도"]) if "연도" in fiscal else fiscal
    if f.empty:
        return pd.DataFrame()
    y = 2024 if (f["연도"] == 2024).any() else f["연도"].max()
    f = f[f["연도"] == y][["시도", value]]
    out = s.merge(f, on="시도", how="inner")
    out["재정 기준 연도"] = y
    out["심의 건수 / 재정 1조"] = out["심의 건수 (2024.3.28~6.30)"] / (out[value] / 1e12)
    return out
