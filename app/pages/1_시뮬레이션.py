import pandas as pd
import plotly.express as px
import streamlit as st

from common import chart_style, freeze, llm_badge, retriever, simulate, structures
from sim.explain import explain
from sim.metrics import METRICS, summarize

st.set_page_config(page_title="시뮬레이션", page_icon="🏫", layout="wide")
llm_badge()
st.title("시뮬레이션")

S = structures()
names = {k: s["name"] for k, s in S.items()}

with st.sidebar:
    st.header("실험 설정")
    picked = st.multiselect("비교할 구조", list(S), default=list(S), format_func=names.get)
    days = st.slider("기간 (근무일)", 20, 120, 60, 5)
    rate = st.slider("하루 평균 사안 수", 1.0, 8.0, 3.0, 0.5,
                     help="실측: 8.24 실무 투입 후 10.8까지 140건 이상 ≈ 하루 3건 [아시아뉴스통신]")
    seed = st.number_input("난수 시드", 0, 9999, 7)
    st.subheader("① 환경 압력")
    surge = st.checkbox("언론 보도 등으로 사안 급증")
    surge_day = st.slider("급증 시작일", 0, days - 1, 20) if surge else None
    surge_mult = st.slider("급증 배수", 1.5, 4.0, 2.5, 0.5) if surge else 1.0
    st.subheader("통합 구조(B·C) 공통 조건 덮어쓰기")
    use_over = st.checkbox("조건을 직접 조정")
    over = {}
    if use_over:
        over["linkage_procedure"] = st.toggle("조건① 연계절차 (조례 제17조)", True)
        over["nonregular_availability"] = st.slider("조건② 비상근 즉시 응답 비율", 0.05, 1.0, 0.25, 0.05)
        over["regular_officers"] = st.slider("조건② 상근 전담관 수", 5, 60, 20, 5)
        over["manual"] = st.toggle("조건③ 업무매뉴얼 (조례 제25조)", True)

if not picked:
    st.info("비교할 구조를 하나 이상 고르세요.")
    st.stop()

frames = []
with st.spinner("시뮬레이션 실행 중..."):
    for k in picked:
        o = freeze(over) if (use_over and S[k]["kind"] == "integrated") else ()
        df, _ = simulate(k, days, rate, int(seed), surge_day, surge_mult, o)
        frames.append(df)
df = pd.concat(frames, ignore_index=True)
short = {k: s.get("short", s["name"]) for k, s in S.items()}
df["구조"] = df["structure"].map(short)
CS = chart_style()
summary = summarize(df, "structure")

st.subheader("사안당 평균 지표")
show = summary.rename(index=names, columns={k: v[0] for k, v in METRICS.items()} | {"cases": "처리 사안 수"})
st.dataframe(show, width="stretch")
with st.expander("지표와 이론의 연결"):
    st.table(pd.DataFrame([{"지표": v[0], "보는 것": v[1]} for v in METRICS.values()]))

c1, c2 = st.columns(2)
with c1:
    fig = px.box(df, x="구조", y="closure_days", color="구조", points=False, title="종결까지 걸린 기간 (근무일)",
                 labels={"closure_days": "근무일"}, **CS)
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width="stretch")
with c2:
    m = summary[["contacts", "repeats", "coordination"]].rename(index=short).reset_index(names="구조")
    m = m.melt(id_vars="구조", var_name="지표", value_name="사안당 평균")
    m["지표"] = m["지표"].map(lambda k: METRICS[k][0])
    fig = px.bar(m, x="지표", y="사안당 평균", color="구조", barmode="group",
                 title="조정 부담은 누가 지는가: 교사(접촉·진술) vs 조직(조정 메시지)", **CS)
    st.plotly_chart(fig, width="stretch")

st.subheader("이론별 분석: 사안 특성에 따라 구조 효과가 달라지는가")
axis = st.radio("나누는 기준", ["perrow", "interdependence"], horizontal=True,
                format_func={"perrow": "Perrow 조직기술 유형", "interdependence": "Thompson 상호의존 유형"}.get)
metric = st.selectbox("지표", list(METRICS), index=1, format_func=lambda k: METRICS[k][0])
g = df.groupby([axis, "구조"])[metric].mean().reset_index()
st.plotly_chart(px.bar(g, x=axis, y=metric, color="구조", barmode="group",
                       labels={metric: METRICS[metric][0], axis: ""}, **CS), width="stretch")

if surge:
    st.subheader("① 환경 압력: 날짜별 종결 기간")
    df["접수일"] = df["arrival_day"].astype(int)
    daily = df.groupby(["접수일", "구조"])["closure_days"].mean().reset_index()
    fig = px.line(daily, x="접수일", y="closure_days", color="구조",
                  labels={"closure_days": "종결까지 (근무일)"}, **CS)
    fig.add_vrect(x0=surge_day, x1=surge_day + 7, fillcolor="gray", opacity=0.15, line_width=0)
    st.plotly_chart(fig, width="stretch")
    st.caption("급증 구간에 접수된 사안일수록 오래 걸리면 구조가 환경 변화를 흡수하지 못한다는 뜻입니다.")

st.subheader("결과 설명")
base = st.selectbox("기준 구조", picked, index=0, format_func=names.get)
target = st.selectbox("비교 구조", picked, index=min(len(picked) - 1, 2), format_func=names.get)
if st.button("설명 생성", type="primary", disabled=base == target):
    ctx = f"기간 {days}일, 하루 평균 {rate}건" + (f", {surge_day}일차부터 {surge_mult}배 급증" if surge else "")
    if use_over:
        ctx += f", 통합 구조 조건 덮어쓰기: {over}"
    with st.spinner("설명 작성 중..."):
        text, hits, used = explain(summary.rename(index=names), names[base], names[target], retriever(), ctx)
    st.markdown(text)
    with st.expander(f"근거 자료 {len(hits)}개" + (" (Claude가 인용)" if used else "")):
        for i, h in enumerate(hits, 1):
            st.markdown(f"**[{i}]** {h.citation}  \n{h.doc.text}")
