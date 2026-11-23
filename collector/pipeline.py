"""수집 파이프라인.

    python -m collector.pipeline                    # 시드 + 모든 수집기
    python -m collector.pipeline --seed-only
    python -m collector.pipeline --only boards,pages   # 일부 수집기만
    python -m collector.pipeline --snapshot         # 공개 가능한 원문을 data/snapshot/ 에도 저장(커밋용)
    python -m collector.pipeline --list             # 수집기 목록과 필요한 키

수집기 (config/sources.yaml 의 섹션)
    laws          법률·시행령 조문            국가법령정보센터 API (LAW_OC)
    ordinances    자치법규(조례·규칙) 조문     국가법령정보센터 API (LAW_OC)
    admin_rules   행정규칙(교육부 고시 등)     국가법령정보센터 API (LAW_OC)
    precedents    판례 검색·요지               국가법령정보센터 API (LAW_OC)
    pages         웹페이지 (교육부·경기도교육청 게시글은 첨부 HWPX까지 읽음)
    boards        교육부·경기도교육청 보도자료 게시판 키워드 검색
    files         HWPX·PDF·DOCX 파일 (URL 또는 로컬 경로), data/raw/inbox/ 폴더
    bills         국회 법률안과 제안이유                 열린국회정보 API (ASSEMBLY_KEY)

결과: data/processed/corpus.jsonl
원문이 들어오면 같은 대상을 요약한 시드(팀 요약)를 뺀다. 대응 규칙은 merge() 참고.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from .schema import Document

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "config" / "seed_corpus.yaml"
SOURCES = ROOT / "config" / "sources.yaml"
OUT = ROOT / "data" / "processed" / "corpus.jsonl"
SNAPSHOT = ROOT / "data" / "snapshot" / "corpus.jsonl"
INBOX = ROOT / "data" / "raw" / "inbox"

# 원문이 이보다 짧으면(자바스크립트로 그리는 페이지 등) 수집이 덜 된 것으로 보고 시드를 남긴다.
MIN_REPLACE_CHARS = 150
# 스냅샷(저장소에 커밋)에 넣는 유형. 법령·판례는 저작권 보호 대상이 아니고(저작권법 제7조),
# 정부 보도자료·안내는 공공누리 제1유형이다. 언론 기사(C)는 넣지 않는다.
SNAPSHOT_TYPES = {"law", "ordinance", "admin_rule", "precedent", "policy", "foreign_policy", "bill"}

COLLECTORS = {
    "laws": "법률·시행령 조문 (LAW_OC)",
    "ordinances": "자치법규 조문 (LAW_OC)",
    "admin_rules": "행정규칙: 교육부 고시 등 (LAW_OC)",
    "precedents": "판례 (LAW_OC)",
    "pages": "웹페이지 (키 불필요)",
    "boards": "교육부·경기도교육청 보도자료 검색 (키 불필요)",
    "files": "HWPX·PDF·DOCX 파일, data/raw/inbox/ (키 불필요)",
    "bills": "국회 법률안·제안이유 (ASSEMBLY_KEY)",
}
KEYS = {**{k: "LAW_OC" for k in ("laws", "ordinances", "admin_rules", "precedents")}, "bills": "ASSEMBLY_KEY"}
NEEDS_LAW_OC = {"laws", "ordinances", "admin_rules", "precedents"}


def load_seed() -> list[Document]:
    data = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    return [Document.from_dict(d) for d in data["documents"]]


def load_sources() -> dict:
    return yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}


def _tag(docs: list[Document], entry: dict | None) -> list[Document]:
    """sources.yaml 항목의 replaces(대체할 시드 id)를 문서 meta 에 남긴다."""
    if entry and entry.get("replaces"):
        for d in docs:
            d.meta.setdefault("replaces", list(entry["replaces"]))
    return docs


def _collect_law_api(src: dict, only: set[str], log) -> list[Document]:
    from .law_api import LawAPIClient
    client = LawAPIClient()
    docs: list[Document] = []
    if "laws" in only:
        for i, name in enumerate((src.get("laws") or [])):
            try:
                got = client.fetch_by_name("law", name, doc_prefix=f"law{i}")
                log(f"[법령] {name}: 조문 {len(got)}개")
                for d in got:
                    d.meta["law"] = name
                docs += got
            except Exception as e:  # 한 소스 실패가 전체를 멈추지 않게
                log(f"[법령] {name} 실패: {e}")
    if "ordinances" in only:
        ords = list((src.get("ordinances") or []))
        for q in (src.get("ordinance_search") or []):
            try:
                hits = client.search_ordinances(q["query"], must_contain=tuple(q.get("must_contain", [])))
                known = {o["name"].replace(" ", "") for o in ords}
                for h in hits[: q.get("max", 10)]:
                    nm = h.get("자치법규명", "")
                    if nm and nm.replace(" ", "") not in known:
                        ords.append({"name": nm, "mst": h.get("자치법규일련번호", ""), "discovered": True})
                        known.add(nm.replace(" ", ""))
                log(f"[조례 검색] '{q['query']}': {len(hits)}건")
            except Exception as e:
                log(f"[조례 검색] '{q['query']}' 실패: {e}")
        for i, o in enumerate(ords):
            try:
                got = client.fetch_by_name("ordin", o["name"], doc_prefix=f"ord{i}")
                if not got and o.get("mst"):
                    got = client.fetch("ordin", o["mst"], doc_prefix=f"ord{i}")
                if not got and o.get("mst") and not o.get("discovered"):
                    from .law_api import fetch_ordinance_html
                    got = fetch_ordinance_html(o["mst"], o["name"], doc_prefix=f"ord{i}")
                log(f"[조례] {o['name']}: 조문 {len(got)}개")
                for d in got:
                    d.meta["ordinance"] = o["name"]
                    if o.get("discovered"):
                        d.meta["discovered"] = True  # 검색으로 찾은 조례는 시드 조문을 대체하지 않는다
                docs += _tag(got, o)
            except Exception as e:
                log(f"[조례] {o['name']} 실패: {e}")
    if "admin_rules" in only:
        for i, name in enumerate((src.get("admin_rules") or [])):
            try:
                got = client.fetch_admrul_by_name(name, doc_prefix=f"adm{i}")
                log(f"[행정규칙] {name}: 조문 {len(got)}개")
                docs += got
            except Exception as e:
                log(f"[행정규칙] {name} 실패: {e}")
    if "precedents" in only:
        p = src.get("precedents") or {}
        seen: set[str] = set()
        for q in p.get("queries", []):
            try:
                hits = client.search_precedents(q, display=p.get("max_per_query", 5))
            except Exception as e:
                log(f"[판례] '{q}' 검색 실패: {e}")
                continue
            n = 0
            for h in hits[: p.get("max_per_query", 5)]:
                pid = h.get("판례일련번호", "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                try:
                    d = client.fetch_precedent(pid)
                    if d:
                        d.meta["query"] = q
                        docs.append(d)
                        n += 1
                except Exception as e:
                    log(f"[판례] {pid} 실패: {e}")
            log(f"[판례] '{q}': {n}건")
    return docs


def collect_live(log=print, only: set[str] | None = None) -> list[Document]:
    only = set(only or COLLECTORS)
    src = load_sources()
    docs: list[Document] = []

    if only & NEEDS_LAW_OC:
        if os.environ.get("LAW_OC"):
            docs += _collect_law_api(src, only, log)
        else:
            log("LAW_OC가 없어 법령·조례·행정규칙·판례 수집을 건너뜁니다.")

    if "pages" in only:
        from .html_page import fetch_page
        for p in (src.get("pages") or []):
            try:
                d = fetch_page(p["url"], p.get("reliability", "C"), selector=p.get("selector"))
                if p.get("source_type"):
                    d.source_type = p["source_type"]
                if p.get("title"):
                    d.title = p["title"]
                log(f"[웹] {d.title[:40]} ({len(d.text)}자)")
                docs += _tag([d], p)
            except Exception as e:
                log(f"[웹] {p['url']} 실패: {e}")

    if "boards" in only:
        from .sites import BOARDS, collect_board
        for b in (src.get("boards") or []):
            if b.get("site") not in BOARDS:
                log(f"[게시판] 알 수 없는 site: {b.get('site')} (가능: {', '.join(BOARDS)})")
                continue
            docs += collect_board(b["site"], b.get("keywords", []), max_posts=b.get("max_posts", 20),
                                  pages=b.get("pages", 1), since=str(b.get("since", "")),
                                  attachments=b.get("attachments", True), log=log)

    if "files" in only:
        from .files import chunk, collect_inbox, load_entry
        for f in (src.get("files") or []):
            try:
                d = load_entry(f, ROOT)
                parts = chunk(d)
                log(f"[파일] {d.title[:40]} ({len(d.text)}자, {len(parts)}개로 나눔)")
                docs += _tag(parts, f)
            except Exception as e:
                log(f"[파일] {f.get('url') or f.get('path')} 실패: {e}")
        docs += [p for d in collect_inbox(INBOX, log=log) for p in chunk(d)]

    if "bills" in only:
        from .assembly import collect_bills
        docs += collect_bills(src.get("bills"), log=log)

    # 같은 문서가 게시판 검색과 pages 양쪽에서 들어오면 하나만 남긴다(replaces 가 있는 쪽 우선).
    uniq: dict[str, Document] = {}
    for d in docs:
        if d.id not in uniq or d.meta.get("replaces"):
            uniq[d.id] = d
    return list(uniq.values())


def _url_key(url: str) -> str:
    from .sites import post_key
    return post_key(url) if url else ""


def merge(seed: list[Document], live: list[Document]) -> list[Document]:
    """원문이 들어오면 같은 대상을 요약한 시드를 뺀다.

    1) sources.yaml 항목의 replaces: [시드 id]
    2) 시드와 원문의 URL이 같은 게시글/페이지 (MIN_REPLACE_CHARS 이상 수집됐을 때만)
    3) 조례: sources.yaml 에 이름으로 적은 조례의 같은 조문번호 (검색으로 찾은 조례는 제외)
    이미 verified 인 시드(이론 등)는 그대로 둔다.
    """
    full = [d for d in live if len(d.text) >= MIN_REPLACE_CHARS]
    explicit = {sid for d in full for sid in d.meta.get("replaces", [])}
    live_urls = {_url_key(d.url) for d in full if d.url}
    live_ord_articles = {d.article_no for d in live if d.source_type == "ordinance" and d.article_no
                         and not d.meta.get("discovered")}

    def replaced(s: Document) -> bool:
        if s.verified:
            return False
        if s.id in explicit:
            return True
        if s.source_type == "ordinance":
            return bool(s.article_no) and s.article_no in live_ord_articles
        return bool(s.url) and _url_key(s.url) in live_urls

    return [d for d in seed if not replaced(d)] + live


def snapshot_docs(live: list[Document]) -> list[Document]:
    return [d for d in live if d.source_type in SNAPSHOT_TYPES and d.reliability == "A"
            and d.verified and not d.meta.get("inbox")]


def write(docs: list[Document], path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
    return path


def _read_jsonl(path: Path) -> list[Document]:
    return [Document.from_dict(json.loads(l)) for l in path.read_text(encoding="utf-8").splitlines() if l]


LAW_CACHE = ROOT / "data" / "processed" / "law_cache.jsonl"
LAW_CACHE_TTL = 7 * 86400
LAW_TYPES = {"law", "ordinance", "admin_rule", "precedent"}


def cached_law_docs(path: Path = LAW_CACHE, ttl: int = LAW_CACHE_TTL, log=lambda *_: None) -> list[Document]:
    """배포 앱용: LAW_OC 가 있으면 법령·조례·행정규칙·판례 원문을 받아 일주일 캐시한다. 실패하면 이전 캐시."""
    old = _read_jsonl(path) if path.exists() else []
    if not os.environ.get("LAW_OC") or (path.exists() and time.time() - path.stat().st_mtime < ttl):
        return old
    try:
        docs = _collect_law_api(load_sources(), NEEDS_LAW_OC, log)
    except Exception:  # 앱 시작을 막지 않는다
        return old
    if docs:
        write(docs, path)
        return docs
    return old


ORD_CACHE = ROOT / "data" / "processed" / "ordinance_html_cache.jsonl"


def cached_ordinance_html(path: Path = ORD_CACHE, ttl: int = LAW_CACHE_TTL) -> list[Document]:
    """키 없이 sources.yaml 의 조례(mst) 본문을 국가법령정보센터 화면에서 받아 일주일 캐시한다.
    LAW_OC 가 막히거나 없어도 조례 조문 원문으로 팀 요약을 대체하기 위한 길. 실패하면 이전 캐시."""
    old = _read_jsonl(path) if path.exists() else []
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return old
    from .law_api import fetch_ordinance_html
    docs = []
    for i, o in enumerate(load_sources().get("ordinances") or []):
        if not o.get("mst"):
            continue
        try:
            docs += fetch_ordinance_html(o["mst"], o["name"], doc_prefix=f"ord{i}")
        except Exception:  # 앱 시작을 막지 않는다
            continue
    if docs:
        write(docs, path)
        return docs
    return old


def load_corpus(path: Path = OUT, live_bills: bool = True, live_laws: bool = True) -> list[Document]:
    """로컬 수집 결과 → 없으면 시드 + 커밋된 스냅샷(배포 환경) → 없으면 시드.
    배포 환경에서 원문 법령이 없고 LAW_OC 가 있으면 법령 원문을 받아(일주일 캐시) 팀 요약을 대체하고,
    법률안이 하나도 없고 ASSEMBLY_KEY 가 있으면 국회 법률안을 받아(하루 캐시) 더한다."""
    if path.exists():
        docs = _read_jsonl(path)
    elif path == OUT and SNAPSHOT.exists():
        docs = merge(load_seed(), _read_jsonl(SNAPSHOT))
    else:
        docs = load_seed()
    if live_laws and path == OUT and not any(d.source_type in LAW_TYPES and d.verified for d in docs):
        laws = cached_law_docs()
        if laws:
            have = {d.id for d in laws}
            docs = merge([d for d in docs if d.id not in have], laws)
    if live_laws and path == OUT and not any(d.source_type == "ordinance" and d.verified for d in docs):
        ords = cached_ordinance_html()
        if ords:
            docs = merge(docs, ords)
    if live_bills and path == OUT and not any(d.source_type == "bill" for d in docs):
        from .assembly import cached_bills
        docs += cached_bills(load_sources().get("bills"))
    return docs


def _print_list() -> None:
    for k, v in COLLECTORS.items():
        need = KEYS.get(k)
        ok = "사용 가능" if (not need or os.environ.get(need)) else f"{need} 필요"
        print(f"  {k:<12} {v}  [{ok}]")


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="교권보호국 시뮬레이터 지식베이스 수집")
    ap.add_argument("--seed-only", action="store_true", help="수집 없이 시드만 저장")
    ap.add_argument("--only", default="", help="쉼표로 구분한 수집기 이름 (예: boards,pages)")
    ap.add_argument("--snapshot", action="store_true",
                    help=f"공개 가능한 원문(법령·판례·정부자료)을 {SNAPSHOT.relative_to(ROOT)} 에도 저장")
    ap.add_argument("--list", action="store_true", help="수집기 목록")
    a = ap.parse_args(argv)
    if a.list:
        _print_list()
        return 0
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    if only and (bad := only - set(COLLECTORS)):
        ap.error(f"알 수 없는 수집기: {', '.join(sorted(bad))} (가능: {', '.join(COLLECTORS)})")
    seed = load_seed()
    live = [] if a.seed_only else collect_live(only=only)
    docs = merge(seed, live)
    p = write(docs)
    left = [d for d in docs if not d.verified]
    print(f"문서 {len(docs)}개 저장 → {p}  (원문 {len(docs) - len(left)}개, 팀 요약 {len(left)}개)")
    if left:
        print("  남은 팀 요약: " + ", ".join(d.id for d in left))
    if a.snapshot and live:
        snap = snapshot_docs(live)
        write(snap, SNAPSHOT)
        print(f"스냅샷 {len(snap)}개 → {SNAPSHOT.relative_to(ROOT)} (커밋하면 배포 앱에도 원문이 반영됩니다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
