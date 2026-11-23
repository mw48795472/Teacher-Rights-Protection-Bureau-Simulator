"""실측 원자료 → 시뮬레이터용 집계표.

    python -m collector.measured data/raw/경기도교육청_행정구역별_학제별_학급_학생_교원_20250401.xlsx

경기도교육청 학교 통계(xlsx, 8MB)를 교육지원청별 학교·교원·학생 수로 줄여
data/measured/gyeonggi_offices.csv 에 저장한다(커밋용). 원자료는 data/raw/ 에 둔다.
CSV 원자료(보건복지부·경찰청)는 CP949 인코딩이라 read_kr_csv 로 읽는다.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OFFICES_CSV = ROOT / "data" / "measured" / "gyeonggi_offices.csv"
LEVELS = ("유치원", "초등학교", "중학교", "고등학교", "특수학교")

# 도교육청 직속(고등학교 등, 교육청명 '경기')은 소재 시·군으로 관할 교육지원청을 정한다.
CITY_TO_OFFICE = {
    "수원시": "수원", "성남시": "성남", "의정부시": "의정부", "부천시": "부천", "광명시": "광명",
    "안양시": "안양과천", "과천시": "안양과천", "동두천시": "동두천양주", "양주시": "동두천양주",
    "고양시": "고양", "구리시": "구리남양주", "남양주시": "구리남양주", "안산시": "안산",
    "평택시": "평택", "화성시": "화성오산", "오산시": "화성오산", "시흥시": "시흥",
    "군포시": "군포의왕", "의왕시": "군포의왕", "용인시": "용인", "이천시": "이천",
    "광주시": "광주하남", "하남시": "광주하남", "여주시": "여주", "양평군": "양평", "김포시": "김포",
    "파주시": "파주", "안성시": "안성", "연천군": "연천", "가평군": "가평", "포천시": "포천",
}


def read_kr_csv(src) -> pd.DataFrame:
    """공공데이터포털 CSV(대개 CP949)를 읽는다. UTF-8(BOM 포함)도 받아 준다."""
    data = Path(src).read_bytes() if not hasattr(src, "read") else src.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 인코딩을 알 수 없습니다 (UTF-8, CP949 아님).")
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            s = df[c].astype(str).str.strip()
            num = pd.to_numeric(s.str.replace(",", ""), errors="coerce")
            df[c] = num if num.notna().all() else s
    return df


def _office(row) -> str | None:
    name = str(row["교육청명"]).replace("·", "").strip()
    if name == "경기":
        return CITY_TO_OFFICE.get(str(row["행정구"]).strip())
    return name


def build_office_table(xlsx: Path | str) -> pd.DataFrame:
    """교육지원청별 학교 수·교원 수·학생 수 (유치원·초·중·고·특수)."""
    cols = {0: "시도", 2: "교육청명", 3: "행정구", 4: "학교급", 6: "학교명"}
    t = pd.read_excel(xlsx, sheet_name="교원수", header=None, skiprows=4).dropna(subset=[0])
    t = t.rename(columns={**cols, 8: "교원수"})
    s = pd.read_excel(xlsx, sheet_name="학급 구분별 학급 및 학생수", header=None, skiprows=4).dropna(subset=[0])
    s = s.rename(columns={**cols, 9: "학생수"})
    df = t[["교육청명", "행정구", "학교급", "학교명", "교원수"]].merge(
        s[["교육청명", "행정구", "학교급", "학교명", "학생수"]], how="left",
        on=["교육청명", "행정구", "학교급", "학교명"])
    df = df[df["학교급"].isin(LEVELS)].copy()
    df["office"] = df.apply(_office, axis=1)
    missing = df[df["office"].isna()]
    if len(missing):
        raise ValueError(f"교육지원청을 정하지 못한 학교 {len(missing)}곳: {missing['행정구'].unique()[:5]}")
    out = df.groupby("office").agg(schools=("학교명", "size"), teachers=("교원수", "sum"),
                                   students=("학생수", "sum")).reset_index()
    out[["teachers", "students"]] = out[["teachers", "students"]].fillna(0).astype(int)
    return out.sort_values("teachers", ascending=False).reset_index(drop=True)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    out = build_office_table(argv[0])
    OFFICES_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OFFICES_CSV, index=False, encoding="utf-8")
    print(f"교육지원청 {len(out)}곳, 학교 {out.schools.sum():,}곳, 교원 {out.teachers.sum():,}명 → {OFFICES_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
