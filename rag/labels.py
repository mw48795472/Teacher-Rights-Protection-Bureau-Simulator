"""근거 자료 출처 표시. Document 의 메서드 대신 함수로 둔다.

배포 앱은 지식베이스(Document 객체)를 캐시에 오래 들고 있어서, 새 코드가 Document 에 속성을 더해도
캐시 안의 옛 객체에는 없다(AttributeError). 함수는 속성을 getattr 로 읽어 옛 객체에도 통한다.
"""
from __future__ import annotations


def has_link(doc) -> bool:
    return str(getattr(doc, "url", "") or "").startswith("http")


def source_tag(doc) -> str:
    """원문 수집 = '' · 원문 링크가 있는 요약 = '요약·원문 링크' · 그 밖 = '팀 요약, 원문 확인 필요'."""
    if getattr(doc, "verified", False):
        return ""
    return "요약·원문 링크" if has_link(doc) else "팀 요약, 원문 확인 필요"


def needs_check(doc) -> bool:
    """원문도 링크도 없는 팀 요약만 '원문 확인 필요'."""
    return not getattr(doc, "verified", False) and not has_link(doc)


def tag_suffix(doc, sep: str = ", ") -> str:
    t = source_tag(doc)
    return f"{sep}{t}" if t else ""
