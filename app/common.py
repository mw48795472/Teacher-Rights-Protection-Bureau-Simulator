"""대시보드 공통: 경로, .env, 캐시된 검색기·시뮬레이션."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from collector.pipeline import load_corpus  # noqa: E402
from geo.gyeonggi import load_schools, office_weights  # noqa: E402
from geo.neis import NeisError, fetch_schools, neis_key, reconcile  # noqa: E402
from rag.retriever import Retriever  # noqa: E402
from sim.engine import SimConfig, list_structures, run  # noqa: E402
from sim.metrics import to_frame  # noqa: E402


@st.cache_resource
def retriever() -> Retriever:
    return Retriever(load_corpus())


@st.cache_data
def structures() -> dict:
    return list_structures()


@st.cache_data
def scenarios() -> list[dict]:
    return yaml.safe_load((ROOT / "config" / "scenarios.yaml").read_text(encoding="utf-8"))["scenarios"]


@st.cache_data(show_spinner=False)
def schools() -> pd.DataFrame:
    """경기도 초·중·고 위치 (data/schools). 없으면 빈 표."""
    return load_schools()


@st.cache_data(ttl=86400, show_spinner=False)
def neis_status() -> dict:
    """NEIS 학교기본정보 대조 결과. 키가 없거나 실패하면 이유만 담는다."""
    if not neis_key():
        return {"ok": False, "reason": "NEIS_KEY 없음"}
    if schools().empty:
        return {"ok": False, "reason": "위치 데이터 없음"}
    try:
        merged, rec = reconcile(schools(), fetch_schools(neis_key()))
    except NeisError as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "merged": merged, **rec}


def schools_enriched() -> pd.DataFrame:
    st_ = neis_status()
    return st_["merged"] if st_["ok"] else schools()


def offices() -> tuple:
    """교육지원청별 사안 비중. 실측 교원 수(2025.4.)가 있으면 교원 수, 없으면 학교 수에 비례."""
    from sim.calibration import office_teacher_weights
    return tuple(sorted((office_teacher_weights() or office_weights(schools())).items()))


def simulate(key: str, days: int, rate: float, seed: int, surge_day, surge_mult: float,
             overrides: tuple = (), scenario: tuple = (), capacity: int = 6) -> tuple[pd.DataFrame, dict]:
    """(사안별 결과표, 시나리오 사안의 로그 {label: trace}).
    사안은 교육지원청별 교원 수(없으면 학교 수) 비중대로 각 관할에서 생기고, 그 교육지원청 위원회로 간다."""
    return _simulate(key, days, rate, seed, surge_day, surge_mult, overrides, scenario, offices(), capacity)


@st.cache_data(show_spinner=False)
def _simulate(key, days, rate, seed, surge_day, surge_mult, overrides, scenario, offices_, capacity):
    s = structures()[key]
    cfg = SimConfig(s, days=days, arrivals_per_day=rate, seed=seed, surge_day=surge_day,
                    surge_multiplier=surge_mult, overrides=dict(overrides),
                    offices=dict(offices_), committee_capacity=capacity)
    cases = run(cfg, retriever(), [(_thaw(spec), day) for spec, day in scenario])
    traces = {c.label: c.trace for c in cases if c.label}
    return to_frame(cases, key), traces


def freeze(d: dict) -> tuple:
    return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in d.items()))


def _thaw(t) -> dict:
    d = dict(t)
    if "needs" in d:
        d["needs"] = list(d["needs"])
    return d


PALETTE = ["#8a8f98", "#e8833a", "#2a6fdb", "#2e9e6a", "#a35bd6", "#d64f6b"]


def chart_style() -> dict:
    """구조별 색과 순서를 모든 차트에서 같게 유지한다."""
    shorts = [s.get("short", s["name"]) for s in structures().values()]
    return {"category_orders": {"구조": shorts},
            "color_discrete_map": {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(shorts)}}


def llm_badge():
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        st.sidebar.success("Claude 설명: 켜짐")
    else:
        st.sidebar.info("Claude 설명: 꺼짐 (.env에 ANTHROPIC_API_KEY를 넣으면 켜짐)")
