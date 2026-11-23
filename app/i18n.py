"""다국어(한국어/English) 모드.

사이드바에서 English를 고르면 화면에 나가는 한국어 문자열을 Google Cloud Translation API(v2)로
번역해 보여 준다. 각 페이지 코드는 그대로 두고, Streamlit의 텍스트 출력 함수를 감싸서 처리한다.

- 키: GOOGLE_TRANSLATE_API_KEY (.env 또는 Streamlit Secrets)
- 같은 문장은 한 번만 번역하고 프로세스가 살아 있는 동안 메모리에 캐시한다.
- 키가 없거나 번역이 실패하면 원문(한국어)을 그대로 보여 준다.
- 표·차트 안의 글자(열 이름, 축 제목)는 번역하지 않는다.
"""
from __future__ import annotations

import functools
import os
import re

import httpx
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

URL = "https://translation.googleapis.com/language/translate/v2"
HANGUL = re.compile(r"[가-힣]")
LANGS = {"한국어": "ko", "English": "en"}
_cache: dict[tuple[str, str], str] = {}
_failed = {"reason": ""}

# 첫 번째 인자(본문 또는 라벨)를 번역할 함수들
TEXT_FUNCS = ["title", "header", "subheader", "markdown", "caption", "text", "info", "success", "warning",
              "error", "expander", "button", "link_button", "download_button", "selectbox", "multiselect",
              "slider", "radio", "toggle", "checkbox", "number_input", "text_input", "file_uploader",
              "metric", "status", "spinner"]


def api_key() -> str | None:
    return os.environ.get("GOOGLE_TRANSLATE_API_KEY") or None


def lang() -> str:
    try:
        return st.session_state.get("ui_lang", "ko")
    except Exception:
        return "ko"


def translate_many(texts: list[str], target: str = "en", key: str | None = None,
                   client: httpx.Client | None = None) -> list[str]:
    """한 번의 요청으로 여러 문장을 번역. HTML이 섞인 문장은 html 형식으로 보내 태그를 보존한다."""
    key = key or api_key()
    if not key or not texts:
        return texts
    out = list(texts)
    todo = [i for i, t in enumerate(texts) if (t, target) not in _cache]
    groups = {"html": [i for i in todo if "<" in texts[i]], "text": [i for i in todo if "<" not in texts[i]]}
    own = client is None
    client = client or httpx.Client(timeout=15)
    try:
        for fmt, idx in groups.items():
            for s in range(0, len(idx), 100):   # API 한 번에 최대 128개
                chunk = idx[s:s + 100]
                try:
                    r = client.post(URL, params={"key": key}, json={
                        "q": [texts[i] for i in chunk], "source": "ko", "target": target, "format": fmt})
                    r.raise_for_status()
                    got = [t["translatedText"] for t in r.json()["data"]["translations"]]
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    _failed["reason"] = type(e).__name__  # 키가 든 URL은 남기지 않는다
                    return [_cache.get((t, target), t) for t in texts]
                for i, tr in zip(chunk, got):
                    if fmt == "text":
                        import html
                        tr = html.unescape(tr)
                    _cache[(texts[i], target)] = tr
    finally:
        if own:
            client.close()
    return [_cache.get((t, target), t) for t in out]


def tr(text):
    """English 모드일 때 한국어가 든 문자열만 번역."""
    if lang() == "ko" or not isinstance(text, str) or not HANGUL.search(text) or not api_key():
        return text
    return translate_many([text], lang())[0]


def _wrap(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if lang() != "ko":
            # 메서드(self, body, ...) / 모듈 함수(body, ...) 모두 첫 문자열 인자를 번역
            args = list(args)
            pos = 1 if args and isinstance(args[0], DeltaGenerator) else 0
            if len(args) > pos and isinstance(args[pos], str):
                args[pos] = tr(args[pos])
            for k in ("label", "body", "help"):
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
            if "format_func" in kwargs and callable(kwargs["format_func"]):
                f = kwargs["format_func"]
                kwargs["format_func"] = lambda x, f=f: tr(f(x))
        return fn(*args, **kwargs)
    inner._i18n = True
    return inner


def _tabs(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if lang() != "ko":
            args = list(args)
            pos = 1 if args and isinstance(args[0], DeltaGenerator) else 0
            if len(args) > pos:
                args[pos] = [tr(t) for t in args[pos]]
        return fn(*args, **kwargs)
    inner._i18n = True
    return inner


def selector():
    """사이드바 언어 선택. 라벨은 번역하지 않도록 원본 함수로 그린다."""
    radio = getattr(DeltaGenerator.radio, "__wrapped__", DeltaGenerator.radio)
    choice = radio(st.sidebar, "언어 / Language", list(LANGS), horizontal=True, key="ui_lang_label",
                   index=list(LANGS.values()).index(lang()))
    st.session_state["ui_lang"] = LANGS[choice]
    if LANGS[choice] != "ko" and not api_key():
        cap = getattr(DeltaGenerator.caption, "__wrapped__", DeltaGenerator.caption)
        cap(st.sidebar, "GOOGLE_TRANSLATE_API_KEY가 없어 한국어로 표시합니다. "
                        "(Add GOOGLE_TRANSLATE_API_KEY to translate.)")
    elif _failed["reason"]:
        cap = getattr(DeltaGenerator.caption, "__wrapped__", DeltaGenerator.caption)
        cap(st.sidebar, f"Translation failed ({_failed['reason']}); showing Korean.")


def install():
    if getattr(DeltaGenerator.markdown, "_i18n", False):
        return
    for name in TEXT_FUNCS:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap(getattr(DeltaGenerator, name)))
        if hasattr(st, name):
            setattr(st, name, _wrap(getattr(st, name)) if name != "spinner" else _wrap(getattr(st, name)))
    DeltaGenerator.tabs = _tabs(DeltaGenerator.tabs)
    st.tabs = _tabs(st.tabs)
    # 페이지마다 set_page_config 직후 언어 선택을 그린다
    orig = st.set_page_config

    @functools.wraps(orig)
    def page_config(*a, **k):
        r = orig(*a, **k)
        selector()
        return r
    st.set_page_config = page_config
