from types import SimpleNamespace

from rag.answer import extractive
from rag.labels import has_link, needs_check, source_tag, tag_suffix


def test_labels_work_on_old_objects_without_new_attributes():
    old = SimpleNamespace(title="옛 문서", text="본문", reliability="A", url="https://x", verified=False)
    assert has_link(old) and source_tag(old) == "요약·원문 링크" and not needs_check(old)
    bare = SimpleNamespace(title="t", text="b", reliability="C", url="", verified=False)
    assert needs_check(bare) and tag_suffix(bare) == ", 팀 요약, 원문 확인 필요"
    assert tag_suffix(SimpleNamespace(verified=True, url="")) == ""


def test_answer_context_with_old_doc(monkeypatch):
    from rag import answer as ans
    from rag.retriever import Hit
    old = SimpleNamespace(title="옛 문서", text="본문", reliability="A", url="", verified=False, article_no="")
    h = Hit(old, 1.0)
    assert "원문 확인 필요" in h.citation
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "옛 문서" in ans.answer("q", [h])[0] and extractive("q", [h])


def test_fresh_clears_resource_cache():
    src = open("app/fresh.py", encoding="utf-8").read()
    assert "st.cache_resource.clear()" in src
