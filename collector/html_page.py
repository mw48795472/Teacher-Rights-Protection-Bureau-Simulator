"""일반 웹페이지(보도자료·기사) 수집기. 제목·날짜·본문 문단을 뽑는다."""
from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup

from .schema import Document

DATE_RE = re.compile(r"(20\d{2})[.\-/년]\s?(\d{1,2})[.\-/월]\s?(\d{1,2})")


def parse_html(html: str, url: str, reliability: str = "C", selector: str | None = None,
               title: str | None = None) -> Document:
    """selector: 본문 영역 CSS 선택자. 메뉴가 본문에 섞이는 사이트(경기교권보호지원센터 등)에 지정."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    og = soup.find("meta", property="og:title")
    title = title or (og.get("content") if og else None) or (soup.title.string if soup.title else "") or url
    pub = soup.find("meta", property="article:published_time")
    date = pub.get("content", "")[:10] if pub else ""
    container = (soup.select_one(selector) if selector else None) \
        or soup.find("article") or soup.find("main") or soup.body or soup
    tags = ["p", "li", "td"] + (["h2", "h3", "h4", "h5", "dt", "dd"] if selector else [])
    paras = [p.get_text(" ", strip=True) for p in container.find_all(tags)]
    paras = [p for p in paras if len(p) >= (4 if selector else 20)]
    text = "\n".join(dict.fromkeys(paras))  # 중복 문단 제거, 순서 유지
    if not date:
        m = DATE_RE.search(text)
        if m:
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    st = "news" if reliability == "C" else "policy"
    return Document(
        id="web-" + hashlib.sha1(url.encode()).hexdigest()[:10],
        source_type=st, title=(title or "").strip() or url, text=text, url=url,
        reliability=reliability, verified=True, meta={"date": date},
    )


HEADERS = {"User-Agent": "Mozilla/5.0 (research-collector)"}


def fetch_page(url: str, reliability: str = "C", timeout: float = 20.0,
               selector: str | None = None) -> Document:
    """일반 웹페이지. 교육부·경기도교육청 게시글은 sites.py 의 전용 수집기로 넘긴다."""
    from . import sites
    special = sites.handler_for(url)
    if special:
        return special(url, reliability=reliability, timeout=timeout)
    r = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return parse_html(r.text, url, reliability, selector=selector)
