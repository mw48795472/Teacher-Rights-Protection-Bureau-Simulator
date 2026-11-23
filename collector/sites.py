"""기관 사이트 전용 수집기: 교육부·경기도교육청 보도자료.

- 교육부(moe.go.kr) 보도자료: 웹 본문(.synapTextWrap)이 요약본이거나 비어 있고, 전문은 첨부
  .hwpx 에 있다. 첨부 보도자료를 읽어 본문으로 쓰고, [별첨] PDF 등은 별도 문서로 만든다.
- 경기도교육청(goe.go.kr) 보도자료: 본문이 .bbsV_cont 에 있다.
- 게시판 검색: 제목 키워드로 목록을 훑어 게시글 URL을 모은다.

두 사이트 모두 공공누리 제1유형(출처표시) 표시가 붙은 공공저작물이다.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .documents import UnsupportedFile, extract_text, filename_from_headers
from .schema import Document

HEADERS = {"User-Agent": "Mozilla/5.0 (research-collector)"}
MOE = "https://www.moe.go.kr"
GOE = "https://www.goe.go.kr"
MOE_PRESS = {"boardID": "294", "m": "020402", "s": "moe"}
GOE_PRESS = {"mi": "10102", "bbsId": "1922"}
DATE_RE = re.compile(r"(20\d{2})[.\-/]\s?(\d{1,2})[.\-/]\s?(\d{1,2})")
TEXT_EXT = (".hwpx", ".pdf", ".docx")


def _doc_id(prefix: str, key: str) -> str:
    return f"{prefix}-" + hashlib.sha1(key.encode()).hexdigest()[:10]


def _date(s: str) -> str:
    m = DATE_RE.search(s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def _clean_title(filename: str) -> str:
    name = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", filename).strip()
    name = re.sub(r"^\[[^\]]*보도자료\]\s*", "", name)  # [교육부 01-22(목) 석간보도자료]
    return name.strip()


def _client(http: httpx.Client | None, timeout: float) -> httpx.Client:
    return http or httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)


# ── 교육부 ──────────────────────────────────────────────

def parse_moe_view(html: str, url: str) -> dict:
    """교육부 게시글 HTML → {title, date, text, attachments:[(이름, 절대URL)]}"""
    soup = BeautifulSoup(html, "lxml")
    head = soup.select_one("section.news-header")
    title = head.find("h3").get_text(" ", strip=True) if head and head.find("h3") else ""
    date = _date(head.get_text(" ", strip=True)) if head else ""
    body = soup.select_one(".synapTextWrap") or soup.select_one("#postContents")
    text = "\n".join(t.strip() for t in body.get_text("\n").splitlines() if t.strip()) if body else ""
    atts = []
    for a in soup.select("a[href*='fileDown.do']"):
        li = a.find_parent("li")
        label = li.find("span").get_text(" ", strip=True) if li and li.find("span") else a.get_text(" ", strip=True)
        label = re.sub(r"\s*\[\s*[\d.,]+\s*[KMG]?B\s*\]\s*$", "", label).strip()
        atts.append((label, urljoin(MOE, a["href"])))
    if not title and atts:
        title = _clean_title(atts[0][0])
    return {"title": title, "date": date, "text": text, "attachments": list(dict.fromkeys(atts))}


def fetch_moe_post(url: str, *, reliability: str = "A", timeout: float = 30.0,
                   http: httpx.Client | None = None, attachments: bool = True) -> list[Document]:
    c = _client(http, timeout)
    r = c.get(url)
    r.raise_for_status()
    v = parse_moe_view(r.text, url)
    main_text, extra, errors = v["text"], [], []
    for i, (label, href) in enumerate(v["attachments"]):
        if not label.lower().endswith(TEXT_EXT):
            continue
        is_press = "보도자료" in label or (i == 0 and not label.startswith("[별첨"))
        if not is_press and not attachments:
            continue
        try:
            fr = c.get(href)
            fr.raise_for_status()
            text = extract_text(fr.content, filename_from_headers(fr.headers, label) or label)
        except Exception as e:  # 첨부 하나가 실패해도 본문은 살린다
            errors.append(f"{label}: {e}")
            continue
        if is_press:
            if len(text) > len(main_text):
                main_text = text  # 첨부 보도자료 전문이 웹 본문(요약)보다 길면 전문을 쓴다
        else:
            extra.append((label, text))
    meta = {"date": v["date"], "site": "moe", "license": "공공누리 제1유형"}
    if errors:
        meta["attachment_errors"] = errors
    docs = [Document(id=_doc_id("moe", url), source_type="policy",
                     title=f"교육부 보도자료 「{v['title']}」" + (f"({v['date']})" if v["date"] else ""),
                     text=main_text, url=url, reliability=reliability, verified=bool(main_text),
                     meta=meta)]
    for label, text in extra:
        docs.append(Document(id=_doc_id("moe", url + label), source_type="policy",
                             title=f"교육부 {_clean_title(label)}", text=text, url=url,
                             reliability=reliability, verified=bool(text),
                             meta={"date": v["date"], "site": "moe", "attachment": label,
                                   "parent": docs[0].id, "license": "공공누리 제1유형"}))
    return [d for d in docs if d.text]


def parse_moe_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tr in soup.select("table tbody tr"):
        a = tr.find("a", onclick=re.compile(r"goView\("))
        if not a:
            continue
        args = re.findall(r"'([^']*)'", a["onclick"])
        if len(args) < 2:
            continue
        board_id, seq = args[0], args[1]
        tds = tr.find_all("td")
        out.append({
            "title": (a.get("title") or a.get_text(" ", strip=True)).strip(),
            "date": _date(" ".join(td.get_text(" ", strip=True) for td in tds)),
            "url": f"{MOE}/boardCnts/viewRenew.do?boardID={board_id}&boardSeq={seq}&lev=0&m={MOE_PRESS['m']}",
        })
    return out


def search_moe_press(keyword: str, *, pages: int = 1, http: httpx.Client | None = None,
                     timeout: float = 20.0, search_type: str = "S") -> list[dict]:
    c = _client(http, timeout)
    found = []
    for page in range(1, pages + 1):
        r = c.get(f"{MOE}/boardCnts/listRenew.do",
                  params={**MOE_PRESS, "searchType": search_type, "searchStr": keyword, "page": page})
        r.raise_for_status()
        rows = parse_moe_list(r.text)
        found += rows
        if len(rows) < 10:
            break
    return found


# ── 경기도교육청 ─────────────────────────────────────────

def parse_goe_view(html: str, url: str, reliability: str = "A") -> Document:
    soup = BeautifulSoup(html, "lxml")
    view = soup.select_one(".bbs_ViewA") or soup
    h3 = view.find("h3")
    title = h3.get_text(" ", strip=True) if h3 else ""
    data = view.select_one(".bbsV_data")
    date = _date(data.get_text(" ", strip=True)) if data else ""
    body = view.select_one(".bbsV_cont")
    text = "\n".join(t.strip() for t in body.get_text("\n").splitlines() if t.strip()) if body else ""
    atts = [a.get_text(" ", strip=True).replace("\xa0", "").strip() for a in view.select(".bbsV_atchmnfl a.fileName")]
    return Document(id=_doc_id("goe", url), source_type="policy",
                    title=f"경기도교육청 보도자료 「{title}」" + (f"({date})" if date else ""),
                    text=text, url=url, reliability=reliability, verified=bool(text),
                    meta={"date": date, "site": "goe", "attachments": atts, "license": "공공누리 제1유형"})


def fetch_goe_post(url: str, *, reliability: str = "A", timeout: float = 30.0,
                   http: httpx.Client | None = None, **_) -> list[Document]:
    c = _client(http, timeout)
    r = c.get(url)
    r.raise_for_status()
    d = parse_goe_view(r.text, url, reliability)
    return [d] if d.text else []


def parse_goe_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.select("a.nttInfoBtn[data-id]"):
        tit = a.select_one(".lst_tit")
        out.append({
            "title": (a.get("title") or (tit.get_text(" ", strip=True) if tit else "")).strip(),
            "date": _date(a.get_text(" ", strip=True)),
            "url": f"{GOE}/goe/na/ntt/selectNttInfo.do?mi={GOE_PRESS['mi']}&bbsId={GOE_PRESS['bbsId']}&nttSn={a['data-id']}",
        })
    return out


def search_goe_press(keyword: str, *, pages: int = 1, http: httpx.Client | None = None,
                     timeout: float = 20.0, search_type: str = "sj") -> list[dict]:
    c = _client(http, timeout)
    found = []
    for page in range(1, pages + 1):
        r = c.get(f"{GOE}/goe/na/ntt/selectNttList.do",
                  params={**GOE_PRESS, "searchType": search_type, "searchValue": keyword, "currPage": page})
        r.raise_for_status()
        rows = parse_goe_list(r.text)
        found += rows
        if len(rows) < 10:
            break
    return found


# ── 공통 ────────────────────────────────────────────────

BOARDS: dict[str, tuple[Callable, Callable]] = {
    "moe_press": (search_moe_press, fetch_moe_post),
    "goe_press": (search_goe_press, fetch_goe_post),
}


def handler_for(url: str) -> Callable | None:
    """URL이 전용 수집기가 있는 게시글이면 Document 하나를 돌려주는 함수를 준다(fetch_page 호환)."""
    u = urlparse(url)
    host = u.netloc.lower()
    if host.endswith("moe.go.kr") and "viewRenew.do" in u.path:
        fn = fetch_moe_post
    elif host.endswith("goe.go.kr") and "selectNttInfo.do" in u.path:
        fn = fetch_goe_post
    else:
        return None

    def one(url: str, reliability: str = "A", timeout: float = 30.0) -> Document:
        docs = fn(url, reliability=reliability, timeout=timeout, attachments=False)
        if not docs:
            raise ValueError("본문을 찾지 못했습니다.")
        return docs[0]
    return one


def post_key(url: str) -> str:
    """같은 게시글을 다른 쿼리 순서로 적어도 같게 보도록 정규화한 키."""
    u = urlparse(url)
    q = parse_qs(u.query)
    for k in ("boardSeq", "nttSn"):
        if k in q:
            return f"{u.netloc.lower().removeprefix('www.')}|{k}={q[k][0]}"
    return f"{u.netloc.lower().removeprefix('www.')}{u.path.rstrip('/')}?{u.query}"


def collect_board(site: str, keywords: list[str], *, max_posts: int = 20, pages: int = 1,
                  since: str = "", attachments: bool = True, delay: float = 0.5,
                  timeout: float = 30.0, log=print) -> list[Document]:
    """게시판을 키워드로 검색해 게시글을 수집한다. since='2023-07-01' 처럼 날짜 하한을 줄 수 있다."""
    search, fetch = BOARDS[site]
    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as c:
        hits: dict[str, dict] = {}
        for kw in keywords:
            try:
                for h in search(kw, pages=pages, http=c):
                    if since and h["date"] and h["date"] < since:
                        continue
                    hits.setdefault(post_key(h["url"]), h)
            except httpx.HTTPError as e:
                log(f"[{site}] '{kw}' 검색 실패: {e}")
            time.sleep(delay)
        picked = sorted(hits.values(), key=lambda h: h["date"], reverse=True)[:max_posts]
        log(f"[{site}] 검색 결과 {len(hits)}건 중 {len(picked)}건 수집")
        docs: list[Document] = []
        for h in picked:
            try:
                got = fetch(h["url"], http=c, attachments=attachments)
                docs += got
                log(f"  - {h['title'][:40]} ({sum(len(d.text) for d in got)}자, 문서 {len(got)}개)")
            except Exception as e:
                log(f"  - {h['title'][:40]} 실패: {e}")
            time.sleep(delay)
    return docs
