"""국가법령정보센터 Open API(DRF) 수집기.

인증키(OC)는 https://open.law.go.kr 에서 무료로 신청한다. 환경변수 LAW_OC 로 전달.
법률(target=law)과 자치법규(target=ordin)의 XML을 조문 단위 Document 로 바꾼다.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

import httpx

from .schema import Document

BASE = "https://www.law.go.kr/DRF"

# 법률은 <조문단위>, 자치법규는 <조> 요소에 조문이 담긴다.
ARTICLE_TAGS = ("조문단위", "조")
TITLE_TAGS = ("조문제목", "조제목")
BODY_TAGS = ("조문내용", "조내용")
NUMBER_TAGS = ("조문번호", "조번호")
SUB_TAGS = ("항내용", "호내용", "목내용")
NAME_TAGS = ("법령명_한글", "법령명한글", "자치법규명")


def _text(el: ET.Element | None) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""


def _first(el: ET.Element, tags: tuple[str, ...]) -> ET.Element | None:
    for t in tags:
        found = el.find(t)
        if found is not None:
            return found
    return None


def _article_no(el: ET.Element) -> str:
    num = _first(el, NUMBER_TAGS)
    raw = _text(num) if num is not None else el.get("조문번호", "")
    if not raw:
        return ""
    if raw.startswith("제"):
        return raw
    digits = raw.lstrip("0")
    # 자치법규는 '000600'처럼 6자리(조 4 + 가지번호 2)로 오는 경우가 있다.
    if len(raw) == 6 and raw.isdigit():
        main, branch = int(raw[:4]), int(raw[4:])
        return f"제{main}조" + (f"의{branch}" if branch else "")
    return f"제{digits or raw}조"


def parse_law_xml(xml_text: str, *, source_type: str, url: str, doc_prefix: str) -> list[Document]:
    root = ET.fromstring(xml_text)
    name = ""
    for t in NAME_TAGS:
        found = root.find(f".//{t}")
        if found is not None and _text(found):
            name = _text(found)
            break
    docs: list[Document] = []
    for tag in ARTICLE_TAGS:
        for art in root.iter(tag):
            # 법률 XML에는 '전문'(장·절 제목) 단위도 섞여 있어 걸러낸다.
            if art.findtext("조문여부") == "전문":
                continue
            body = _text(_first(art, BODY_TAGS))
            subs = [_text(s) for s in art.iter() if s.tag in SUB_TAGS and _text(s)]
            text = " ".join([body, *subs]).strip()
            if not text:
                continue
            no = _article_no(art)
            title = _text(_first(art, TITLE_TAGS))
            docs.append(Document(
                id=f"{doc_prefix}-{no or len(docs)}",
                source_type=source_type,
                title=f"{name} {no} ({title})".strip() if title else f"{name} {no}".strip(),
                text=text,
                url=url,
                article_no=no,
                reliability="A",
                verified=True,
            ))
    return docs


class LawAPIClient:
    def __init__(self, oc: str | None = None, timeout: float = 20.0):
        self.oc = oc or os.environ.get("LAW_OC", "")
        if not self.oc:
            raise RuntimeError("LAW_OC(국가법령정보센터 인증키)가 설정되지 않았습니다.")
        self.http = httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, target: str, query: str) -> list[dict]:
        r = self.http.get(f"{BASE}/lawSearch.do",
                          params={"OC": self.oc, "target": target, "type": "XML", "query": query})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        out = []
        for item in root.iter("law"):
            out.append({c.tag: _text(c) for c in item})
        return out

    def fetch(self, target: str, mst: str, *, doc_prefix: str) -> list[Document]:
        params = {"OC": self.oc, "target": target, "type": "XML", "MST": mst}
        r = self.http.get(f"{BASE}/lawService.do", params=params)
        r.raise_for_status()
        url = f"https://www.law.go.kr/{'ordinInfoP.do?ordinSeq' if target == 'ordin' else 'lsInfoP.do?lsiSeq'}={mst}"
        return parse_law_xml(r.text, source_type="ordinance" if target == "ordin" else "law",
                             url=url, doc_prefix=doc_prefix)

    def fetch_by_name(self, target: str, name: str, *, doc_prefix: str) -> list[Document]:
        hits = self.search(target, name)
        key = "자치법규일련번호" if target == "ordin" else "법령일련번호"
        name_key = "자치법규명" if target == "ordin" else "법령명한글"
        exact = [h for h in hits if h.get(name_key, "").replace(" ", "") == name.replace(" ", "")]
        pick = (exact or hits)[:1]
        if not pick or not pick[0].get(key):
            return []
        return self.fetch(target, pick[0][key], doc_prefix=doc_prefix)
