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
import re
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


SIDO_FULL = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
             "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
             "경기도": "경기", "강원도": "강원", "강원특별자치도": "강원", "충청북도": "충북", "충청남도": "충남",
             "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
             "제주특별자치도": "제주", "제주도": "제주"}
TOTAL = ("계", "합계", "전체", "소계", "총계")


def sido_short(name: str) -> str | None:
    """이름 앞부분으로 시도를 찾는다 ('서울특별시교육청' → '서울'). 시군구가 섞인 표에는 sido_exact 를 쓴다."""
    n = str(name).strip()
    for s in SIDO:
        if n.startswith(s) or n.startswith(s[0] + "라" + s[1:]) or n.startswith(s[0] + "청" + s[1:]) \
                or n.startswith(s[0] + "상" + s[1:]):
            return s
    return None


def sido_exact(name: str) -> str | None:
    """이름이 시도와 정확히 같을 때만 (시군구 '부산진구'·'광주시'를 시도로 잡지 않게)."""
    n = re.sub(r"\s+", "", str(name))
    return SIDO_FULL.get(n) or (n if n in SIDO else None)


def teachers_table(rows: list[dict], item: str | None = None) -> pd.DataFrame:
    """statisticsData 응답 → 시도·연도·교원수 (시도 이름은 짧은 이름으로).
    - 시군구 행은 버린다 (이름이 시도와 정확히 같은 행만).
    - 항목(ITM_NM)이 여럿이면 item 이 들어간 항목만, 그중 '여'·'남'·'1인당'이 붙은 항목은 뺀다.
    - 둘째 분류(C2_NM, 예: 성별·설립별)가 있으면 '계' 행만 쓴다.
    - 같은 시도·연도에 행이 여럿 남으면 가장 큰 값(합계)을 쓴다."""
    df = pd.DataFrame(rows)
    if df.empty or not {"C1_NM", "PRD_DE", "DT"} <= set(df.columns):
        return pd.DataFrame(columns=["시도", "연도", "교원수"])
    if "ITM_NM" in df:
        nm = df["ITM_NM"].astype(str)
        keep = ~nm.str.contains(r"1인당|여교원|남교원|^여|^남|비율|%")
        if item:
            keep &= nm.str.contains(item)
        if keep.any():
            df = df[keep]
    for c in ("C2_NM", "C3_NM"):
        if c in df and df[c].astype(str).str.strip().isin(TOTAL).any():
            df = df[df[c].astype(str).str.strip().isin(TOTAL)]
    df = df.assign(시도=df["C1_NM"].map(sido_exact), 연도=pd.to_numeric(df["PRD_DE"].astype(str).str[:4], errors="coerce"),
                   교원수=pd.to_numeric(df["DT"].astype(str).str.replace(",", ""), errors="coerce"))
    df = df.dropna(subset=["시도", "연도", "교원수"])
    out = df.groupby(["시도", "연도"], as_index=False)["교원수"].max()
    out["연도"] = out["연도"].astype(int)
    return out


LAST_HITS: list[dict] = []   # 마지막 검색 결과 (진단용)
_URL_IDS = re.compile(r"orgId=(\w+).*?tblId=(\w+)")


def candidate_tables(t: dict, client=None) -> list[dict]:
    """통계표 후보. 1) tblId 2) KOSIS 표 주소(url: …statHtml.do?orgId=…&tblId=…) 3) KOSIS 통계표 검색.
    검색은 기관을 가리지 않고 이름에 '교원'과 시도 표시('시도'·'시·도'·'지역')가 있는 표를 고른다.
    기관이 orgId 와 같은 표를 앞에 둔다."""
    global LAST_HITS
    if t.get("tblId"):
        return [{"ORG_ID": t.get("orgId", "334"), "TBL_ID": t["tblId"], "TBL_NM": t.get("tblNm", "")}]
    m = _URL_IDS.search(str(t.get("url") or ""))
    if m:
        return [{"ORG_ID": m.group(1), "TBL_ID": m.group(2), "TBL_NM": t.get("tblNm", "")}]
    out, seen, hits = [], set(), []
    for q in t.get("search") or ["시도별 교원수", "시도별 교원 현황", "교원수", "학교급별 교원수"]:
        try:
            rows = _get("statisticsSearch.do", client, searchNm=q)
        except KosisError:
            continue
        hits += rows
        for r in rows:
            nm = str(r.get("TBL_NM", ""))
            if "교원" in nm and "1인당" not in nm and any(k in nm for k in ("시도", "시·도", "시군구", "지역")) and r.get("TBL_ID") not in seen:
                seen.add(r.get("TBL_ID"))
                out.append(r)
    LAST_HITS = hits
    org = str(t.get("orgId", "334"))
    return sorted(out, key=lambda r: str(r.get("ORG_ID")) != org)


def hits_summary(n: int = 8) -> str:
    seen, rows = set(), []
    for r in LAST_HITS:
        k = (r.get("ORG_ID"), r.get("TBL_ID"))
        if k in seen:
            continue
        seen.add(k)
        rows.append(f"{r.get('TBL_NM')} ({r.get('ORG_ID')}/{r.get('TBL_ID')})")
    return "; ".join(rows[:n])


def _param_sets(t: dict) -> list[dict]:
    """표마다 받는 요청 변수가 달라 몇 가지를 차례로 시도한다.
    기간을 start~end 로 주면 그 기간 자료가 없는 표는 오류를 내므로 '최근 N개 시점'도 시도한다."""
    base = {"itmId": t.get("itmId", "ALL"), "objL1": "ALL", "prdSe": "Y"}
    rng = {"startPrdDe": str(t.get("start", 2019)), "endPrdDe": str(t.get("end", 2025))}
    recent = {"newEstPrdCnt": str(int(t.get("end", 2025)) - int(t.get("start", 2019)) + 1)}
    return [{**base, **rng}, {**base, **recent}, {**base, "objL2": "ALL", **rng}, {**base, "objL2": "ALL", **recent}]


def read_table(org: str, tbl: str, t: dict, client=None) -> tuple[pd.DataFrame, str]:
    """통계표 하나 → (시도·연도·교원수, 실패 사유). 시도가 10곳 이상 나오면 성공."""
    why = []
    for ps in _param_sets(t):
        try:
            rows = _get("statisticsData.do", client, orgId=org, tblId=tbl, **ps)
        except KosisError as e:
            why.append(str(e))
            continue
        df = teachers_table(rows, t.get("item"))
        if df["시도"].nunique() >= 10:
            return df, ""
        why.append(f"{len(rows)}행 중 시도 {df['시도'].nunique()}곳")
    uniq = list(dict.fromkeys(why))
    return pd.DataFrame(columns=["시도", "연도", "교원수"]), " / ".join(uniq[:3])


def _find_level(level: dict, client=None) -> dict | None:
    """학교급 표를 검색으로 찾는다: 이름이 검색어로 시작하고 시도 표시가 있는 표 (기관 101 e-지방지표 우선)."""
    global LAST_HITS
    q = level.get("search") or f"{level.get('name', '')} 교원수"
    try:
        rows = _get("statisticsSearch.do", client, searchNm=q)
    except KosisError:
        return None
    LAST_HITS += rows
    ok = [r for r in rows if str(r.get("TBL_NM", "")).replace(" ", "").startswith(q.replace(" ", ""))
          and "1인당" not in str(r.get("TBL_NM", "")) and "시도" in str(r.get("TBL_NM", ""))]
    ok.sort(key=lambda r: str(r.get("ORG_ID")) != str(level.get("orgId", "101")))
    return ok[0] if ok else None


def fetch_levels(t: dict, client=None) -> pd.DataFrame:
    """학교급별 표(초·중·고 …)를 각각 읽어 시도·연도별로 더한다.
    결과 열: 시도, 연도, 학교급별 교원 수 열, 교원수(합계). 모든 학교급이 있는 연도만 남긴다.
    attrs['table'] 에 쓴 표, attrs['missing'] 에 못 읽은 학교급을 남긴다."""
    global LAST_HITS
    LAST_HITS = []
    parts, used, missing = [], [], []
    for lv in t["levels"]:
        name = lv.get("name", "")
        c = {"ORG_ID": str(lv.get("orgId", "101")), "TBL_ID": lv["tblId"], "TBL_NM": name} if lv.get("tblId") \
            else _find_level(lv, client)
        if not c:
            missing.append(f"{name}(표 못 찾음)")
            continue
        df, why = read_table(c["ORG_ID"], c["TBL_ID"], t, client)
        if df.empty:
            missing.append(f"{name}({c['ORG_ID']}/{c['TBL_ID']}: {why})")
            continue
        parts.append(df.rename(columns={"교원수": name}).set_index(["시도", "연도"]))
        used.append(f"{name} {c['ORG_ID']}/{c['TBL_ID']}")
    if not parts:
        raise KosisError("학교급별 교원 수 표를 읽지 못함: " + "; ".join(missing))
    wide = pd.concat(parts, axis=1).dropna().reset_index()
    names = [p.columns[0] for p in parts]
    wide["교원수"] = wide[names].sum(axis=1)
    wide[names + ["교원수"]] = wide[names + ["교원수"]].astype(int)
    wide.attrs["table"] = "KOSIS " + ", ".join(used)
    wide.attrs["missing"] = missing
    return wide


def fetch_teachers(cfg: dict | None = None, client=None) -> pd.DataFrame:
    """시도별 교원 수. config 의 levels(학교급별 표)가 있으면 그것을 더하고, 없으면 표 하나를 찾아 읽는다.
    결과 표의 attrs['table'] 에 쓴 통계표 이름·ID를 남긴다."""
    cfg = cfg or (yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {})
    t = (cfg or {}).get("teachers") or {}
    if t.get("levels"):
        return fetch_levels(t, client)
    cands = candidate_tables(t, client)
    if not cands:
        raise KosisError("시도별 교원 수 통계표를 찾지 못함 (config/kosis.yaml 에 tblId 기입 필요)")
    why = []
    for c in cands[:5]:
        df, w = read_table(c["ORG_ID"], c["TBL_ID"], t, client)
        if not df.empty:
            df.attrs["table"] = f"{c.get('TBL_NM', '')} ({c['ORG_ID']}/{c['TBL_ID']})"
            return df
        why.append(f"{c.get('TBL_ID')}: {w}")
    raise KosisError("후보 통계표에서 시도별 교원 수를 읽지 못함: " + "; ".join(why))


def status() -> dict:
    """화면 진단용: 키 유무와 교원 수를 받은 결과 (키 값은 담지 않음)."""
    if not kosis_key():
        return {"ok": False, "reason": "KOSIS_KEY 없음"}
    try:
        df = fetch_teachers()
    except KosisError as e:
        found = hits_summary()
        return {"ok": False, "reason": str(e) + (f" · 검색된 표: {found}" if found else " · 검색 결과 없음")}
    miss = df.attrs.get("missing") or []
    return {"ok": True, "reason": f"{len(df)}행" + (f" · 빠진 학교급: {'; '.join(miss)}" if miss else ""),
            "table": df.attrs.get("table", "")}


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
