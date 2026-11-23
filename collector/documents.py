"""첨부파일·로컬 파일에서 본문 텍스트를 뽑는다.

교육부 보도자료처럼 웹페이지 본문은 비어 있고 내용이 첨부 한글(.hwpx)·PDF에만 있는
경우가 많아, 파일 형식별로 텍스트를 꺼내는 함수를 모아 둔다.

지원: .hwpx(한글 2014+ 개방형), .pdf, .docx, .txt/.md, .html
미지원: .hwp(구형 바이너리). 한글에서 '다른 이름으로 저장 → HWPX'로 바꿔 넣으면 된다.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SUPPORTED = (".hwpx", ".pdf", ".docx", ".txt", ".md", ".html", ".htm")


class UnsupportedFile(ValueError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(lines: list[str]) -> str:
    out = []
    for ln in lines:
        ln = re.sub(r"[ \t 　]+", " ", ln).strip()
        if ln:
            out.append(ln)
    return "\n".join(out)


def _hwpx_paragraphs(el: ET.Element, out: list[str]) -> None:
    """<hp:p> 하나를 한 줄로. 표 안의 문단(<hp:p> 안의 <hp:p>)은 따로 한 줄씩 꺼낸다."""
    buf: list[str] = []

    def walk(node: ET.Element) -> None:
        for ch in node:
            name = _local(ch.tag)
            if name == "p":
                _hwpx_paragraphs(ch, out)
            elif name == "t":
                buf.append("".join(ch.itertext()))
            else:
                walk(ch)

    walk(el)
    if buf:
        out.append("".join(buf))


def hwpx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted((n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
                       key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
        if not names:
            raise UnsupportedFile("HWPX 안에 Contents/section*.xml 이 없습니다.")
        lines: list[str] = []
        for n in names:
            root = ET.fromstring(z.read(n))
            for el in root:  # <hs:sec> 바로 아래가 문단(<hp:p>)
                if _local(el.tag) == "p":
                    _hwpx_paragraphs(el, lines)
    return _clean(lines)


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return _clean([(page.extract_text() or "") for page in reader.pages])


def docx_text(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    lines = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells))
    return _clean(lines)


def html_text(data: bytes) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    return _clean(soup.get_text("\n").splitlines())


def sniff_ext(data: bytes, filename: str = "") -> str:
    ext = Path(filename).suffix.lower()
    if ext in SUPPORTED:
        return ext
    if ext == ".hwp" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".hwp"
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
        if any(n.startswith("Contents/section") for n in names):
            return ".hwpx"
        if "word/document.xml" in names:
            return ".docx"
    return ext


def extract_text(data: bytes, filename: str = "") -> str:
    ext = sniff_ext(data, filename)
    if ext == ".hwpx":
        return hwpx_text(data)
    if ext == ".pdf":
        return pdf_text(data)
    if ext == ".docx":
        return docx_text(data)
    if ext in (".html", ".htm"):
        return html_text(data)
    if ext in (".txt", ".md"):
        return _clean(data.decode("utf-8", errors="replace").splitlines())
    if ext == ".hwp":
        raise UnsupportedFile("구형 .hwp 는 읽지 못합니다. 한글에서 HWPX나 PDF로 저장해 주세요.")
    raise UnsupportedFile(f"지원하지 않는 파일 형식입니다: {filename or ext or '알 수 없음'}")


def filename_from_headers(headers, fallback: str = "") -> str:
    """Content-Disposition 의 filename(퍼센트 인코딩 포함)을 꺼낸다."""
    from urllib.parse import unquote_plus
    cd = headers.get("content-disposition", "") if headers else ""
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)"?', cd, re.I)
    if not m:
        return fallback
    raw = m.group(1).strip()
    try:
        name = unquote_plus(raw)
    except Exception:
        name = raw
    # 일부 서버는 UTF-8 바이트를 latin-1 로 보낸다
    try:
        name = name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return name
