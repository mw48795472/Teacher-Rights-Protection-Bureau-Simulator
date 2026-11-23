import yaml


def test_data_needs_file():
    d = yaml.safe_load(open("config/data_needs.yaml", encoding="utf-8"))
    for key in ("empirical", "learning"):
        assert d[key]
        for r in d[key]:
            assert {"item", "current", "status", "priority", "why", "need", "how"} <= set(r)
            assert r["status"] in ("실측", "일부", "가정") and r["priority"] in ("상", "중", "하")


def test_every_page_marks_data_kind():
    import glob
    pages = {p: open(p, encoding="utf-8").read() for p in glob.glob("app/pages/*.py")}
    for p, src in pages.items():
        if "근거_자료" in p:
            assert 'data_label("real"' in src
        else:
            assert "data_label(" in src, p
    assert "가상 데이터" in open("app/Home.py", encoding="utf-8").read()
