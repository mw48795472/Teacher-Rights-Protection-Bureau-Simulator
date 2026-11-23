import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import i18n  # noqa: E402


def test_translate_many_batches_and_caches():
    calls = []

    def handler(req):
        import json
        body = json.loads(req.content)
        calls.append(body)
        return httpx.Response(200, json={"data": {"translations": [{"translatedText": f"EN({q})"} for q in body["q"]]}})

    c = httpx.Client(transport=httpx.MockTransport(handler))
    i18n._cache.clear()
    out = i18n.translate_many(["안녕", "<b>굵게</b>"], key="k", client=c)
    assert out == ["EN(안녕)", "EN(<b>굵게</b>)"]
    assert {b["format"] for b in calls} == {"text", "html"}
    i18n.translate_many(["안녕"], key="k", client=c)
    assert len(calls) == 2  # 캐시 사용


def test_failure_returns_original_without_key_leak():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    i18n._cache.clear()
    assert i18n.translate_many(["실패"], key="secret", client=c) == ["실패"]
    assert "secret" not in i18n._failed["reason"]
