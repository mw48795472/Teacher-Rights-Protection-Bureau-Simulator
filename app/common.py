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
from geo.gyeonggi import load_schools  # noqa: E402
from geo.regions import module as region_module, region_of  # noqa: E402
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
def schools(region: str = "경기") -> pd.DataFrame:
    """지역 초·중·고 위치 (data/schools). 경기 2,576곳, 인천 550곳. 없으면 빈 표."""
    return load_schools() if region == "경기" else region_module(region).load_schools()


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


def schools_enriched(region: str = "경기") -> pd.DataFrame:
    """NEIS 대조는 경기만 한다 (인천은 위치 표준데이터만)."""
    if region != "경기":
        return schools(region)
    st_ = neis_status()
    return st_["merged"] if st_["ok"] else schools()


def offices(region: str = "경기") -> tuple:
    """교육지원청별 사안 비중. 경기는 실측 교원 수(2025.4.)가 있으면 교원 수, 없으면 학교 수. 인천은 학교 수 비례."""
    from sim.calibration import office_teacher_weights
    if region == "경기":
        return tuple(sorted((office_teacher_weights() or region_module("경기").office_weights(schools())).items()))
    return tuple(sorted(region_module(region).office_weights(schools(region)).items()))


def region(key: str) -> str:
    return region_of(structures()[key])


def effective_rate(key: str, rate: float) -> float:
    """화면의 '하루 평균 사안 수'(경기 기준)를 구조의 지역 규모로 바꾼 값. 인천은 2024 교보위 건수 비율(약 0.26배)."""
    from sim.calibration import region_case_scale
    return rate * region_case_scale(region(key))


def simulate(key: str, days: int, rate: float, seed: int, surge_day, surge_mult: float,
             overrides: tuple = (), scenario: tuple = (), capacity: int = 6,
             case_source: str = "assumed") -> tuple[pd.DataFrame, dict]:
    """(사안별 결과표, 시나리오 사안의 로그 {label: trace}).
    사안은 구조가 속한 지역(경기·인천)의 교육지원청 비중대로 각 관할에서 생기고, 그 교육지원청 위원회로 간다.
    인천형은 사안 유입량도 인천 규모(effective_rate)로 줄여 돌린다."""
    r = region(key)
    return _simulate(key, days, effective_rate(key, rate), seed, surge_day, surge_mult, overrides, scenario,
                     offices(r), capacity, case_source)


@st.cache_data(show_spinner=False)
def _simulate(key, days, rate, seed, surge_day, surge_mult, overrides, scenario, offices_, capacity,
              case_source="assumed"):
    s = structures()[key]
    cfg = SimConfig(s, days=days, arrivals_per_day=rate, seed=seed, surge_day=surge_day,
                    surge_multiplier=surge_mult, overrides=dict(overrides),
                    offices=dict(offices_), committee_capacity=capacity, case_source=case_source)
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


# 다국어 모드 (한국어/English). GOOGLE_TRANSLATE_API_KEY가 있으면 사이드바에서 English 선택 시 번역.
import i18n  # noqa: E402

i18n.install()


# ── 데이터 성격 표기: 가상(시뮬레이션·시나리오) vs 실측 ──
DATA_KINDS = {
    "sim": ("orange", "🧪 가상 데이터",
            "시뮬레이션이 만든 합성 사안입니다. 사안 유입량·유형 비율·관할 비중만 실측에 맞췄고, "
            "처리시간·확률·인원 대부분은 팀 가정값입니다. 실제 교권보호단의 운영 통계가 아닙니다."),
    "scenario": ("violet", "🎭 가상 시나리오",
                 "사안 설정은 기사 사실이나 드라마 설정에서 가져왔지만, 처리 과정과 시간은 시뮬레이션이 만든 것입니다."),
    "agent": ("violet", "🎭 가상 시뮬레이션",
              "인물의 행동은 에이전트(또는 오프라인 예시 스크립트)가 지어낸 장면입니다. 법령·조례 판정만 실제 문서를 인용합니다."),
    "real": ("green", "📏 실측 데이터", "공공데이터·공식 통계·법령 원문에서 옮긴 값입니다."),
}


def data_label(kind: str, detail: str = ""):
    """차트·표 위에 데이터 성격 배지와 한 줄 설명을 단다."""
    color, tag, desc = DATA_KINDS[kind]
    st.caption(f":{color}-badge[{tag}] {detail or desc}")


def mark_virtual(fig, text: str = "가상 데이터 · 시뮬레이션 결과"):
    """plotly 그림 오른쪽 위에 가상 데이터 표기를 넣는다 (그림을 따로 저장·공유해도 남도록)."""
    fig.add_annotation(text=f"🧪 {text}", xref="paper", yref="paper", x=1, y=1.0, xanchor="right", yanchor="bottom",
                       showarrow=False, font=dict(size=11, color="#c2410c"),
                       bgcolor="rgba(251,146,60,.12)", bordercolor="rgba(194,65,12,.35)", borderwidth=1, borderpad=3)
    return fig


def scenario_kind(spec: dict) -> str:
    """시나리오 이름으로 사실 기반인지 가상인지 표기 문구."""
    name = spec.get("name", "")
    if "가상" in name:
        return "설정부터 가상인 시나리오입니다. 처리 과정도 시뮬레이션입니다."
    return "사안 설정은 보도된 사실에서 가져왔고, 처리 과정과 시간은 시뮬레이션이 만든 가상 결과입니다."
