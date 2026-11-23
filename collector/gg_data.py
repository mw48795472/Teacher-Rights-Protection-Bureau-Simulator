"""경기데이터드림(data.gg.go.kr) Open API 수집기.

키(GG_DATA_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 키 값은 화면·로그에 찍지 않는다.
요청 형식: https://openapi.gg.go.kr/{서비스}?KEY=…&Type=json&pIndex=1&pSize=1000
키 없이 부르면 샘플 5건만 오므로, 5건보다 많이 오면 키가 통한 것이다.

받는 데이터
- 지구대·파출소 현황 (Ptrldvsnsubpolcstus): 교원 대상 아동학대 신고가 접수되는 경찰 관서. 교육지원청별 관서 수
- 초중고등학교 현황 (GgSchoolM): 학교 위치. data/schools 표준데이터와 교육지원청별 학교 수를 대조

    python -m collector.gg_data --check   # 키가 통하는지만 확인
    python -m collector.gg_data           # data/measured/gg/*.csv 로 저장
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
import pandas as pd

from .measured import CITY_TO_OFFICE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "measured" / "gg"
BASE = "https://openapi.gg.go.kr"
SAMPLE_ROWS = 5

SERVICES = {
    "police": {"service": "Ptrldvsnsubpolcstus", "title": "경기도 지구대(파출소) 현황",
               "page": "https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=DQ2I0RA86JC3Z2M9Q8RZ17985111&infSeq=3"},
    "schools": {"service": "GgSchoolM", "title": "경기도 초중고등학교 현황",
                "page": "https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=1CO945ICIYJN0ZYSPR0F21083003&infSeq=3"},
}


class GgDataError(RuntimeError):
    pass


def gg_key() -> str | None:
    return (os.environ.get("GG_DATA_KEY") or "").strip() or None


def parse_openapi(payload: dict, service: str) -> tuple[list[dict], int]:
    """(행, 전체 건수). 경기데이터드림·열린국회정보 공통 형식. 오류 응답이면 GgDataError, 자료 없음(INFO-200)은 빈 목록."""
    if "RESULT" in payload:  # 키 오류 등은 서비스명 없이 RESULT만 온다
        res = payload["RESULT"]
        if res.get("CODE") == "INFO-200":
            return [], 0
        raise GgDataError(f"{res.get('CODE')}: {res.get('MESSAGE')}")
    body = payload.get(service)
    if not body:
        raise GgDataError(f"예상하지 못한 응답 형식 (서비스 {service})")
    head = body[0].get("head", [])
    total, code, msg = 0, None, ""
    for h in head:
        total = h.get("list_total_count", total)
        if "RESULT" in h:
            code, msg = h["RESULT"].get("CODE"), h["RESULT"].get("MESSAGE", "")
    if code not in (None, "INFO-000"):
        raise GgDataError(f"{code}: {msg}")
    rows = body[1].get("row", []) if len(body) > 1 else []
    return rows, int(total)


def fetch_rows(service: str, key: str | None, page_size: int = 1000, max_pages: int = 50,
               client: httpx.Client | None = None, base: str = BASE, **params) -> list[dict]:
    """서비스의 모든 행. key 가 None 이면 샘플 5건. base 를 바꾸면 열린국회정보에도 쓴다."""
    own = client is None
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": "Mozilla/5.0 (research-collector)"})
    try:
        out: list[dict] = []
        for page in range(1, max_pages + 1):
            q = {"Type": "json", "pIndex": page, "pSize": page_size, **params}
            if key:
                q["KEY"] = key
            try:
                r = client.get(f"{base}/{service}", params=q)
                r.raise_for_status()
                payload = r.json()
            except (httpx.HTTPError, ValueError) as e:  # 예외 메시지에 URL(키 포함)이 섞이지 않게
                code = f" HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else ""
                raise GgDataError(f"{service} 요청 실패 ({type(e).__name__}{code})") from None
            rows, total = parse_openapi(payload, service)
            out.extend(rows)
            if not key or not rows or len(out) >= total:
                break
        return out
    finally:
        if own:
            client.close()


def check_key(key: str | None = None, client: httpx.Client | None = None) -> dict:
    """키가 통하는지. {ok, reason, total, rows}. 샘플 한도(5건)를 넘겨 받으면 통한 것."""
    key = key or gg_key()
    if not key:
        return {"ok": False, "reason": "GG_DATA_KEY 없음"}
    svc = SERVICES["police"]["service"]
    try:
        rows = fetch_rows(svc, key, page_size=20, max_pages=1, client=client)
    except Exception as e:  # noqa: BLE001  모듈을 다시 읽은 뒤 GgDataError 클래스가 달라져도 화면이 죽지 않게
        return {"ok": False, "reason": f"연결 실패: {e}" if isinstance(e, RuntimeError) else f"연결 실패 ({type(e).__name__})"}
    if len(rows) <= SAMPLE_ROWS:
        return {"ok": False, "reason": f"샘플 {len(rows)}건만 받음 (키가 아직 승인되지 않았을 수 있음)", "rows": len(rows)}
    return {"ok": True, "reason": "정상", "rows": len(rows)}


def office_of(city: str | None, addr: str | None = None) -> str | None:
    """시·군 이름(또는 주소의 두 번째 낱말)으로 교육지원청."""
    if city and str(city).strip() in CITY_TO_OFFICE:
        return CITY_TO_OFFICE[str(city).strip()]
    parts = str(addr or "").split()
    if len(parts) > 1 and parts[0].startswith("경기"):
        return CITY_TO_OFFICE.get(parts[1])
    return None


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def police_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["office", "city", "station", "name", "kind", "addr", "lat", "lon", "date"])
    return pd.DataFrame({
        "office": [office_of(c, a) for c, a in zip(df.get("SIGUN_NM"), df.get("REFINE_ROADNM_ADDR"))],
        "city": df.get("SIGUN_NM"),
        "station": df.get("POLCSTTN_NM"),
        "name": df.get("GOVOFC_NM"),
        "kind": df.get("DIV_NM"),
        "addr": df.get("REFINE_ROADNM_ADDR").fillna("").where(lambda s: s != "", df.get("REFINE_LOTNO_ADDR")),
        "lat": _num(df.get("REFINE_WGS84_LAT")),
        "lon": _num(df.get("REFINE_WGS84_LOGT")),
        "date": df.get("DATA_STD_DE"),
    })


def schools_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["office", "name", "level", "public", "addr", "lat", "lon"])
    addr = df.get("REFINE_ROADNM_ADDR").fillna("")
    return pd.DataFrame({
        "office": [office_of(None, a or b) for a, b in zip(addr, df.get("REFINE_LOTNO_ADDR"))],
        "name": df.get("FACLT_NM"),
        "level": df.get("SCHOOL_DIV_NM"),
        "public": df.get("PLVTINST_DIV_NM"),
        "addr": addr,
        "lat": _num(df.get("REFINE_WGS84_LAT")),
        "lon": _num(df.get("REFINE_WGS84_LOGT")),
    })


TABLES = {"police": police_table, "schools": schools_table}


def fetch_table(name: str, key: str | None = None, client: httpx.Client | None = None) -> pd.DataFrame:
    key = key or gg_key()
    if not key:
        raise GgDataError("GG_DATA_KEY 없음")
    return TABLES[name](fetch_rows(SERVICES[name]["service"], key, client=client))


def by_office(df: pd.DataFrame, col: str = "count") -> pd.DataFrame:
    return (df.dropna(subset=["office"]).groupby("office").size().rename(col).reset_index()
            .sort_values(col, ascending=False, ignore_index=True))


def load_saved(name: str) -> pd.DataFrame:
    p = OUT / f"{name}.csv"
    return pd.read_csv(p, dtype={"date": str}) if p.exists() else pd.DataFrame()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="경기데이터드림 Open API 수집")
    ap.add_argument("--check", action="store_true", help="키가 통하는지만 확인")
    ap.add_argument("--only", nargs="*", choices=list(SERVICES), help="받을 데이터")
    a = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    st = check_key()
    print(f"[경기데이터드림] 키 확인: {'정상' if st['ok'] else '실패'} ({st['reason']})")
    if a.check or not st["ok"]:
        return 0 if st["ok"] else 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name in a.only or list(SERVICES):
        try:
            df = fetch_table(name)
        except GgDataError as e:
            print(f"[경기데이터드림] {SERVICES[name]['title']} 실패: {e}")
            continue
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
        miss = int(df["office"].isna().sum())
        print(f"[경기데이터드림] {SERVICES[name]['title']}: {len(df)}건 → {OUT / (name + '.csv')}"
              + (f" (교육지원청 못 찾은 {miss}건)" if miss else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
