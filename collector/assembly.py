"""열린국회정보(open.assembly.go.kr) Open API 수집기: 교권 관련 국회 법률안.

키(ASSEMBLY_KEY)는 .env 또는 Streamlit Secrets에 넣는다. 키 값은 화면·로그에 찍지 않는다.
- 국회의원 발의법률안 (nzmimeepazxkubdpn): 법률안명 검색어로 의안 목록 (제안자, 소관위, 처리 단계)
- 법률안 제안이유 및 주요내용 (BPMBILLSUMMARY): 의안번호별 제안이유 본문 → 지식베이스 문서

config/sources.yaml 의 `bills:` 에 검색어를 적는다. 수집 파이프라인(`--only bills`)에서도,
배포된 앱에서도(키가 있으면 하루 한 번) 쓴다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .gg_data import GgDataError, fetch_rows
from .schema import Document

BASE = "https://open.assembly.go.kr/portal/openapi"
BILLS = "nzmimeepazxkubdpn"
SUMMARY = "BPMBILLSUMMARY"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "processed" / "assembly_bills.jsonl"
CACHE_TTL = 86400
SAMPLE_ROWS = 5

AssemblyError = GgDataError


def assembly_key() -> str | None:
    return (os.environ.get("ASSEMBLY_KEY") or "").strip() or None


def _client() -> httpx.Client:
    return httpx.Client(timeout=20.0, headers={"User-Agent": "Mozilla/5.0 (research-collector)"})


def check_key(key: str | None = None, client: httpx.Client | None = None) -> dict:
    """키가 통하는지. 샘플 한도(5건)보다 많이 받으면 정상."""
    key = key or assembly_key()
    if not key:
        return {"ok": False, "reason": "ASSEMBLY_KEY 없음"}
    try:
        rows = fetch_rows(BILLS, key, page_size=10, max_pages=1, client=client, base=BASE,
                          AGE="22", BILL_NAME="교육")
    except Exception as e:  # noqa: BLE001  모듈을 다시 읽은 뒤 GgDataError 클래스가 달라져도 화면이 죽지 않게
        return {"ok": False, "reason": f"연결 실패: {e}" if isinstance(e, RuntimeError) else f"연결 실패 ({type(e).__name__})"}
    if len(rows) <= SAMPLE_ROWS:
        return {"ok": False, "reason": f"샘플 {len(rows)}건만 받음 (키 승인 전일 수 있음)", "rows": len(rows)}
    return {"ok": True, "reason": "정상", "rows": len(rows)}


def search_bills(key: str | None, name: str, ages=("22",), client: httpx.Client | None = None) -> list[dict]:
    out = []
    for age in ages:
        out += fetch_rows(BILLS, key, page_size=100, max_pages=10, client=client, base=BASE,
                          AGE=str(age), BILL_NAME=name)
    return out


def bill_summary(key: str | None, bill_no: str, client: httpx.Client | None = None) -> str:
    rows = fetch_rows(SUMMARY, key, page_size=5, max_pages=1, client=client, base=BASE, BILL_NO=str(bill_no))
    return (rows[0].get("SUMMARY") or "").strip() if rows else ""


def stage(b: dict) -> str:
    """의안의 현재 단계 (발의법률안 응답의 날짜 칸으로 판단)."""
    if b.get("PROC_RESULT"):
        return f"본회의 {b['PROC_RESULT']}"
    if b.get("LAW_PROC_DT"):
        return "법사위 처리"
    if b.get("CMT_PROC_DT"):
        return f"소관위 {b.get('CMT_PROC_RESULT_CD') or '처리'}"
    if b.get("CMT_PRESENT_DT"):
        return "소관위 상정"
    if b.get("COMMITTEE_DT"):
        return "소관위 회부"
    return "접수"


def bill_document(b: dict, summary: str) -> Document:
    meta = {k: b.get(k) for k in ("BILL_NO", "PROPOSE_DT", "PROPOSER", "COMMITTEE", "AGE")}
    meta = {k.lower(): v for k, v in meta.items() if v}
    meta["stage"] = stage(b)
    head = (f"{b.get('BILL_NAME')} (의안번호 {b.get('BILL_NO')}, {b.get('PROPOSE_DT')} 제안, {b.get('PROPOSER')}, "
            f"{b.get('COMMITTEE') or '소관위 미정'}, 현재 {meta['stage']})")
    return Document(id=f"bill-{b.get('BILL_NO')}", source_type="bill",
                    title=f"{b.get('BILL_NAME')} [{b.get('RST_PROPOSER') or b.get('PROPOSER')} 의원안, {b.get('PROPOSE_DT')}]",
                    text=head + "\n\n" + summary, url=b.get("DETAIL_LINK") or "", reliability="A",
                    verified=bool(summary), meta=meta)


def _matches(b: dict, summary: str, q: dict) -> bool:
    must = q.get("must_contain") or []
    return not must or any(w in summary for w in must)


def collect_bills(cfg: dict | None, key: str | None = None, client: httpx.Client | None = None,
                  delay: float = 0.1, log=print) -> list[Document]:
    """cfg: {ages: [22], max_bills: 60, since: 'YYYY-MM-DD', queries: [{name, must_contain?}]}"""
    cfg = cfg or {}
    key = key or assembly_key()
    if not key:
        log("[국회] ASSEMBLY_KEY가 없어 법률안 수집을 건너뜁니다.")
        return []
    own = client is None
    client = client or _client()
    ages = [str(a) for a in (cfg.get("ages") or [22])]
    since = str(cfg.get("since") or "")
    found: dict[str, tuple[dict, dict]] = {}
    try:
        for q in (cfg.get("queries") or []):
            try:
                rows = search_bills(key, q["name"], ages, client)
            except GgDataError as e:
                log(f"[국회] '{q['name']}' 검색 실패: {e}")
                continue
            for b in rows:
                if b.get("BILL_NO") and str(b.get("PROPOSE_DT") or "") >= since:
                    found.setdefault(b["BILL_NO"], (b, q))
        bills = sorted(found.values(), key=lambda t: str(t[0].get("PROPOSE_DT") or ""), reverse=True)
        docs = []
        for b, q in bills:
            if len(docs) >= int(cfg.get("max_bills", 60)):
                break
            try:
                s = bill_summary(key, b["BILL_NO"], client)
            except GgDataError as e:
                log(f"[국회] {b['BILL_NO']} 제안이유 실패: {e}")
                continue
            if _matches(b, s, q):
                docs.append(bill_document(b, s))
            if delay:
                time.sleep(delay)
        log(f"[국회] 법률안 {len(docs)}건 (검색 결과 {len(found)}건)")
        return docs
    finally:
        if own:
            client.close()


def cached_bills(cfg: dict | None, path: Path = CACHE, ttl: int = CACHE_TTL, log=lambda *_: None) -> list[Document]:
    """배포 앱용: 키가 있으면 하루 한 번 받아 data/processed/ 에 둔다. 실패하면 이전 캐시를 쓴다."""
    old = [Document.from_dict(json.loads(l)) for l in path.read_text(encoding="utf-8").splitlines() if l] \
        if path.exists() else []
    if not assembly_key() or (path.exists() and time.time() - path.stat().st_mtime < ttl):
        return old
    try:
        docs = collect_bills(cfg, delay=0, log=log)
    except Exception:  # 앱 시작을 막지 않는다
        return old
    if docs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(d.to_dict(), ensure_ascii=False) + "\n" for d in docs), encoding="utf-8")
        return docs
    return old
