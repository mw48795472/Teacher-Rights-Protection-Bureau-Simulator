"""지방교육재정알리미(eduinfo.go.kr) Open API: 시도교육청 재정 공시 → 교권보호 관련 예산.

키(EDUFIN_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 키 값은 화면·로그에 찍지 않는다.
요청 형식 (eduinfo.go.kr 'API 이용안내'):
  http://openapi.eduinfo.go.kr/openApi.do?requestType={서비스}&key=…&Type=json&pIndex=1&pSize=100&YMQ={회계연도}
제공 서비스와 출력 칸 이름은 로그인한 '서비스별 OPEN API 메타 정보' 화면에만 나와서, 서비스 이름은
config/edufin.yaml 에 적고 응답의 행을 그대로 저장한다. 그다음 사업명 칸에서 교권·교육활동보호 키워드로 거른다.

    python -m collector.edufin --check     # 키·서비스가 통하는지, 응답 칸 이름 보기
    python -m collector.edufin             # data/measured/edufin/{서비스}.csv 저장
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
BASE = "http://openapi.eduinfo.go.kr/openApi.do"
CFG = ROOT / "config" / "edufin.yaml"
OUT = ROOT / "data" / "measured" / "edufin"


LAST_HEAD = ""   # 마지막 응답 앞부분 (키는 가림). 행이 0건일 때 원인을 보여 주려고 남긴다


class EdufinError(RuntimeError):
    pass


def edufin_key() -> str | None:
    return (os.environ.get("EDUFIN_KEY") or "").strip() or None


def config() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}


def _rows(payload) -> list[dict]:
    """응답 JSON 안에서 가장 긴 '딕셔너리 목록'을 행으로 본다 (서비스마다 감싸는 형식이 달라도 되게)."""
    best: list[dict] = []

    def walk(x):
        nonlocal best
        if isinstance(x, list):
            if x and all(isinstance(i, dict) and any(not isinstance(v, (dict, list)) for v in i.values()) for i in x) \
                    and len(x) > len(best):   # 감싸는 칸({"head": [...]}, {"row": [...]})은 행이 아니다
                best = x
            for i in x:
                walk(i)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
    walk(payload)
    return best


def _error(payload) -> str | None:
    """RESULT/CODE 형식의 오류 응답이면 메시지."""
    if isinstance(payload, dict):
        res = payload.get("RESULT") or payload.get("result")
        if isinstance(res, dict):
            code = str(res.get("CODE") or res.get("code") or "")
            if code and not code.endswith("000") and code != "INFO-200":
                return f"{code}: {res.get('MESSAGE') or res.get('message') or ''}"
    return None


def _xml_rows(root) -> list[dict]:
    """XML에서 자식 칸을 가진 같은 이름 원소가 여럿이면 그것을 행으로 본다."""
    best: list[dict] = []
    for parent in root.iter():
        groups: dict[str, list] = {}
        for k in parent:
            if len(k) and k.tag not in ("head", "RESULT", "result"):
                groups.setdefault(k.tag, []).append(k)
        for kids in groups.values():
            if len(kids) > len(best):
                best = [{c.tag: (c.text or "").strip() for c in k} for k in kids]
    return best


def parse_body(text: str, key: str = "") -> dict | list:
    """JSON 이면 그대로, XML 이면 {RESULT, rows} 로. 둘 다 아니면 응답 앞부분(키는 가림)을 담아 오류."""
    t = (text or "").strip().lstrip("\ufeff")
    try:
        import json
        return json.loads(t)
    except ValueError:
        pass
    if t.startswith("<"):
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(t)
        except ET.ParseError:
            root = None
        if root is not None:
            code = root.findtext(".//CODE") or root.findtext(".//code")
            msg = root.findtext(".//MESSAGE") or root.findtext(".//message") or ""
            out: dict = {"rows": _xml_rows(root)}
            if code:
                out["RESULT"] = {"CODE": code, "MESSAGE": msg}
            return out
    head = " ".join(t.replace(key, "***").split())[:160] if key else " ".join(t.split())[:160]
    raise EdufinError(f"JSON·XML이 아닌 응답: {head or '(빈 응답)'}")


def fetch(service: str, year: int | str | None, key: str | None = None, page_size: int = 100, max_pages: int = 200,
          client: httpx.Client | None = None, **params) -> pd.DataFrame:
    key = key or edufin_key()
    if not key:
        raise EdufinError("EDUFIN_KEY 없음")
    own = client is None
    client = client or httpx.Client(timeout=30.0, headers={"User-Agent": "Mozilla/5.0 (research-collector)"})
    out: list[dict] = []
    try:
        for page in range(1, max_pages + 1):
            q = {"requestType": service, "key": key, "Type": "json", "type": "json", "pIndex": page,
                 "pSize": page_size, **params}
            if year is not None and "YMQ" not in q:
                q["YMQ"] = str(year)
            try:
                r = client.get(BASE, params=q)
                r.raise_for_status()
            except httpx.HTTPError as e:  # URL(키 포함)이 메시지에 섞이지 않게
                code = f" HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else ""
                raise EdufinError(f"{service} 요청 실패 ({type(e).__name__}{code})") from None
            global LAST_HEAD
            LAST_HEAD = " ".join(r.text.replace(key, "***").split())[:200]
            payload = parse_body(r.text, key)
            err = _error(payload)
            if err:
                raise EdufinError(err)
            rows = _rows(payload)
            out.extend(rows)
            if len(rows) < page_size:
                break
    finally:
        if own:
            client.close()
    df = pd.DataFrame(out)
    if not df.empty and year is not None and "회계연도" not in df:
        df.insert(0, "회계연도", int(str(year)[:4]))
    return df


def keyword_rows(df: pd.DataFrame, keywords) -> pd.DataFrame:
    """문자열 칸 어디에든 키워드가 들어간 행 (예: 사업명에 '교권', '교육활동보호')."""
    if df.empty:
        return df
    text = df.select_dtypes(exclude="number").astype(str).agg(" ".join, axis=1)
    mask = text.str.contains("|".join(map(str, keywords)), regex=True)
    return df[mask]


KEY_PROBLEM = ("인증키", "ERROR-290", "ERROR-300", "INFO-300", "INFO-100", "KEY")


def _variants(years) -> list[tuple[str, dict, int | None]]:
    """(설명, 추가 파라미터, 회계연도) — 회계연도 형식이 공개 안내에 없어 몇 가지를 차례로 시도한다."""
    ys = sorted({int(y) for y in years}, reverse=True) or [2024]
    out = [("YMQ 없이", {}, None)]
    for y in ys[:4]:
        out.append((f"YMQ={y}", {"YMQ": str(y)}, y))
    out.append((f"YMQ={ys[0]}12", {"YMQ": f"{ys[0]}12"}, ys[0]))
    out.append((f"YMQ={ys[0]}4 (4분기)", {"YMQ": f"{ys[0]}4"}, ys[0]))
    return out


def probe(service: str = "opclTotal", years=(2025, 2024, 2023, 2022), client=None) -> dict:
    """실제 행이 오는 요청 조건을 찾는다. {ok, mode, params, year, df, tried:[(설명, 결과)], key_problem}"""
    tried, key_problem = [], False
    for label, extra, y in _variants(years):
        try:
            df = fetch(service, None, page_size=20, max_pages=1, client=client, **extra)
        except EdufinError as e:
            msg = str(e)
            tried.append((label, msg[:120]))
            key_problem |= any(k in msg for k in KEY_PROBLEM)
            continue
        if not df.empty:
            if y is not None and "회계연도" not in df:
                df.insert(0, "회계연도", y)
            return {"ok": True, "mode": label, "params": extra, "year": y, "df": df, "tried": tried,
                    "key_problem": False}
        head = LAST_HEAD
        tried.append((label, f"0행 · {head[:120] or '(빈 응답)'}"))
        key_problem |= any(k in head for k in KEY_PROBLEM)
    return {"ok": False, "mode": None, "params": {}, "year": None, "df": pd.DataFrame(), "tried": tried,
            "key_problem": key_problem}


def check(cfg: dict | None = None, client=None) -> dict:
    cfg = cfg or config()
    svc = (cfg.get("services") or [{}])[0]
    if not edufin_key():
        return {"ok": False, "reason": "EDUFIN_KEY 없음"}
    pr = probe(svc.get("requestType", "opclTotal"), cfg.get("years") or [2024], client=client)
    if pr["ok"]:
        df = pr["df"]
        if len(df) <= 5:
            return {"ok": False, "reason": f"{pr['mode']}로 {len(df)}건만 받음 (샘플 키 한도: 키가 아직 승인되지 않았을 수 있음)",
                    "columns": list(df.columns)}
        return {"ok": True, "reason": f"정상 ({pr['mode']})", "rows": len(df), "columns": list(df.columns)}
    tried = " / ".join(f"{a}: {b}" for a, b in pr["tried"])
    if pr["key_problem"]:
        return {"ok": False, "reason": f"키 문제로 보임 (미승인·오타·만료). 시도한 조건: {tried}"}
    return {"ok": False, "reason": f"어떤 조건으로도 행이 오지 않음. 시도한 조건: {tried}"}


def saved(name: str) -> pd.DataFrame:
    p = OUT / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def collect(cfg: dict | None = None, log=print, client=None) -> dict[str, pd.DataFrame]:
    """서비스마다 먼저 probe()로 통하는 조건을 찾고, 회계연도가 필요한 형식이면 연도별로 받는다."""
    cfg = cfg or config()
    OUT.mkdir(parents=True, exist_ok=True)
    got = {}
    years = cfg.get("years") or []
    for svc in cfg.get("services") or []:
        name = svc.get("name") or svc["requestType"]
        pr = probe(svc["requestType"], years or [2024], client=client)
        if not pr["ok"]:
            log(f"[지방교육재정알리미] {name}: 행 없음 ({'; '.join(f'{a}: {b}' for a, b in pr['tried'])})")
            got[name] = pd.DataFrame()
            continue
        extra = {**(svc.get("params") or {})}
        frames = []
        if pr["year"] is None:            # 회계연도 없이 전체가 오는 서비스
            frames.append(fetch(svc["requestType"], None, client=client, **extra))
        else:
            fmt = pr["params"]["YMQ"].replace(str(pr["year"]), "{y}")
            for y in years or [pr["year"]]:
                try:
                    df = fetch(svc["requestType"], None, client=client, YMQ=fmt.format(y=y), **extra)
                except EdufinError as e:
                    log(f"[지방교육재정알리미] {name} {y}: {e}")
                    continue
                if not df.empty and "회계연도" not in df:
                    df.insert(0, "회계연도", int(y))
                frames.append(df)
        frames = [f for f in frames if not f.empty]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not df.empty:
            df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
            log(f"[지방교육재정알리미] {name}: {len(df)}행 ({pr['mode']}) → {OUT / (name + '.csv')}")
        got[name] = df
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="지방교육재정알리미 Open API 수집")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    st = check()
    print(f"[지방교육재정알리미] 키 확인: {'정상' if st['ok'] else '실패'} ({st['reason']})")
    if st.get("columns"):
        print("응답 칸:", ", ".join(map(str, st["columns"])))
    if a.check or not st["ok"]:
        return 0 if st["ok"] else 1
    collect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
