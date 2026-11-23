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


def simulate(key: str, days: int, rate: float, seed: int, surge_day, surge_mult: float,
             overrides: tuple = (), scenario: tuple = ()) -> tuple[pd.DataFrame, dict]:
    """(사안별 결과표, 시나리오 사안의 로그 {label: trace})"""
    return _simulate(key, days, rate, seed, surge_day, surge_mult, overrides, scenario)


@st.cache_data(show_spinner=False)
def _simulate(key, days, rate, seed, surge_day, surge_mult, overrides, scenario):
    s = structures()[key]
    cfg = SimConfig(s, days=days, arrivals_per_day=rate, seed=seed, surge_day=surge_day,
                    surge_multiplier=surge_mult, overrides=dict(overrides))
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
