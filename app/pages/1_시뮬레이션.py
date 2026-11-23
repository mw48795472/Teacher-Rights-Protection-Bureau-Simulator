import pandas as pd
import plotly.express as px
import streamlit as st

import plotly.graph_objects as go

from common import chart_style, freeze, llm_badge, retriever, schools_enriched, simulate, structures
from geo.gyeonggi import OFFICES, hierarchy
from sim import insights
from sim.explain import explain
from sim.metrics import METRICS, summarize

st.set_page_config(page_title="시뮬레이션", page_icon="🏫", layout="wide")
llm_badge()
st.title("시뮬레이션")
st.caption("검증하는 가설: H1 통합 장치(Lawrence & Lorsch·Gulick) · H2 사안 유형(Thompson·Perrow) · "
           "H3 환경 압력(Burns & Stalker) · H4 제도화(조례) · H5 인력 안정성(Van de Ven·Woodward). Home의 '가설과 검증' 참고.")


def analysis(lines: list[str], title: str = "분석"):
    if lines:
        with st.container(border=True):
            st.markdown(f"**📊 {title}**")
            st.markdown("\n".join(f"- {x}" for x in lines))

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
    st.subheader("② 관할 위원회")
    cap = st.slider("위원회 1회 심의 정원 (가정)", 1, 20, 6,
                    help="교육지원청마다 위원회가 따로 열리고, 정원을 넘는 사안은 다음 회의로 밀립니다.")
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
        df, _ = simulate(k, days, rate, int(seed), surge_day, surge_mult, o, capacity=cap)
        frames.append(df)
df = pd.concat(frames, ignore_index=True)
short = {k: s.get("short", s["name"]) for k, s in S.items()}
df["구조"] = df["structure"].map(short)
CS = chart_style()
summary = summarize(df, "structure")

st.subheader("사안당 평균 지표")
show = summary.rename(index=names, columns={k: v[0] for k, v in METRICS.items()} | {"cases": "처리 사안 수"})
st.dataframe(show, width="stretch")
analysis(insights.overview(summary, short), "핵심 결과")
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

st.subheader("관할 교육지원청별 결과")
st.caption("경기도 초·중·고 2,576곳의 학교 수 비중대로 사안이 생기고, 그 학교 관할 교육지원청의 "
           "지역교권보호위원회로 넘어갑니다. 원 크기는 사안 수, 색은 위원회 심의까지 평균 대기입니다.")
sch = schools_enriched()
odf = pd.DataFrame([{"office": o.key, "name": o.name, "lat": o.lat, "lon": o.lon} for o in OFFICES])
wc = df[df["committee_wait_days"] > 0]
per = (df.groupby(["구조", "office"]).agg(사안=("id", "size"), 종결일=("closure_days", "mean"))
       .join(wc.groupby(["구조", "office"]).agg(위원회_대기일=("committee_wait_days", "mean")))
       .reset_index().fillna(0).merge(odf, on="office"))
m1, m2 = st.columns([3, 2])
with m1:
    which = st.radio("구조", picked, horizontal=True, format_func=short.get, key="map_structure")
    mp = per[per["구조"] == short[which]]
    MAP = dict(map_style="carto-positron", zoom=7.9, center={"lat": 37.55, "lon": 127.1})
    fig = go.Figure()
    if not sch.empty and st.toggle("학교 표시", True):
        hover = sch["name"] + " (" + sch["level"] + ")"
        if "phone" in sch:
            hover = hover + "<br>" + sch["phone"].fillna("")
        fig.add_trace(go.Scattermap(lat=sch["lat"], lon=sch["lon"], mode="markers", name="학교",
                                    marker=dict(size=4, color="#2a6fdb", opacity=0.35),
                                    hovertext=hover, hoverinfo="text"))
    size = 12 + 38 * mp["사안"] / max(1, mp["사안"].max())
    fig.add_trace(go.Scattermap(
        lat=mp["lat"], lon=mp["lon"], mode="markers+text", name="교육지원청", text=mp["office"],
        textposition="top center",
        marker=dict(size=size, color=mp["위원회_대기일"], colorscale="OrRd", showscale=True, opacity=0.85,
                    colorbar=dict(title="위원회<br>대기(일)")),
        hovertext=[f"{r.name}<br>사안 {r.사안}건 · 위원회 대기 {r.위원회_대기일:.1f}일 · 종결 {r.종결일:.1f}일"
                   for r in mp.itertuples()], hoverinfo="text"))
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      map=dict(style=MAP["map_style"], zoom=MAP["zoom"], center=MAP["center"]))
    st.plotly_chart(fig, width="stretch")
with m2:
    tbl = per.pivot_table(index="office", columns="구조", values="위원회_대기일").round(1)
    st.markdown("**교육지원청별 위원회 대기 (근무일)**")
    st.dataframe(tbl.sort_values(tbl.columns[0], ascending=False), width="stretch", height=520)
analysis(insights.offices(per, short[which]), f"관할 분석 ({short[which]})")
with st.expander("감독 구조: 교육부 → 경기도교육청 → 교육지원청 → 위원회·학교"):
    h = hierarchy(sch)
    st.plotly_chart(px.sunburst(h, ids="id", parents="parent", names="label", values="value",
                                hover_data={"role": True}, height=560, maxdepth=3), width="stretch")
    st.caption("교육지원청 위치는 시청 부근 대략 위치입니다. 지역교권보호위원회를 교육지원청에 두는 부분은 "
               "교원지위법 원문 확인이 필요합니다.")

st.subheader("이론별 분석: 사안 특성에 따라 구조 효과가 달라지는가")
axis = st.radio("나누는 기준", ["perrow", "interdependence"], horizontal=True,
                format_func={"perrow": "Perrow 조직기술 유형", "interdependence": "Thompson 상호의존 유형"}.get)
metric = st.selectbox("지표", list(METRICS), index=1, format_func=lambda k: METRICS[k][0])
g = df.groupby([axis, "구조"])[metric].mean().reset_index()
st.plotly_chart(px.bar(g, x=axis, y=metric, color="구조", barmode="group",
                       labels={metric: METRICS[metric][0], axis: ""}, **CS), width="stretch")
analysis(insights.by_type(df, axis, metric, METRICS[metric][0]), "유형별 분석")

if surge:
    st.subheader("① 환경 압력: 날짜별 종결 기간")
    df["접수일"] = df["arrival_day"].astype(int)
    daily = df.groupby(["접수일", "구조"])["closure_days"].mean().reset_index()
    fig = px.line(daily, x="접수일", y="closure_days", color="구조",
                  labels={"closure_days": "종결까지 (근무일)"}, **CS)
    fig.add_vrect(x0=surge_day, x1=surge_day + 7, fillcolor="gray", opacity=0.15, line_width=0)
    st.plotly_chart(fig, width="stretch")
    st.caption("급증 구간에 접수된 사안일수록 오래 걸리면 구조가 환경 변화를 흡수하지 못한다는 뜻입니다.")
    analysis(insights.surge(df, surge_day), "환경 압력 분석")

st.subheader("결과 설명 (Claude)")
st.caption("위 분석은 숫자를 규칙으로 읽은 것입니다. 아래 버튼은 Claude가 근거 자료를 인용해 두 구조의 차이를 풀어 씁니다.")
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
