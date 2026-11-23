"""KOSIS(국가통계포털) 공유서비스 Open API: 시도별 교원 수.

키(KOSIS_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 키 값은 화면·로그에 찍지 않는다.
- 통계표 검색: statisticsSearch.do?method=getList&searchNm=…  (통계표 ID 찾기)
- 통계 자료:   statisticsData.do?method=getList&orgId=…&tblId=…&itmId=ALL&objL1=ALL&prdSe=Y
교육통계(한국교육개발원 KESS)는 KOSIS 기관코드 334로 올라와 있다. 통계표 ID는 키가 생긴 뒤
`python -m collector.kosis --search 시도별 교원` 으로 확인해 config/kosis.yaml 에 적는다.

    python -m collector.kosis --search 시도별 교원수   # 통계표 찾기
    python -m collector.kosis                          # data/measured/sido_teachers.csv 저장
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://kosis.kr/openapi"
CFG = ROOT / "config" / "kosis.yaml"
OUT = ROOT / "data" / "measured" / "sido_teachers.csv"
SIDO = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
        "충북", "충남", "전북", "전남", "경북", "경남", "제주")


class KosisError(RuntimeError):
    pass


def kosis_key() -> str | None:
    return (os.environ.get("KOSIS_KEY") or "").strip() or None


def _get(path: str, client: httpx.Client | None = None, **params) -> list[dict]:
    key = kosis_key()
    if not key:
        raise KosisError("KOSIS_KEY 없음")
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        r = client.get(f"{BASE}/{path}", params={"method": "getList", "apiKey": key, "format": "json",
                                                  "jsonVD": "Y", **params})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:  # URL(키 포함)이 메시지에 섞이지 않게
        raise KosisError(f"{path} 요청 실패 ({type(e).__name__})") from None
    finally:
        if own:
            client.close()
    if isinstance(data, dict):  # 오류는 {"err": "…", "errMsg": "…"}
        raise KosisError(f"{data.get('err')}: {data.get('errMsg')}")
    return data


def search(name: str, client=None) -> pd.DataFrame:
    rows = _get("statisticsSearch.do", client, searchNm=name)
    cols = [c for c in ("ORG_ID", "TBL_ID", "TBL_NM", "STAT_NM", "STRT_PRD_DE", "END_PRD_DE") if rows and c in rows[0]]
    return pd.DataFrame(rows)[cols] if rows else pd.DataFrame()


def sido_short(name: str) -> str | None:
    n = str(name).strip()
    for s in SIDO:
        if n.startswith(s) or n.startswith(s[0] + "라" + s[1:]) or n.startswith(s[0] + "청" + s[1:]) \
                or n.startswith(s[0] + "상" + s[1:]):
            return s
    return None


def teachers_table(rows: list[dict], item: str | None = None) -> pd.DataFrame:
    """statisticsData 응답 → 시도·연도·교원수 (시도 이름은 짧은 이름으로)."""
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["시도", "연도", "교원수"])
    if item and "ITM_NM" in df:
        df = df[df["ITM_NM"].astype(str).str.contains(item)]
    df = df.assign(시도=df["C1_NM"].map(sido_short), 연도=pd.to_numeric(df["PRD_DE"].astype(str).str[:4]),
                   교원수=pd.to_numeric(df["DT"], errors="coerce"))
    df = df.dropna(subset=["시도", "교원수"])
    return df.groupby(["시도", "연도"], as_index=False)["교원수"].sum()


def fetch_teachers(cfg: dict | None = None, client=None) -> pd.DataFrame:
    cfg = cfg or (yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {})
    t = (cfg or {}).get("teachers") or {}
    if not t.get("tblId"):
        raise KosisError("config/kosis.yaml 에 teachers.tblId 가 없음 (--search 로 찾기)")
    rows = _get("statisticsData.do", client, orgId=t.get("orgId", "334"), tblId=t["tblId"],
                itmId=t.get("itmId", "ALL"), objL1="ALL", objL2=t.get("objL2", ""), prdSe="Y",
                startPrdDe=str(t.get("start", 2019)), endPrdDe=str(t.get("end", 2025)))
    return teachers_table(rows, t.get("item"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KOSIS 시도별 교원 수")
    ap.add_argument("--search", help="통계표 이름 검색어")
    a = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    try:
        if a.search:
            print(search(a.search).to_string(index=False))
            return 0
        df = fetch_teachers()
    except KosisError as e:
        print(f"[KOSIS] {e}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"[KOSIS] 시도별 교원 수 {len(df)}행 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
