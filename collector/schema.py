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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
