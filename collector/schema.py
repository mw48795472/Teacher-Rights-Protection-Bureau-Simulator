"""수집 문서 공통 스키마."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Document:
    id: str
    source_type: str          # ordinance | law | policy | news | foreign_policy | theory
    title: str
    text: str
    url: str = ""
    article_no: str = ""
    reliability: str = "C"    # A 공식, B 학술, C 언론, D 참고
    verified: bool = False    # 원문에서 직접 수집했으면 True
    meta: dict = field(default_factory=dict)

    @property
    def has_link(self) -> bool:
        return str(self.url).startswith("http")

    @property
    def needs_check(self) -> bool:
        """원문을 수집하지도 않았고 원문 링크도 없는 팀 요약만 '원문 확인 필요'."""
        return not self.verified and not self.has_link

    @property
    def source_tag(self) -> str:
        """인용 옆에 붙는 짧은 표시. 원문 수집=없음, 링크 있는 요약='요약·원문 링크', 그 밖='팀 요약, 원문 확인 필요'."""
        if self.verified:
            return ""
        return "요약·원문 링크" if self.has_link else "팀 요약, 원문 확인 필요"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
