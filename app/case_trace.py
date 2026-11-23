"""시뮬레이션 페이지의 '사안 추적' 보기: 시나리오 사안 1건이 구조마다 누구를 거쳐 처리되는지."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from common import data_label, freeze, mark_virtual, retriever, scenario_kind, scenarios, simulate, structures
from sim.explain import narrate_case


def render(days: int, rate: float, seed: int, capacity: int, source: str):
    st.caption("보는 것: 분업과 조정(Gulick·Thompson). 같은 사안이 구조에 따라 누구를 거치고, 교사가 몇 번 다시 진술하는지. "
               "시나리오 사안 1건을 사이드바 설정(기간·하루 사안 수·시드·위원회 정원·사안 생성)의 평소 업무량 속에 넣습니다.")
    S = structures()
    names = {k: s["name"] for k, s in S.items()}
    sc = scenarios()
    pick = st.selectbox("시나리오", range(len(sc)), format_func=lambda i: sc[i]["name"], key="trace_pick")
    spec = sc[pick]
    st.info(spec.get("description", ""))
    data_label("scenario", scenario_kind(spec) + " 경과일·주체·행동 기록은 가상 데이터입니다.")
    c1, c2, c3 = st.columns(3)
    left = c1.selectbox("왼쪽 구조", list(S), index=0, format_func=names.get, key="trace_left")
    right = c2.selectbox("오른쪽 구조", list(S), index=min(2, len(S) - 1), format_func=names.get, key="trace_right")
    inject_day = c3.slider("투입 시점 (근무일)", 0, max(0, min(50, days - 1)), min(10, days - 1), key="trace_day")

    docs = {d.id: d for d in retriever().docs}
    scenario = ((freeze(spec), float(inject_day)),)

    def show(col, key):
        _, traces = simulate(key, days, rate, seed, None, 1.0, (), scenario, capacity, source)
        trace = traces.get(spec["name"], [])
        with col:
            st.subheader(names[key])
            if not trace:
                st.warning("기간 안에 종결되지 않았습니다.")
                return
            t0 = trace[0]["day"]
            rows = [{**e, "경과일": round(e["day"] - t0, 2),
                     "근거": docs[e["cite"]].title if e["cite"] in docs else ""} for e in trace]
            d = pd.DataFrame(rows)
            st.metric("종결까지 (가상)", f"{d['경과일'].iloc[-1]:.1f} 근무일")
            fig = px.scatter(d, x="경과일", y="actor", hover_data=["action", "근거"], height=360)
            fig.update_traces(marker_size=12)
            fig.update_layout(yaxis_title="", xaxis_title="경과일 (근무일)")
            st.plotly_chart(mark_virtual(fig, "가상 시나리오 · 시뮬레이션 결과"), width="stretch", key=f"tl-{key}")
            st.dataframe(d[["경과일", "actor", "action", "근거"]].rename(columns={"actor": "주체", "action": "행동"}),
                         width="stretch", hide_index=True)
            if st.button("Claude로 이야기 풀기", key=f"nar-{key}"):
                with st.spinner("작성 중..."):
                    text, used = narrate_case(trace, spec["name"], names[key], retriever())
                st.markdown(text if used else "Claude 키가 없어 이야기 풀기를 쓸 수 없습니다.")

    a, b = st.columns(2)
    show(a, left)
    show(b, right)
