"""일반 웹페이지(보도자료·기사) 수집기. 제목·날짜·본문 문단을 뽑는다."""
from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup

from .schema import Document

DATE_RE = re.compile(r"(20\d{2})[.\-/년]\s?(\d{1,2})[.\-/월]\s?(\d{1,2})")


def parse_html(html: str, url: str, reliability: str = "C") -> Document:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    og = soup.find("meta", property="og:title")
    title = (og.get("content") if og else None) or (soup.title.string if soup.title else "") or url
    pub = soup.find("meta", property="article:published_time")
    date = pub.get("content", "")[:10] if pub else ""
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all(["p", "li", "td"])]
    paras = [p for p in paras if len(p) >= 20]
    text = "\n".join(dict.fromkeys(paras))  # 중복 문단 제거, 순서 유지
    if not date:
        m = DATE_RE.search(text)
        if m:
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    st = "news" if reliability == "C" else "policy"
    return Document(
        id="web-" + hashlib.sha1(url.encode()).hexdigest()[:10],
        source_type=st, title=title.strip(), text=text, url=url,
        reliability=reliability, verified=True, meta={"date": date},
    )


def fetch_page(url: str, reliability: str = "C", timeout: float = 20.0) -> Document:
    headers = {"User-Agent": "Mozilla/5.0 (research-collector)"}
    r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return parse_html(r.text, url, reliability)
