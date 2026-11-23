import pandas as pd
import plotly.express as px
import streamlit as st

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다 (common·sim 을 불러오기 전에)

fresh.ensure()
from common import freeze, llm_badge, retriever, scenarios, simulate, structures
from sim.explain import narrate_case

st.set_page_config(page_title="사안 추적", page_icon="🏫", layout="wide")
llm_badge()
st.title("사안 추적")
st.caption("보는 것: 분업과 조정(Gulick·Thompson). 같은 사안이 구조에 따라 누구를 거치고, 교사가 몇 번 다시 진술하는지.")
st.caption("시나리오 사안 1건을 평소 업무량 속에 넣고, 구조마다 누구를 거쳐 처리되는지 비교합니다.")

S = structures()
names = {k: s["name"] for k, s in S.items()}
sc = scenarios()
pick = st.selectbox("시나리오", range(len(sc)), format_func=lambda i: sc[i]["name"])
spec = sc[pick]
st.info(spec.get("description", ""))
c1, c2, c3 = st.columns(3)
left = c1.selectbox("왼쪽 구조", list(S), index=0, format_func=names.get)
right = c2.selectbox("오른쪽 구조", list(S), index=min(2, len(S) - 1), format_func=names.get)
inject_day = c3.slider("투입 시점 (근무일)", 0, 50, 10)

docs = {d.id: d for d in retriever().docs}
scenario = ((freeze(spec), float(inject_day)),)


def show(col, key):
    _, traces = simulate(key, 60, 3.0, 7, None, 1.0, (), scenario)
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
        st.metric("종결까지", f"{d['경과일'].iloc[-1]:.1f} 근무일")
        fig = px.scatter(d, x="경과일", y="actor", hover_data=["action", "근거"], height=360)
        fig.update_traces(marker_size=12)
        fig.update_layout(yaxis_title="", xaxis_title="경과일 (근무일)")
        st.plotly_chart(fig, width="stretch", key=f"tl-{key}")
        st.dataframe(d[["경과일", "actor", "action", "근거"]].rename(columns={"actor": "주체", "action": "행동"}),
                     width="stretch", hide_index=True)
        if st.button("Claude로 이야기 풀기", key=f"nar-{key}"):
            with st.spinner("작성 중..."):
                text, used = narrate_case(trace, spec["name"], names[key], retriever())
            st.markdown(text if used else "Claude 키가 없어 이야기 풀기를 쓸 수 없습니다.")


a, b = st.columns(2)
show(a, left)
show(b, right)
