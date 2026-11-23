import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import llm_badge, retriever, scenarios, structures
from geo.gyeonggi import DEFAULT_CSV, OFFICE_BY_KEY, OFFICES, hierarchy, load_schools, office_weights
from sim.engine import SimConfig, run
from sim.metrics import to_frame

st.set_page_config(page_title="학교 지도", page_icon="🏫", layout="wide")
llm_badge()
st.title("경기도 학교 지도와 감독 구조")
st.caption("경기도교육청 → 25개 교육지원청 → 관할 초·중·고 학교. 사안은 실제 학교에서 생기고, "
           "그 학교 관할 교육지원청의 지역교권보호위원회로 넘어갑니다.")


@st.cache_data(show_spinner="학교 데이터를 읽는 중...")
def schools_from(data: bytes | None) -> pd.DataFrame:
    import io
    return load_schools(io.BytesIO(data) if data is not None else None)


up = st.file_uploader("전국초중등학교위치표준데이터 CSV (선택)", type="csv",
                      help="공공데이터포털(data.go.kr)에서 '전국초중등학교위치표준데이터'를 검색해 CSV를 내려받으세요. 키는 필요 없습니다.")
try:
    schools = schools_from(up.getvalue() if up else None)
except ValueError as e:
    st.error(str(e))
    schools = schools_from(None)

if schools.empty:
    st.info("학교 데이터가 없어 **25개 교육지원청만** 표시합니다. 사안은 교육지원청마다 같은 비중으로 생깁니다. "
            "CSV를 올리거나 저장소의 `data/schools/gyeonggi_schools.csv`에 넣으면 실제 학교와 학교 수 비중으로 돕니다.")
else:
    src = "업로드한 파일" if up else f"`{DEFAULT_CSV.relative_to(DEFAULT_CSV.parents[2])}`"
    lv = schools["level"].value_counts()
    st.success(f"{src}에서 경기도 학교 {len(schools):,}곳을 읽었습니다 "
               f"(초 {lv.get('초등학교', 0):,} · 중 {lv.get('중학교', 0):,} · 고 {lv.get('고등학교', 0):,}).")

offices_df = pd.DataFrame([{"office": o.key, "name": o.name, "lat": o.lat, "lon": o.lon} for o in OFFICES])
n_by_office = schools["office"].value_counts() if not schools.empty else pd.Series(dtype=int)
offices_df["학교 수"] = offices_df["office"].map(n_by_office).fillna(0).astype(int)

tab_map, tab_tree, tab_sim = st.tabs(["지도", "감독 구조", "관할별 시뮬레이션"])

LEVEL_COLOR = {"초등학교": "#2a6fdb", "중학교": "#2e9e6a", "고등학교": "#e8833a"}
MAP = dict(map_style="carto-positron", zoom=8.2, center={"lat": 37.55, "lon": 127.1})


def office_layer(fig, df, size=None, text=None):
    fig.add_trace(go.Scattermap(
        lat=df["lat"], lon=df["lon"], mode="markers+text",
        marker=dict(size=size if size is not None else 14, color="#d64f6b", opacity=0.85),
        text=df["office"], textposition="top center", name="교육지원청",
        hovertext=text if text is not None else df["name"], hoverinfo="text"))


with tab_map:
    levels = st.multiselect("학교급", list(LEVEL_COLOR), default=list(LEVEL_COLOR)) if not schools.empty else []
    if not schools.empty:
        pts = schools[schools["level"].isin(levels)]
        fig = px.scatter_map(pts, lat="lat", lon="lon", color="level", color_discrete_map=LEVEL_COLOR,
                             hover_name="name", hover_data={"office": True, "addr": True, "lat": False, "lon": False,
                                                            "level": False},
                             height=620, **MAP)
        fig.update_traces(marker=dict(size=5, opacity=0.6))
    else:
        fig = go.Figure()
        fig.update_layout(height=620, map=dict(style=MAP["map_style"], zoom=MAP["zoom"], center=MAP["center"]))
    office_layer(fig, offices_df, text=offices_df["name"] + "<br>관할 학교 " + offices_df["학교 수"].astype(str) + "곳")
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend_title_text="")
    st.plotly_chart(fig, width="stretch")
    st.caption("교육지원청 위치는 해당 시청 부근의 대략 위치입니다 (청사 주소 아님).")

with tab_tree:
    h = hierarchy(schools)
    fig = px.sunburst(h, ids="id", parents="parent", names="label", values="value",
                      hover_data={"role": True}, height=640, maxdepth=3)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "- **교육부**: 교원지위법 등 국가 기준\n"
        "- **경기도교육청 / 교육감**: 교권보호단 단장. 교권보호 119로 접수하고 상근·비상근 전담관을 배정 (조례)\n"
        "- **교육지원청 25곳**: 관할 학교를 지도·감독하고 지역교권보호위원회를 둔다. 침해 여부 심의와 조치는 위원회 몫\n"
        "- **전담관**: 사안 지원과 연계 담당. 조사·심의 권한은 없다 (조례 요약)\n\n"
        ":orange[지역교권보호위원회를 교육지원청에 두는 부분은 교원지위법 원문으로 확인이 필요합니다 "
        "(현재 근거 자료에 원문이 없음).]")

with tab_sim:
    S = structures()
    c1, c2, c3, c4 = st.columns(4)
    keys = c1.multiselect("조직 구조", list(S), default=[k for k in ("A_distributed", "B_gyeonggi") if k in S],
                          format_func=lambda k: S[k].get("short", S[k]["name"]))
    rate = c2.slider("하루 사안 수 (도 전체)", 1.0, 15.0, 3.0, 0.5)
    cap = c3.slider("위원회 1회 심의 정원 (가정)", 1, 20, 6)
    interval = c4.slider("위원회 개최 간격 (근무일, 가정)", 5, 60, 20)

    # 특정 학교에서 시나리오 사안을 일으킨다
    sc = scenarios()
    d1, d2 = st.columns(2)
    pick = d1.selectbox("시나리오 사안", range(len(sc)), format_func=lambda i: sc[i]["name"])
    if not schools.empty:
        opts = schools.sort_values(["office", "name"])
        bucheon = [i for i in opts.index if opts.at[i, "office"] == "부천"]  # 1호 사안은 부천
        si = d2.selectbox("사안이 생긴 학교", opts.index,
                          index=list(opts.index).index(bucheon[0]) if bucheon else 0,
                          format_func=lambda i: f"{opts.at[i, 'name']} ({opts.at[i, 'office']})")
        where_school, where_office = opts.at[si, "name"], opts.at[si, "office"]
    else:
        where_office = d2.selectbox("사안이 생긴 교육지원청", [o.key for o in OFFICES], index=3)
        where_school = f"{where_office} 관할 학교"

    if st.button("실행", type="primary", disabled=not keys):
        weights = office_weights(schools)
        spec = {**sc[pick], "office": where_office, "name": f"{sc[pick]['name']} @ {where_school}"}
        out = {}
        for k in keys:
            cfg = SimConfig(S[k], days=60, arrivals_per_day=rate, seed=7, offices=weights,
                            committee_capacity=cap, overrides={"committee_interval_days": interval})
            cases = run(cfg, retriever(), [(spec, 10.0)])
            out[k] = (to_frame(cases, k), next((c.trace for c in cases if c.label == spec["name"]), []))
        st.session_state["geo_runs"] = {"runs": out, "spec": spec, "where": (where_school, where_office)}

    res = st.session_state.get("geo_runs")
    if res:
        runs = res["runs"]
        frames = []
        for k, (df, _) in runs.items():
            g = df.groupby("office").agg(사안=("id", "size"), 종결일=("closure_days", "mean"))
            wc = df[df["committee_wait_days"] > 0].groupby("office")["committee_wait_days"]
            g["위원회 사안"] = wc.size()
            g["위원회 대기일"] = wc.mean()
            g["구조"] = S[k].get("short", S[k]["name"])
            frames.append(g.reset_index())
        per = pd.concat(frames).fillna(0)
        per = per.merge(offices_df[["office", "lat", "lon"]], on="office")

        show = st.selectbox("지도에 표시할 구조", list(runs), format_func=lambda k: S[k].get("short", S[k]["name"]))
        m = per[per["구조"] == S[show].get("short", S[show]["name"])]
        fig = px.scatter_map(m, lat="lat", lon="lon", size="사안", color="위원회 대기일",
                             color_continuous_scale="OrRd", hover_name="office",
                             hover_data={"사안": True, "위원회 사안": True, "위원회 대기일": ":.1f", "종결일": ":.1f",
                                         "lat": False, "lon": False},
                             size_max=40, height=560, **MAP)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("원 크기 = 관할에서 생긴 사안 수, 색 = 위원회 심의까지 평균 대기 (근무일).")

        tbl = per.pivot_table(index="office", columns="구조", values=["사안", "위원회 대기일", "종결일"]).round(1)
        st.dataframe(tbl.sort_values(tbl.columns[0], ascending=False), width="stretch")

        school, office = res["where"]
        st.subheader(f"시나리오 사안 경로: {school} → {OFFICE_BY_KEY[office].name}")
        cols = st.columns(len(runs))
        for col, (k, (_, trace)) in zip(cols, runs.items()):
            with col:
                st.markdown(f"**{S[k].get('short', S[k]['name'])}**")
                if not trace:
                    st.warning("기간 안에 종결되지 않았습니다.")
                    continue
                t0 = trace[0]["day"]
                st.dataframe(pd.DataFrame([{"경과일": round(e["day"] - t0, 1), "주체": e["actor"], "행동": e["action"]}
                                           for e in trace]), width="stretch", hide_index=True)
