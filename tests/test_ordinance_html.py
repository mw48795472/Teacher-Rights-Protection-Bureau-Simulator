import pytest

from collector import law_api, pipeline
from collector.schema import Document

HTML = """<html><body><script>var x=1;</script>
<div class="toc">제6조(교권보호단의 설치 및 기능)</div>
<div id="conScroll">
<p>제1조(목적) 이 조례는 교권보호전담관 운영에 필요한 사항을 정한다.</p>
<p>제6조(교권보호단의 설치 및 기능) ① 교육감은 교권보호단을 둔다.</p><p>② 교권보호단의 기능은 다음과 같다.</p>
<p>1. 정책 수립</p>
<p>제9조(교권보호전담관) ① 교육감은 교권보호전담관을 둔다.</p>
<p>부칙 &lt;제8957호, 2026. 10. 7.&gt;</p><p>제1조(시행일) 이 조례는 공포한 날부터 시행한다.</p>
</div></body></html>"""


def test_parse_ordinance_html_articles():
    docs = law_api.parse_ordinance_html(HTML, name="경기도교육청 교권보호전담관 운영 조례", mst="2176205", doc_prefix="ord0")
    by = {d.article_no: d for d in docs}
    assert set(by) == {"제1조", "제6조", "제9조"}          # 부칙 제1조(시행일)는 빠진다
    assert by["제6조"].title.endswith("제6조 (교권보호단의 설치 및 기능)")
    assert "1. 정책 수립" in by["제6조"].text and by["제6조"].verified
    assert "ordinSeq=2176205" in by["제6조"].url


def test_html_ordinances_replace_seed_articles():
    seed = [Document(id="ord-06", source_type="ordinance", title="조례 제6조", text="요약", url="", article_no="제6조",
                     reliability="A", verified=False)]
    live = law_api.parse_ordinance_html(HTML, name="조례", mst="1", doc_prefix="ord0")
    out = pipeline.merge(seed, live)
    assert not any(d.id == "ord-06" for d in out)


@pytest.mark.live_ordinance
def test_cached_ordinance_html_uses_cache_on_failure(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("blocked")
    monkeypatch.setattr(law_api, "fetch_ordinance_html", boom)
    assert pipeline.cached_ordinance_html(path=tmp_path / "c.jsonl") == []
