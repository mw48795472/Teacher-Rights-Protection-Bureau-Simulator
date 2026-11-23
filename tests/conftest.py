import pytest


@pytest.fixture(autouse=True)
def _no_live_ordinance_html(monkeypatch, request):
    """테스트에서는 국가법령정보센터 화면을 부르지 않는다 (그 기능을 시험하는 테스트만 예외)."""
    if "live_ordinance" in request.keywords:
        return
    from collector import pipeline
    monkeypatch.setattr(pipeline, "cached_ordinance_html", lambda *a, **k: [])


def pytest_configure(config):
    config.addinivalue_line("markers", "live_ordinance: 조례 원문 화면 수집 함수를 직접 시험")
