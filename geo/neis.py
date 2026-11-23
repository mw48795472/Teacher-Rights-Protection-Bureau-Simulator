"""NEIS 교육정보 개방포털 학교기본정보 API.

https://open.neis.go.kr/hub/schoolInfo 에서 시도교육청 단위로 학교 목록을 받는다.
키(NEIS_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 좌표는 없으므로 위치 표준데이터와 학교명·관할로 대조한다.
"""
from __future__ import annotations

import os

import httpx
import pandas as pd

from .gyeonggi import LEVELS, office_key

URL = "https://open.neis.go.kr/hub/schoolInfo"
GYEONGGI = "J10"   # 경기도교육청 시도교육청코드
PAGE = 1000        # API 최대 페이지 크기


class NeisError(RuntimeError):
    pass


def neis_key() -> str | None:
    return os.environ.get("NEIS_KEY") or None


def _rows(payload: dict) -> tuple[list[dict], int]:
    if "RESULT" in payload:  # 오류이거나 데이터 없음
        r = payload["RESULT"]
        if r.get("CODE") == "INFO-200":
            return [], 0
        raise NeisError(f"{r.get('CODE')}: {r.get('MESSAGE')}")
    body = payload["schoolInfo"]
    head = body[0]["head"]
    total = int(head[0]["list_total_count"])
    code = head[1]["RESULT"]["CODE"]
    if code != "INFO-000":
        raise NeisError(f"{code}: {head[1]['RESULT'].get('MESSAGE')}")
    return body[1]["row"], total


def fetch_schools(key: str, atpt: str = GYEONGGI, client: httpx.Client | None = None) -> pd.DataFrame:
    """초·중·고 학교 목록. 열: name, level, office, code, phone, homepage, addr, coedu, found."""
    own = client is None
    client = client or httpx.Client(timeout=20)
    rows, page = [], 1
    try:
        while True:
            try:
                resp = client.get(URL, params={"KEY": key, "Type": "json", "pIndex": page, "pSize": PAGE,
                                               "ATPT_OFCDC_SC_CODE": atpt})
                resp.raise_for_status()
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                # 오류 메시지에 키가 든 URL이 섞이지 않도록 종류만 남긴다
                raise NeisError(f"NEIS 요청 실패 ({type(e).__name__})") from None
            got, total = _rows(payload)
            rows += got
            if not got or len(rows) >= total:
                break
            page += 1
    finally:
        if own:
            client.close()
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["name", "level", "office", "code", "phone", "homepage", "addr", "coedu", "found"])
    out = pd.DataFrame({
        "name": df.get("SCHUL_NM"),
        "level": df.get("SCHUL_KND_SC_NM"),
        "office": df.get("JU_ORG_NM", pd.Series(dtype=str)).map(office_key),
        "code": df.get("SD_SCHUL_CODE"),
        "phone": df.get("ORG_TELNO"),
        "homepage": df.get("HMPG_ADRES"),
        "addr": df.get("ORG_RDNMA"),
        "coedu": df.get("COEDU_SC_NM"),
        "found": df.get("FOND_SC_NM"),
    })
    return out[out["level"].isin(LEVELS)].reset_index(drop=True)


def reconcile(schools: pd.DataFrame, neis: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """위치 표준데이터에 NEIS 정보(학교코드·전화·홈페이지 등)를 붙이고 양쪽 차이를 센다."""
    keys = ["name", "office"]
    extra = neis.drop(columns=["level", "addr"]).drop_duplicates(keys)
    merged = schools.merge(extra, on=keys, how="left")
    s_keys = set(map(tuple, schools[keys].values))
    n_keys = set(map(tuple, neis[keys].values))
    stats = {"일치": len(s_keys & n_keys), "NEIS에만": len(n_keys - s_keys), "위치데이터에만": len(s_keys - n_keys)}
    only_neis = neis[[k in (n_keys - s_keys) for k in map(tuple, neis[keys].values)]]
    return merged, {**stats, "only_neis": only_neis}
