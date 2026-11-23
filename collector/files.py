"""파일 수집기: 매뉴얼·지침·회의록처럼 웹페이지가 아닌 파일(HWPX·PDF·DOCX)을 지식베이스에 넣는다.

두 가지 방법:
1) config/sources.yaml 의 `files:` 에 URL 또는 로컬 경로와 메타데이터를 적는다(권장).
2) data/raw/inbox/ 폴더에 파일을 넣는다. 출처를 모르므로 신뢰도 D(참고)로 들어가며,
   인용하려면 1)처럼 sources.yaml 에 등록해 신뢰도와 출처 URL을 적어 준다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from .documents import SUPPORTED, extract_text, filename_from_headers
from .schema import Document

HEADERS = {"User-Agent": "Mozilla/5.0 (research-collector)"}


def _doc(text: str, *, key: str, title: str, url: str, source_type: str, reliability: str,
         meta: dict) -> Document:
    return Document(id="file-" + hashlib.sha1(key.encode()).hexdigest()[:10], source_type=source_type,
                    title=title, text=text, url=url, reliability=reliability, verified=bool(text),
                    meta=meta)


def load_entry(entry: dict, root: Path, timeout: float = 60.0) -> Document:
    """entry: {url | path, title?, source_type?, reliability?, source_url?, date?}"""
    if entry.get("path"):
        p = (root / entry["path"]).resolve() if not Path(entry["path"]).is_absolute() else Path(entry["path"])
        data, name = p.read_bytes(), p.name
        url = entry.get("source_url", "")
        key = str(entry["path"])
    else:
        r = httpx.get(entry["url"], headers=HEADERS, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        data, name = r.content, filename_from_headers(r.headers, entry["url"].rsplit("/", 1)[-1])
        url = entry.get("source_url", entry["url"])
        key = entry["url"]
    text = extract_text(data, name)
    return _doc(text, key=key, title=entry.get("title") or Path(name).stem, url=url,
                source_type=entry.get("source_type", "policy"),
                reliability=entry.get("reliability", "B"),
                meta={"file": name, **({"date": entry["date"]} if entry.get("date") else {})})


def collect_inbox(folder: Path, log=print) -> list[Document]:
    docs = []
    if not folder.exists():
        return docs
    for p in sorted(folder.iterdir()):
        if p.name.startswith(".") or not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED:
            log(f"[파일] {p.name}: 지원하지 않는 형식이라 건너뜀 ({', '.join(SUPPORTED)})")
            continue
        try:
            text = extract_text(p.read_bytes(), p.name)
        except Exception as e:
            log(f"[파일] {p.name} 실패: {e}")
            continue
        docs.append(_doc(text, key=f"inbox/{p.name}", title=p.stem, url="", source_type="policy",
                         reliability="D", meta={"file": p.name, "inbox": True}))
        log(f"[파일] {p.name} ({len(text)}자, 신뢰도 D: sources.yaml 에 등록하면 출처·신뢰도를 줄 수 있음)")
    return docs
