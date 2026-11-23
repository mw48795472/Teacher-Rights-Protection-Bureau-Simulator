"""학교알리미(schoolinfo.go.kr) 공시정보 Open API: 학교별 공시 항목을 받아 시도별로 합친다.

키(SCHOOLINFO_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 키 값은 화면·로그에 찍지 않는다.
요청 형식 (학교알리미 'API 이용안내'):
  https://www.schoolinfo.go.kr/openApi.do?apiKey=…&apiType={항목}&pbanYr={공시연도}&schulKndCode={02|03|04}
응답: {"resultCode": "success", "resultMsg": "정상", "list": [...]}.
Open API에는 학교폭력 심의 결과가 없어서(공시 화면 전용), 여기서는 학생 수 같은 분모를 받는다. config/schoolinfo.yaml 참고.

    python -m collector.schoolinfo --check     # 키가 통하는지, 응답 칸 이름 보기
    python -m collector.schoolinfo             # data/measured/schoolinfo/{서비스}.csv 저장
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
BASE = "https://www.schoolinfo.go.kr/openApi.do"
CFG = ROOT / "config" / "schoolinfo.yaml"
OUT = ROOT / "data" / "measured" / "schoolinfo"
SIDO_NAMES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북",
              "전남", "경북", "경남", "제주", "충청북", "충청남", "전라북", "전라남", "경상북", "경상남", "전남광주"]
LONG = {"충청북": "충북", "충청남": "충남", "전라북": "전북", "전라남": "전남", "경상북": "경북", "경상남": "경남"}


class SchoolinfoError(RuntimeError):
    pass


def schoolinfo_key() -> str | None:
    return (os.environ.get("SCHOOLINFO_KEY") or "").strip() or None


def config() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}


def fetch(api_type: str, year: int, kind: str, key: str | None = None, client: httpx.Client | None = None,
          **params) -> pd.DataFrame:
    key = key or schoolinfo_key()
    if not key:
        raise SchoolinfoError("SCHOOLINFO_KEY 없음")
    own = client is None
    client = client or httpx.Client(timeout=60.0, headers={"User-Agent": "Mozilla/5.0 (research-collector)"})
    try:
        q = {"apiKey": key, "apiType": api_type, "pbanYr": str(year), "schulKndCode": kind, **params}
        try:
            r = client.get(BASE, params=q)
            r.raise_for_status()
        except httpx.HTTPError as e:  # URL(키 포함)이 메시지에 섞이지 않게
            code = f" HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else ""
            raise SchoolinfoError(f"apiType {api_type} 요청 실패 ({type(e).__name__}{code})") from None
        try:
            payload = r.json()
        except ValueError:
            head = " ".join(r.text.replace(key, "***").split())[:160]
            raise SchoolinfoError(f"JSON이 아닌 응답: {head or '(빈 응답)'}") from None
    finally:
        if own:
            client.close()
    if str(payload.get("resultCode", "")).lower() not in ("success", "", "00"):
        raise SchoolinfoError(f"{payload.get('resultCode')}: {payload.get('resultMsg')}")
    df = pd.DataFrame(payload.get("list") or [])
    if not df.empty:
        df.insert(0, "공시연도", int(year))
        df.insert(1, "학교급코드", kind)
    return df


def sido_of(df: pd.DataFrame) -> pd.Series:
    """주소·시도 칸(이름에 ADRES/ADRCD/ATPT/SIDO/시도/주소가 든 칸) 앞부분에서 시도 약칭을 찾는다."""
    cand = [c for c in df.columns if any(k in str(c).upper() for k in ("ADRCD_NM", "ADRES", "ATPT", "SIDO", "시도", "주소"))]
    for c in cand:
        s = df[c].astype(str).str.replace(" ", "")
        hit = s.str.extract("^(" + "|".join(sorted(SIDO_NAMES, key=len, reverse=True)) + ")")[0]
        if hit.notna().mean() > 0.8:
            return hit.map(lambda v: LONG.get(v, "광주" if v == "전남광주" else v) if isinstance(v, str) else v)
    return pd.Series([None] * len(df), index=df.index)


def students_by_sido(df: pd.DataFrame) -> pd.DataFrame:
    """학생수 칸(이름에 STDNT/학생이 들고 '계'·'TOT'·'SUM'이 든 숫자 칸, 없으면 학생 칸 합)을 시도×공시연도로 더한다."""
    if df.empty:
        return pd.DataFrame(columns=["시도", "공시연도", "학생수"])
    d = df.copy()
    d["시도"] = sido_of(d)
    num = {c: pd.to_numeric(d[c], errors="coerce") for c in d.columns if c not in ("공시연도", "학교급코드", "시도")}
    stu = [c for c, v in num.items() if v.notna().mean() > 0.8 and any(k in str(c).upper() for k in ("STDNT", "학생"))]
    tot = [c for c in stu if any(k in str(c).upper() for k in ("SUM", "TOT", "계", "합"))]
    cols = tot[:1] or stu
    if not cols or d["시도"].isna().all():
        return pd.DataFrame(columns=["시도", "공시연도", "학생수"])
    d["학생수"] = sum(num[c].fillna(0) for c in cols)
    return d.dropna(subset=["시도"]).groupby(["시도", "공시연도"], as_index=False)["학생수"].sum()


def check(cfg: dict | None = None, client=None) -> dict:
    cfg = cfg or config()
    if not schoolinfo_key():
        return {"ok": False, "reason": "SCHOOLINFO_KEY 없음"}
    svc = (cfg.get("services") or [{"apiType": "09"}])[0]
    year = max(cfg.get("years") or [2025])
    try:
        df = fetch(svc["apiType"], year, "03", client=client)
    except SchoolinfoError as e:
        return {"ok": False, "reason": str(e)}
    if df.empty:
        return {"ok": False, "reason": f"apiType {svc['apiType']} {year} 공시: 0행"}
    return {"ok": True, "reason": f"정상 (apiType {svc['apiType']}, {year} 공시 중학교 {len(df):,}행)",
            "columns": list(df.columns)}


def collect(cfg: dict | None = None, log=print, client=None) -> dict[str, pd.DataFrame]:
    cfg = cfg or config()
    OUT.mkdir(parents=True, exist_ok=True)
    got = {}
    for svc in cfg.get("services") or []:
        name = svc.get("name") or f"api{svc['apiType']}"
        frames = []
        for y in cfg.get("years") or []:
            for kind in (cfg.get("school_kinds") or {"02": "", "03": "", "04": ""}):
                try:
                    frames.append(fetch(svc["apiType"], y, str(kind), client=client, **(svc.get("params") or {})))
                except SchoolinfoError as e:
                    log(f"[학교알리미] {name} {y} {kind}: {e}")
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not df.empty:
            df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
        log(f"[학교알리미] {name}: {len(df):,}행")
        got[name] = df
    return got


def saved(name: str = "students_by_grade") -> pd.DataFrame:
    p = OUT / f"{name}.csv"
    return pd.read_csv(p, dtype={"학교급코드": str}) if p.exists() else pd.DataFrame()


_AUTO = {"tried": False, "note": ""}


def students(fetch: bool = True, log=None) -> pd.DataFrame:
    """시도×공시연도 학생 수. 저장 파일이 없고 키가 있으면 한 번 받아 저장한다(앱 첫 화면에서 자동).
    실패하면 빈 표와 _AUTO['note']에 이유를 남긴다."""
    df = saved()
    if df.empty and fetch and schoolinfo_key() and not _AUTO["tried"]:
        _AUTO["tried"] = True
        notes: list[str] = []
        try:
            df = collect(log=notes.append).get("students_by_grade", pd.DataFrame())
        except Exception as e:  # 화면을 막지 않는다
            notes.append(f"{type(e).__name__}: {e}")
            df = pd.DataFrame()
        _AUTO["note"] = " / ".join(n for n in notes if "0행" not in n or df.empty)[:600]
    out = students_by_sido(df)
    if not df.empty and out.empty:
        _AUTO["note"] = "받은 칸에서 시도·학생 수 칸을 찾지 못함. 받은 칸: " + ", ".join(map(str, df.columns[:40]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="학교알리미 공시정보 Open API")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if a.check:
        r = check()
        print(("✅ " if r["ok"] else "⚠️ ") + r["reason"])
        if r.get("columns"):
            print("칸:", ", ".join(map(str, r["columns"])))
        return 0 if r["ok"] else 1
    collect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
