"""사안별 결과를 표로 만들고 구조별로 요약한다. 지표는 이론 개념과 1:1로 대응한다."""
from __future__ import annotations

import pandas as pd

from .cases import Case
from .engine import HOURS_PER_DAY

METRICS = {
    "first_response_h": ("첫 응답까지 (근무시간)", "신속성: 조정 실패 비용"),
    "closure_days": ("종결까지 (근무일)", "신속성"),
    "process_days": ("처리 기간: 위원회 대기 제외 (근무일)", "구조가 직접 좌우하는 신속성 (위원회 개최 간격의 영향을 뺌)"),
    "contacts": ("교사가 접촉한 기관 수", "통합 (Lawrence & Lorsch)"),
    "repeats": ("같은 내용 반복 진술", "교사 부담, 피해 교원 중심 전달체계"),
    "coordination": ("조정 메시지 수", "조정 비용 (Thompson)"),
    "duplicates": ("업무 중복 건수", "역할 구분 (조례 제17조)"),
    "handoffs": ("담당자 공백·인수인계", "전담 인력 안정성"),
    "misroutes": ("창구 착오", "공식화 (조례 제25조)"),
}


def to_frame(cases: list[Case], structure: str) -> pd.DataFrame:
    rows = []
    for c in cases:
        if c.closed is None:
            continue
        rows.append({
            "structure": structure, "id": c.id, "office": c.office,
            "committee_wait_days": c.committee_wait / HOURS_PER_DAY, "label": c.label, "type": c.type,
            "severity": c.severity, "perrow": c.perrow, "interdependence": c.interdependence,
            "n_needs": len(c.needs), "analyzable": c.analyzable, "variety_high": c.variety_high,
            "committee": c.committee, "reworks": c.reworks, "needs": "·".join(c.needs),
            "actor": c.actor, "level": c.level, "recognized": c.recognized,
            "process_days": (c.closed - c.arrival - c.committee_wait) / HOURS_PER_DAY,
            "arrival_day": c.arrival / HOURS_PER_DAY,
            "first_response_h": (c.first_response or c.arrival) - c.arrival,
            "closure_days": (c.closed - c.arrival) / HOURS_PER_DAY,
            "contacts": c.contacts, "repeats": c.repeats, "coordination": c.coordination,
            "duplicates": c.duplicates, "handoffs": c.handoffs, "misroutes": c.misroutes,
            "guard_blocks": c.guard_blocks, "witnesses": c.witnesses, "mediation": c.mediation,
        })
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, by: list[str] | str = "structure") -> pd.DataFrame:
    cols = list(METRICS)
    g = df.groupby(by)[cols].mean().round(2)
    g["cases"] = df.groupby(by).size()
    return g
