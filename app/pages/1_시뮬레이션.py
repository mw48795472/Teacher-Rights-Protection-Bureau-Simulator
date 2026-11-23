import pandas as pd
import plotly.express as px
import streamlit as st

import plotly.graph_objects as go

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다 (common·sim 을 불러오기 전에)

fresh.ensure()
from common import chart_style, freeze, llm_badge, retriever, schools_enriched, simulate, structures
from geo.gyeonggi import OFFICES, hierarchy
from sim import insights
from sim import typeffects as TE
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
st.caption("H2 (Thompson·Perrow): 필요한 지원이 여럿 얽히고 해결 절차가 불명확한 사안일수록 통합 구조의 효과가 커지는가. "
           "모든 구조에 같은 사안이 똑같이 들어가므로, 사안 하나하나를 짝지어 '구조를 바꾸면 이 사안이 며칠 줄어드는가'를 봅니다.")
t1, t2, t3 = st.columns([2, 2, 3])
axis = t1.radio("나누는 기준", list(TE.AXES), index=1, format_func=TE.AXES.get, key="th_axis")
mkeys = list(METRICS)
metric = t2.selectbox("지표", mkeys, index=mkeys.index("process_days"), format_func=lambda k: METRICS[k][0],
                      key="th_metric", help="기본값은 위원회 대기를 뺀 처리 기간입니다. '종결까지'를 고르면 위원회 개최 "
                      "간격 차이가 위원회를 거치는 사안(지원 3개 이상)에만 얹혀 효과가 부풀려집니다.")
mlabel = METRICS[metric][0]
unit = "일" if metric.endswith("_days") else "h" if metric.endswith("_h") else ""
pair_ok = len(picked) >= 2
if pair_ok:
    base_k = t3.selectbox("짝 비교: 기준 구조", picked, index=0, format_func=short.get, key="th_base")
    rest = [k for k in picked if k != base_k]
    target_k = t3.selectbox("짝 비교: 비교 구조", rest, index=rest.index("B_gyeonggi") if "B_gyeonggi" in rest else 0,
                            format_func=short.get, key="th_target")
    pr = TE.paired(df, metric, base_k, target_k)
    reg = TE.regression(pr)
order = {axis: TE.ORDER[axis]} if axis in TE.ORDER else {}
axis_label = TE.AXES[axis]
ANL = {True: "분석가능성 높음", False: "분석가능성 낮음"}

tabs = st.tabs(["① 유형별 평균", "② 사안별 산점도", "③ 분포", "④ 구조 격차 (짝 비교)", "⑤ 통제 회귀"])
with tabs[0]:
    cst = TE.cells(df, axis, metric)
    fig = px.bar(cst, x=axis, y="mean", color="구조", barmode="group", error_y="ci", hover_data={"n": True, "ci": ":.2f"},
                 labels={"mean": mlabel, axis: axis_label}, **(CS | {"category_orders": CS["category_orders"] | order}))
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    st.caption("막대는 평균, 오차 막대는 95% 신뢰구간입니다. 막대 위에 마우스를 올리면 사안 수(n)가 나옵니다. "
               "사안이 몇 건 안 되는 유형(예: 장인, 지원 5개)은 오차가 커서 순위를 읽으면 안 됩니다.")
    cf = TE.confound(df, axis)
    st.markdown("**유형별 위원회 심의 비율** (구조와 무관하게 사안 유형이 정함): " + " · ".join(
        f"{v} {w * 100:.0f}%" for v, w in zip(cf[axis], cf["위원회_비율"])))
with tabs[1]:
    facet = st.toggle("위원회를 거친 사안과 안 거친 사안을 나눠 보기", value=metric == "closure_days", key="th_facet")
    sc = df.copy()
    keys_order = [short[k] for k in picked]
    off = {s_: (i - (len(keys_order) - 1) / 2) * 0.12 for i, s_ in enumerate(keys_order)}
    sc["x"] = sc["n_needs"] + sc["구조"].map(off) + TE.jitter(len(sc), int(seed), 0.04)
    sc["분석가능성"] = sc["analyzable"].map(ANL)
    sc["위원회"] = sc["committee"].map({True: "위원회 심의 거침", False: "위원회 안 거침"})
    fig = px.scatter(sc, x="x", y=metric, color="구조", symbol="분석가능성",
                     symbol_map={ANL[True]: "circle", ANL[False]: "x"},
                     facet_col="위원회" if facet else None, opacity=0.55,
                     hover_data={"x": False, "type": True, "n_needs": True, "severity": True, "id": True},
                     labels={"x": "필요한 지원 개수", metric: mlabel, "type": "사안 유형", "n_needs": "지원 개수",
                             "severity": "심각도"}, **CS)
    fig.update_traces(marker=dict(size=8))
    groups = [("", sc)] if not facet else list(sc.groupby("위원회"))
    for col, (_, part) in enumerate(groups, start=1):
        tr = TE.trend(part, "n_needs", metric)
        for r in tr.itertuples(index=False):
            xs = [r.x0, r.x1]
            fig.add_trace(go.Scatter(x=xs, y=[r.절편 + r.기울기 * x for x in xs], mode="lines",
                                     line=dict(color=CS["color_discrete_map"].get(r.구조), width=2),
                                     name=f"{r.구조} 추세", showlegend=col == 1,
                                     hovertemplate=f"{r.구조}: 지원 1개당 {r.기울기:+.2f}{unit}<extra></extra>"),
                          row=1, col=col)
    fig.update_xaxes(dtick=1)
    fig.update_layout(height=520)
    st.plotly_chart(fig, width="stretch")
    tr = TE.trend(sc, "n_needs", metric)
    if not tr.empty:
        st.markdown("**지원 1개당 늘어나는 " + mlabel + "** (추세선 기울기 ± 95% 신뢰구간): " + " · ".join(
            f"{r.구조} {r.기울기:+.2f} ± {1.96 * r.기울기_se:.2f}{unit}" for r in tr.itertuples(index=False)))
        st.caption("점 하나가 사안 하나입니다 (구조별로 옆으로 조금 비켜 찍음). ○는 해결 절차가 명확한 사안, ×는 불명확한 사안. "
                   "기울기가 가파른 구조일수록 사안이 얽힐 때 크게 늦어집니다. 두 구조의 기울기 차이가 H2의 핵심입니다.")
with tabs[2]:
    kind = st.radio("모양", ["상자", "바이올린"], horizontal=True, key="th_dist")
    f = px.box if kind == "상자" else px.violin
    kw = dict(points="outliers") if kind == "상자" else dict(box=True, points=False)
    fig = f(df, x=axis, y=metric, color="구조", labels={metric: mlabel, axis: axis_label},
            **(CS | {"category_orders": CS["category_orders"] | order}), **kw)
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")
    st.caption("평균만 보면 긴 꼬리(몇몇 오래 걸린 사안)에 끌려갈 수 있습니다. 상자 가운데 선은 중앙값, 상자는 사안의 가운데 50%입니다.")
with tabs[3]:
    if not pair_ok:
        st.info("구조를 둘 이상 고르면 짝 비교가 나옵니다.")
    else:
        st.markdown(f"**{short[base_k]} − {short[target_k]}**: 같은 사안에서 {short[target_k]}이(가) 줄인 {mlabel}. 0보다 위면 줄인 것입니다.")
        gp = TE.gap_by(pr, "n_needs")
        pp = pr.assign(x=pr["n_needs"] + TE.jitter(len(pr), int(seed) + 1, 0.15),
                       분석가능성=pr["analyzable"].map(ANL))
        fig = px.scatter(pp, x="x", y="diff", color="분석가능성", opacity=0.45,
                         color_discrete_map={ANL[True]: "#8a94a6", ANL[False]: "#d9480f"},
                         hover_data={"x": False, "type": True, "base": ":.1f", "target": ":.1f"},
                         labels={"x": "필요한 지원 개수", "diff": f"줄인 {mlabel}", "type": "사안 유형",
                                 "base": short[base_k], "target": short[target_k]})
        fig.add_trace(go.Scatter(x=gp["n_needs"], y=gp["mean"], mode="lines+markers", name="평균 ± 95% CI",
                                 line=dict(color="#1f2937", width=2), marker=dict(size=10),
                                 error_y=dict(type="data", array=gp["ci"], visible=True),
                                 customdata=gp["n"], hovertemplate="지원 %{x}개: 평균 %{y:.2f} (n=%{customdata})<extra></extra>"))
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        fig.update_xaxes(dtick=1)
        fig.update_layout(height=480)
        st.plotly_chart(fig, width="stretch")
        st.markdown("**Perrow 2×2: 과업다양성 × 분석가능성별 평균 격차**")
        g2 = TE.gap_by(pr, ["variety_high", "analyzable"])
        g2["과업다양성"] = g2["variety_high"].map({False: "낮음 (지원 1~2개)", True: "높음 (지원 3개 이상)"})
        g2["분석가능성"] = g2["analyzable"].map(ANL)
        fig = px.bar(g2, x="과업다양성", y="mean", color="분석가능성", barmode="group", error_y="ci",
                     text=g2["n"].map(lambda n: f"n={n}"),
                     color_discrete_map={ANL[True]: "#8a94a6", ANL[False]: "#d9480f"},
                     category_orders={"과업다양성": ["낮음 (지원 1~2개)", "높음 (지원 3개 이상)"],
                                      "분석가능성": [ANL[True], ANL[False]]},
                     labels={"mean": f"줄인 {mlabel}"})
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, width="stretch")
        st.caption("Perrow 네 칸: 낮음·높음 = 일상적, 낮음·낮음 = 장인, 높음·높음 = 공학적, 높음·낮음 = 비일상적. "
                   "오른쪽 주황 막대(비일상적)가 가장 높으면 Perrow의 예측과 맞습니다.")
with tabs[4]:
    if not pair_ok:
        st.info("구조를 둘 이상 고르면 회귀가 나옵니다.")
    else:
        st.markdown(f"사안별 격차({short[base_k]} − {short[target_k]}, {mlabel})를 사안 특성으로 설명합니다. "
                    "각 계수는 **다른 특성이 같을 때** 그 특성이 격차를 얼마나 키우는지입니다. |t| ≥ 2면 우연으로 보기 어렵습니다.")
        st.dataframe(reg.drop(columns="항").set_index("설명").round(2), width="stretch")
        st.caption(f"최소제곱 회귀, 사안 {len(pr)}건. 시뮬레이션 사안이라 표본을 늘리면(기간·하루 사안 수) t는 얼마든지 커집니다. "
                   "t보다 계수의 부호와 크기를 보세요.")
if pair_ok:
    analysis(insights.theory(pr, reg, short[base_k], short[target_k], mlabel, unit), "유형별 분석 (H2)")
else:
    analysis(insights.by_type(df, axis, metric, mlabel), "유형별 분석")
with st.expander("이 분석은 맞는가: 검증 결과와 한계"):
    st.markdown("""
- **위원회 대기가 효과를 부풀린다 (고침).** 위원회는 심각도 2 이상이면서 단순 상담·민·형사 소송이 아닌 사안만 엽니다. 그래서 지원 1~2개 사안은 위원회로 가지 않고, 3개 이상 사안만 위원회 개최 간격(A 60일, B 30일)만큼 기다립니다. '종결까지'로 유형을 비교하면 교호적 사안의 큰 격차 대부분이 상호의존이 아니라 위원회 간격 차이입니다. 그래서 기본 지표를 **위원회 대기를 뺀 처리 기간**으로 바꾸고, Home의 H2 판정도 같은 지표로 바꿨습니다.
- **분석가능성이 결과에 영향이 없었다 (고침).** 예전에는 분석가능성이 무작위로 붙는 이름표일 뿐이라 공학적과 비일상적의 차이가 전부 지원 개수에서 나왔습니다. 이제 해결 절차가 불명확한 사안은 전문가 처리 시간이 1.5배이고, 분산 구조에서는 기관을 옮길 때 40% 확률로 교사가 앞 기관에 되돌아가며, 통합 구조에서는 사례 회의(2시간) 한 번으로 흡수합니다 (`sim/engine.py`의 가정값).
- **Perrow의 효과는 가정에서 나온다.** 위 메커니즘은 Perrow의 주장을 모델에 넣은 것이라 결과가 그 주장을 '증명'하지는 않습니다. 보여 주는 것은 '이 가정이 맞다면 효과가 이만큼'입니다.
- **Thompson 유형과 Perrow 과업다양성은 같은 변수다.** 둘 다 필요한 지원 개수(1·2·3개 이상)로 정해집니다. 그래서 '지원 개수' 축과 산점도가 가장 정직한 보기입니다.
- **유형과 지원 개수는 팀 가정이다.** 사안 유형별로 필요한 지원은 팀 자료를 바탕으로 정했고, 약 15%는 다른 유형과 겹친 복합 사안이 됩니다. 실측 비율은 사안 유형 비율만 맞췄습니다.
- **표본이 작은 칸이 있다.** 기본 설정(60일, 하루 3건)에서 장인 유형과 지원 5개 사안은 몇 건뿐입니다. 신뢰구간이 넓은 칸은 방향만 보세요.
- **같은 시드 한 번의 결과다.** 사이드바의 난수 시드를 바꿔도 방향이 유지되는지 확인하면 더 튼튼합니다.
""")

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
