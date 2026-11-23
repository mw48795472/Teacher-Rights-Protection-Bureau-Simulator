"""국가법령정보센터 Open API(DRF) 수집기.

인증키(OC)는 https://open.law.go.kr 에서 무료로 신청한다. 환경변수 LAW_OC 로 전달.
법률(target=law)과 자치법규(target=ordin)의 XML을 조문 단위 Document 로 바꾼다.
행정규칙(target=admrul: 고시·훈령·예규)과 판례(target=prec)도 같은 키로 받는다.
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


SEARCH_ITEM = {"law": "law", "ordin": "law", "admrul": "admrul", "prec": "prec"}
ARTICLE_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)\s*(?:\(([^)]*)\))?")


def parse_search_xml(xml_text: str, target: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    tag = SEARCH_ITEM.get(target, target)
    items = list(root.iter(tag))
    if not items and tag != "law":  # 응답 태그가 바뀌어도 동작하도록
        items = list(root.iter("law"))
    return [{c.tag: _text(c) for c in item} for item in items]


def parse_admrul_xml(xml_text: str, *, url: str, doc_prefix: str) -> list[Document]:
    """행정규칙(고시·훈령·예규). <조문내용>이 조문마다 반복되며 '제N조(제목) ...'으로 시작한다."""
    root = ET.fromstring(xml_text)
    name = _text(root.find(".//행정규칙명"))
    kind = _text(root.find(".//행정규칙종류"))
    no = _text(root.find(".//발령번호"))
    bodies = [_text(e) for e in root.iter("조문내용") if _text(e)]
    meta = {"admin_rule": name, "kind": kind, "issue_no": no}
    docs: list[Document] = []
    for body in bodies:
        m = ARTICLE_RE.match(body)
        art = re.sub(r"\s+", "", m.group(1)) if m else ""
        title = m.group(2) if m and m.group(2) else ""
        if not art and docs:  # 조 번호 없이 이어지는 문단은 앞 조문에 붙인다
            docs[-1].text += " " + body
            continue
        docs.append(Document(
            id=f"{doc_prefix}-{art or len(docs)}", source_type="admin_rule",
            title=f"{name} {art} ({title})".strip() if title else f"{name} {art}".strip(),
            text=body, url=url, article_no=art, reliability="A", verified=True, meta=dict(meta)))
    if not docs:  # 조문 구조가 없는 고시는 전체를 한 문서로
        full = _text(root.find(".//본문")) or " ".join(_text(e) for e in root if e.tag not in ("행정규칙기본정보",))
        if full.strip():
            docs.append(Document(id=f"{doc_prefix}-0", source_type="admin_rule", title=name, text=full,
                                 url=url, reliability="A", verified=True, meta=meta))
    return docs


PREC_FIELDS = (("판시사항", "판시사항"), ("판결요지", "판결요지"), ("참조조문", "참조조문"),
               ("판례내용", "판례내용"))


def parse_prec_xml(xml_text: str, *, url: str, doc_id: str, max_chars: int = 12000) -> Document | None:
    """판례 하나 → Document. 전문(판례내용)이 매우 길어 max_chars 에서 자른다."""
    root = ET.fromstring(xml_text)
    get = lambda t: _text(root.find(f".//{t}"))  # noqa: E731
    parts = []
    for tag, label in PREC_FIELDS:
        v = get(tag)
        if v:
            parts.append(f"[{label}] {v}")
    text = "\n".join(parts)
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars] + " …(이하 생략, 원문 링크 참고)"
    court, case_no, date, case_name = get("법원명"), get("사건번호"), get("선고일자"), get("사건명")
    if len(date) == 8 and date.isdigit():
        date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    return Document(id=doc_id, source_type="precedent",
                    title=f"{court} {date} 선고 {case_no} {case_name}".strip(),
                    text=text, url=url, reliability="A", verified=True,
                    meta={"court": court, "case_no": case_no, "date": date})


class LawAPIClient:
    def __init__(self, oc: str | None = None, timeout: float = 20.0):
        self.oc = oc or os.environ.get("LAW_OC", "")
        if not self.oc:
            raise RuntimeError("LAW_OC(국가법령정보센터 인증키)가 설정되지 않았습니다.")
        self.http = httpx.Client(timeout=timeout, follow_redirects=True)

    def search(self, target: str, query: str, display: int = 20, **extra) -> list[dict]:
        r = self.http.get(f"{BASE}/lawSearch.do",
                          params={"OC": self.oc, "target": target, "type": "XML", "query": query,
                                  "display": display, **extra})
        r.raise_for_status()
        return parse_search_xml(r.text, target)

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

    # ── 행정규칙 ──
    def fetch_admrul(self, rule_id: str, *, doc_prefix: str) -> list[Document]:
        r = self.http.get(f"{BASE}/lawService.do",
                          params={"OC": self.oc, "target": "admrul", "type": "XML", "ID": rule_id})
        r.raise_for_status()
        url = f"https://www.law.go.kr/admRulInfoP.do?admRulSeq={rule_id}"
        return parse_admrul_xml(r.text, url=url, doc_prefix=doc_prefix)

    def fetch_admrul_by_name(self, name: str, *, doc_prefix: str) -> list[Document]:
        hits = self.search("admrul", name)
        exact = [h for h in hits if h.get("행정규칙명", "").replace(" ", "") == name.replace(" ", "")]
        # 같은 이름이 여러 건이면(연혁) 현행을 우선
        cur = [h for h in exact if h.get("현행연혁구분", "현행") == "현행"] or exact
        pick = (cur or hits)[:1]
        if not pick or not pick[0].get("행정규칙일련번호"):
            return []
        return self.fetch_admrul(pick[0]["행정규칙일련번호"], doc_prefix=doc_prefix)

    # ── 판례 ──
    def search_precedents(self, query: str, *, display: int = 20, search: int = 2) -> list[dict]:
        """search=1 사건명, 2 본문 검색."""
        return self.search("prec", query, display=display, search=search)

    def fetch_precedent(self, prec_id: str) -> Document | None:
        r = self.http.get(f"{BASE}/lawService.do",
                          params={"OC": self.oc, "target": "prec", "type": "XML", "ID": prec_id})
        r.raise_for_status()
        url = f"https://www.law.go.kr/precInfoP.do?precSeq={prec_id}"
        return parse_prec_xml(r.text, url=url, doc_id=f"prec-{prec_id}")

    def search_ordinances(self, query: str, *, must_contain: tuple[str, ...] = (), display: int = 50) -> list[dict]:
        """자치법규를 검색어로 찾아 이름에 must_contain 이 모두 들어간 것만 남긴다."""
        hits = self.search("ordin", query, display=display)
        return [h for h in hits if all(w in h.get("자치법규명", "") for w in must_contain)]
