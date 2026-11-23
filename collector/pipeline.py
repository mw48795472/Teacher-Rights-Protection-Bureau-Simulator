"""수집 파이프라인.

    python -m collector.pipeline            # 시드 + (LAW_OC 있으면) 법령 API + 웹페이지
    python -m collector.pipeline --seed-only

결과: data/processed/corpus.jsonl  (원문에서 수집한 조문은 같은 조문번호의 시드 요약을 대체)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from .schema import Document

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "config" / "seed_corpus.yaml"
SOURCES = ROOT / "config" / "sources.yaml"
OUT = ROOT / "data" / "processed" / "corpus.jsonl"


def load_seed() -> list[Document]:
    data = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    return [Document.from_dict(d) for d in data["documents"]]


def collect_live(log=print) -> list[Document]:
    docs: list[Document] = []
    src = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    if os.environ.get("LAW_OC"):
        from .law_api import LawAPIClient
        client = LawAPIClient()
        for i, name in enumerate(src.get("laws", [])):
            try:
                got = client.fetch_by_name("law", name, doc_prefix=f"law{i}")
                log(f"[법령] {name}: 조문 {len(got)}개")
                docs += got
            except Exception as e:  # 한 소스 실패가 전체를 멈추지 않게
                log(f"[법령] {name} 실패: {e}")
        for i, o in enumerate(src.get("ordinances", [])):
            try:
                got = client.fetch_by_name("ordin", o["name"], doc_prefix=f"ord{i}")
                if not got and o.get("mst"):
                    got = client.fetch("ordin", o["mst"], doc_prefix=f"ord{i}")
                log(f"[조례] {o['name']}: 조문 {len(got)}개")
                for d in got:
                    d.meta["ordinance"] = o["name"]
                docs += got
            except Exception as e:
                log(f"[조례] {o['name']} 실패: {e}")
    else:
        log("LAW_OC가 없어 법령 API 수집을 건너뜁니다.")
    from .html_page import fetch_page
    for p in src.get("pages", []):
        try:
            d = fetch_page(p["url"], p.get("reliability", "C"))
            log(f"[웹] {d.title[:40]} ({len(d.text)}자)")
            docs.append(d)
        except Exception as e:
            log(f"[웹] {p['url']} 실패: {e}")
    return docs


def merge(seed: list[Document], live: list[Document]) -> list[Document]:
    """원문 조례 조문이 들어오면 같은 조문번호의 시드 요약을 뺀다."""
    live_ord_articles = {d.article_no for d in live if d.source_type == "ordinance" and d.article_no}
    kept = [d for d in seed
            if not (d.source_type == "ordinance" and d.article_no in live_ord_articles)]
    return kept + live


def write(docs: list[Document], path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_corpus(path: Path = OUT) -> list[Document]:
    if not path.exists():
        return load_seed()
    return [Document.from_dict(json.loads(l)) for l in path.read_text(encoding="utf-8").splitlines() if l]


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-only", action="store_true")
    a = ap.parse_args(argv)
    seed = load_seed()
    live = [] if a.seed_only else collect_live()
    docs = merge(seed, live)
    p = write(docs)
    print(f"문서 {len(docs)}개 저장 → {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
