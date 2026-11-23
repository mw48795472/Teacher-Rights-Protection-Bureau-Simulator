import io
import zipfile

import pytest

from collector import pipeline
from collector.documents import UnsupportedFile, extract_text, filename_from_headers, sniff_ext
from collector.html_page import parse_html
from collector.law_api import parse_admrul_xml, parse_prec_xml, parse_search_xml
from collector.pipeline import load_seed, merge, snapshot_docs
from collector.schema import Document
from collector.sites import (handler_for, parse_goe_list, parse_goe_view, parse_moe_list,
                             parse_moe_view, post_key)

HP = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
SECTION = f"""<?xml version="1.0" encoding="UTF-8"?><hs:sec {HP}>
<hp:p><hp:run><hp:secPr/><hp:t>교사가 안심하고 </hp:t></hp:run><hp:run><hp:t>가르치는 학교</hp:t></hp:run></hp:p>
<hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList>
  <hp:p><hp:run><hp:t>표 안 문단 1</hp:t></hp:run></hp:p>
  <hp:p><hp:run><hp:t>표 안 문단 2</hp:t></hp:run></hp:p>
</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
<hp:p><hp:run><hp:t>◦ 기관 중심 민원 대응</hp:t></hp:run></hp:p>
</hs:sec>"""


def make_hwpx(sections: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        for name, xml in sections.items():
            z.writestr(name, xml)
    return buf.getvalue()


def test_hwpx_text_keeps_paragraphs_and_table_cells_in_order():
    data = make_hwpx({"Contents/section0.xml": SECTION,
                      "Contents/section1.xml": SECTION.replace("교사가", "둘째 구역")})
    text = extract_text(data, "보도자료.hwpx")
    lines = text.splitlines()
    assert lines[:4] == ["교사가 안심하고 가르치는 학교", "표 안 문단 1", "표 안 문단 2", "◦ 기관 중심 민원 대응"]
    assert lines[4].startswith("둘째 구역")


def test_sniff_by_magic_bytes_and_reject_old_hwp():
    assert sniff_ext(make_hwpx({"Contents/section0.xml": SECTION}), "fileDown.do") == ".hwpx"
    assert sniff_ext(b"%PDF-1.7 ...", "") == ".pdf"
    with pytest.raises(UnsupportedFile):
        extract_text(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 20, "옛날.hwp")


def test_docx_and_pdf_extract(tmp_path):
    import docx
    d = docx.Document()
    d.add_paragraph("교육활동 보호 매뉴얼")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "구분", "내용"
    p = tmp_path / "m.docx"
    d.save(p)
    text = extract_text(p.read_bytes(), "m.docx")
    assert "교육활동 보호 매뉴얼" in text and "구분 | 내용" in text

    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    w.write(buf)
    assert extract_text(buf.getvalue(), "x.pdf") == ""  # 빈 페이지도 예외 없이 처리


def test_filename_from_percent_encoded_header():
    h = {"content-disposition": "attachment;filename=%5B%EA%B5%90%EC%9C%A1%EB%B6%80%5D+%EB%B3%B4%EB%8F%84.hwpx;"}
    assert filename_from_headers(h) == "[교육부] 보도.hwpx"


MOE_VIEW = """<html><head><title>교육부 > 보도자료</title></head><body>
<div id="txt"><section class="news-header"><h3>교사가 안심하고 가르치는 학교를 만들겠습니다.</h3>
<div class="sub"><span class="reg-date">2026-01-22</span></div></section>
<div class="synapWrap"></div><div class="synapTextWrap"><div>최교진 교육부 장관은 말했다.</div></div>
<section class="attachment"><ul>
<li><span>[교육부 01-22(목) 석간보도자료]교사가 안심하고 가르치는 학교를 만들겠습니다.hwpx [ 318.8 KB ]</span>
<div class="view-btns"><a class="btnBorder" href="/boardCnts/fileDown.do?m=020402&amp;s=moe&amp;fileSeq=a6">다운로드</a></div></li>
<li><span>[별첨] 학교민원 대응 및 교육활동 보호 강화 방안 - 복사본.pdf [ 1.5 MB ]</span>
<div class="view-btns"><a class="btnBorder" href="/boardCnts/fileDown.do?m=020402&amp;s=moe&amp;fileSeq=75">다운로드</a></div></li>
</ul></section></div></body></html>"""

MOE_LIST = """<table><tbody>
<tr><td class="no">25</td><td class="title left"><a href="#" onclick="javascript:goView('294', '103356', '0', null, 'W', '1', 'N', '');"
 title="2024학년도 교육활동 침해 실태조사 결과 발표">2024학년도 교육활동 침해 실태조사 결과 발표</a></td>
<td>홍보담당관</td><td>2025-05-13</td><td>28297</td></tr></tbody></table>"""


def test_parse_moe_view_title_date_body_and_attachments():
    v = parse_moe_view(MOE_VIEW, "u")
    assert v["title"] == "교사가 안심하고 가르치는 학교를 만들겠습니다."
    assert v["date"] == "2026-01-22"
    assert "최교진" in v["text"]
    names = [a[0] for a in v["attachments"]]
    assert names[0].endswith(".hwpx") and names[1].startswith("[별첨]") and names[1].endswith(".pdf")
    assert v["attachments"][0][1].startswith("https://www.moe.go.kr/boardCnts/fileDown.do")


def test_parse_moe_list():
    rows = parse_moe_list(MOE_LIST)
    assert rows == [{"title": "2024학년도 교육활동 침해 실태조사 결과 발표", "date": "2025-05-13",
                     "url": "https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=103356&lev=0&m=020402"}]


def test_fetch_moe_post_prefers_full_hwpx_and_adds_attachment_doc(monkeypatch):
    import httpx
    from collector import sites

    hwpx = make_hwpx({"Contents/section0.xml": SECTION})

    def handler(req: httpx.Request):
        if "viewRenew" in req.url.path:
            return httpx.Response(200, text=MOE_VIEW)
        if req.url.params.get("fileSeq") == "a6":
            return httpx.Response(200, content=hwpx)
        return httpx.Response(200, content=b"not a pdf")  # 별첨 PDF 파싱 실패 → 본문은 살아야 함

    c = httpx.Client(transport=httpx.MockTransport(handler))
    docs = sites.fetch_moe_post("https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=105198",
                                http=c)
    assert len(docs) == 1
    assert "표 안 문단 1" in docs[0].text and docs[0].verified
    assert docs[0].meta["attachment_errors"]
    assert docs[0].title.startswith("교육부 보도자료 「교사가")


GOE_LIST = """<ul><li><a href="javascript:" data-id="2378761" title="경기도교육청, ‘교권보호전담관 워크숍’ 개최" class="nttInfoBtn ">
<dl><dt class="lst_tit">경기도교육청, ‘교권보호전담관 워크숍’ 개최</dt><dd class="txt"><strong>등록일: </strong> 2026.10.24
<strong>조회수: </strong> 164</dd></dl></a></li></ul>"""

GOE_VIEW = """<div class="bbs_ViewA"><h3>경기도교육청, ‘교권보호전담관 워크숍’ 개최</h3>
<ul class="bbsV_data"><li>분류 도교육청</li><li>등록일 2026.10.24</li></ul>
<div class="bbsV_cont"><p>◦ 10월 24일 북부권 워크숍 진행</p><p>◦ 실전 시뮬레이션 도입</p></div>
<div class="bbsV_atchmnfl"><a href="/goe/na/ntt/comm/nttFileDownload.do?fileKey=06" class="fileName">워크숍(생활교육과).hwpx&nbsp;</a></div></div>"""


def test_parse_goe_list_and_view():
    rows = parse_goe_list(GOE_LIST)
    assert rows[0]["date"] == "2026-10-24"
    assert rows[0]["url"].endswith("nttSn=2378761")
    d = parse_goe_view(GOE_VIEW, rows[0]["url"])
    assert d.meta["date"] == "2026-10-24" and d.source_type == "policy" and d.reliability == "A"
    assert d.text.splitlines() == ["◦ 10월 24일 북부권 워크숍 진행", "◦ 실전 시뮬레이션 도입"]
    assert d.meta["attachments"] == ["워크숍(생활교육과).hwpx"]


def test_handler_routing_and_post_key():
    assert handler_for("https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=1")
    assert handler_for("https://www.goe.go.kr/goe/na/ntt/selectNttInfo.do?nttSn=1")
    assert handler_for("https://www.kyeongin.com/article/1") is None
    assert post_key("https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=105198") == \
        post_key("https://moe.go.kr/boardCnts/viewRenew.do?lev=0&boardSeq=105198&m=020402&boardID=294")


def test_parse_html_selector_skips_menus():
    html = """<html><body><div class="gnb"><ul><li>교육활동 보호 교육활동 침해행위의 이해 메뉴 메뉴</li></ul></div>
    <div id="cntntsCn"><h4>지역교권보호위원회의 기능</h4><ul><li>교육활동 침해 기준 마련</li></ul></div></body></html>"""
    d = parse_html(html, "u", "A", selector="#cntntsCn", title="안내")
    assert d.title == "안내"
    assert "메뉴" not in d.text and "지역교권보호위원회의 기능" in d.text


ADMRUL_XML = """<AdmRulService><행정규칙기본정보><행정규칙명>교육활동 침해 행위 및 조치 기준에 관한 고시</행정규칙명>
<행정규칙종류>고시</행정규칙종류><발령번호>2024-20</발령번호></행정규칙기본정보>
<조문내용>제1조(목적) 이 고시는 교육활동 침해 행위를 정한다.</조문내용>
<조문내용>제2조(교원의 교육활동 침해 행위) 다음 각 호와 같다.</조문내용>
<조문내용>1. 반복적으로 부당하게 간섭하는 행위</조문내용>
<조문내용>제3조의2(조치) 별표와 같다.</조문내용></AdmRulService>"""


def test_parse_admrul_splits_articles_and_attaches_items():
    docs = parse_admrul_xml(ADMRUL_XML, url="u", doc_prefix="adm0")
    assert [d.article_no for d in docs] == ["제1조", "제2조", "제3조의2"]
    assert "부당하게 간섭" in docs[1].text
    assert docs[1].title == "교육활동 침해 행위 및 조치 기준에 관한 고시 제2조 (교원의 교육활동 침해 행위)"
    assert docs[0].source_type == "admin_rule" and docs[0].meta["kind"] == "고시"


PREC_XML = """<PrecService><판례정보일련번호>1</판례정보일련번호><사건명>아동학대범죄의처벌등에관한특례법위반</사건명>
<사건번호>2023도1234</사건번호><선고일자>20240314</선고일자><법원명>대법원</법원명>
<판시사항>교사의 생활지도가 정서적 학대에 해당하는지</판시사항><판결요지>정당한 생활지도는 학대가 아니다.</판결요지>
<판례내용>""" + "가" * 20000 + """</판례내용></PrecService>"""


def test_parse_prec_truncates_and_formats_title():
    d = parse_prec_xml(PREC_XML, url="u", doc_id="prec-1", max_chars=500)
    assert d.title == "대법원 2024-03-14 선고 2023도1234 아동학대범죄의처벌등에관한특례법위반"
    assert d.text.startswith("[판시사항] 교사의") and d.text.endswith("원문 링크 참고)")
    assert d.source_type == "precedent"


def test_parse_search_xml_item_tags():
    xml = "<AdmRulSearch><admrul><행정규칙일련번호>9</행정규칙일련번호><행정규칙명>고시</행정규칙명></admrul></AdmRulSearch>"
    assert parse_search_xml(xml, "admrul") == [{"행정규칙일련번호": "9", "행정규칙명": "고시"}]
    xml = "<PrecSearch><prec><판례일련번호>5</판례일련번호></prec></PrecSearch>"
    assert parse_search_xml(xml, "prec")[0]["판례일련번호"] == "5"


def _ids(docs):
    return {d.id for d in docs}


def test_merge_replaces_seed_by_url_explicit_id_and_keeps_short_fetches():
    seed = load_seed()
    long = "원문 " * 100
    live = [
        # 시드 moe-0122 와 쿼리 순서만 다른 같은 게시글
        Document("moe-x", "policy", "교육부", long, verified=True, reliability="A",
                 url="https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=105198&lev=0&m=020402"),
        Document("web-y", "policy", "센터", long, verified=True, reliability="A",
                 meta={"replaces": ["goe-committee"]}),
        # 너무 짧게 수집된 기사(자바스크립트 페이지 등)는 시드를 대체하지 않는다
        Document("web-z", "news", "기사", "짧음", verified=True,
                 url="https://www.ajunews.com/view/20260721172724067"),
    ]
    merged = _ids(merge(seed, live))
    assert "moe-0122" not in merged and "goe-committee" not in merged
    assert "aju-0721" in merged
    assert {"th-lawrence", "moe-x", "web-y", "web-z"} <= merged


def test_merge_ignores_discovered_ordinances_for_article_replacement():
    seed = load_seed()
    other = Document("ord9-제6조", "ordinance", "다른 조례 제6조", "원문", article_no="제6조",
                     verified=True, meta={"discovered": True})
    assert "ord-06" in _ids(merge(seed, [other]))
    own = Document("ord0-제6조", "ordinance", "조례 제6조", "원문", article_no="제6조", verified=True)
    assert "ord-06" not in _ids(merge(seed, [own]))


def test_snapshot_excludes_news_and_inbox_and_load_corpus_falls_back(tmp_path, monkeypatch):
    live = [Document("a", "law", "법", "x" * 200, reliability="A", verified=True),
            Document("b", "news", "기사", "x" * 200, reliability="C", verified=True),
            Document("c", "policy", "inbox", "x" * 200, reliability="A", verified=True, meta={"inbox": True}),
            Document("d", "policy", "보도자료", "x" * 200, reliability="A", verified=True,
                     url="https://more.goe.go.kr/eapc/subList/20000000413")]
    snap = snapshot_docs(live)
    assert _ids(snap) == {"a", "d"}

    out, snap_path = tmp_path / "processed.jsonl", tmp_path / "snap.jsonl"
    pipeline.write(snap, snap_path)
    monkeypatch.setattr(pipeline, "OUT", out)
    monkeypatch.setattr(pipeline, "SNAPSHOT", snap_path)
    docs = pipeline.load_corpus(out)
    ids = _ids(docs)
    assert {"a", "d"} <= ids and "goe-committee" not in ids and "th-lawrence" in ids


def test_cli_rejects_unknown_collector():
    with pytest.raises(SystemExit):
        pipeline.main(["--only", "nope"])
