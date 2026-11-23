import plotly.express as px
import streamlit as st

from common import llm_badge  # noqa: F401  (경로·.env 설정)
from sim import calibration as cal

st.set_page_config(page_title="실측 데이터", page_icon="🏫", layout="wide")
llm_badge()
st.title("실측 데이터와 가정값")
st.caption("시뮬레이터 값 가운데 무엇이 공공데이터로 맞춰졌고 무엇이 아직 가정인지 보여 줍니다. "
           "원자료는 저장소 `data/measured/raw/`, 옮긴 숫자는 `config/measured.yaml`에 있습니다.")

st.subheader("데이터 출처")
src = cal.data_sources_table()
if not src.empty:
    src["링크"] = src["링크"].where(src["링크"].str.startswith("http"), None)
    groups = list(dict.fromkeys(src["구분"]))
    for tab, g in zip(st.tabs(groups), groups):
        with tab:
            st.dataframe(src[src["구분"] == g].drop(columns="구분"), hide_index=True, use_container_width=True,
                         column_config={"링크": st.column_config.LinkColumn("링크", display_text="열기")})
    st.caption("목록은 `config/data_sources.yaml`에 있습니다. 키는 `.env` 또는 Streamlit Secrets에 넣습니다.")

st.subheader("값별 실측·가정 현황")
st.dataframe(cal.assumption_table(), hide_index=True, use_container_width=True)
st.info("처리 시간, 전담관 인원·가용률, 위원회 개최 간격은 공개 자료가 없어 가정값입니다. "
        "경기도교육청 정보공개청구 답변을 받으면 이 표의 '가정 유지' 항목을 바꿉니다.")

st.subheader("사안 유형 비율: 팀 가정 vs 실측 기반")
mix = cal.case_mix_table()
st.dataframe(mix, hide_index=True, use_container_width=True)
long = mix.melt(id_vars="사안 유형", value_vars=["팀 가정(%)", "실측 기반(%)"], var_name="기준", value_name="비율(%)")
st.plotly_chart(px.bar(long, x="사안 유형", y="비율(%)", color="기준", barmode="group"), use_container_width=True)
st.caption("교권보호위원회 침해 유형은 대부분 학생에 의한 침해라 학부모 민원 비중이 낮게 잡힙니다. "
           "경기 교권보호단은 학부모 민원·아동학대 신고 사안이 많다고 보도되었으므로, 실측 기반 비율은 "
           "'교보위로 가는 사안 전체'의 구성으로 읽어 주세요. 끄려면 `config/measured.yaml`의 `use.case_mix`를 false로 바꿉니다.")

c1, c2 = st.columns(2)
with c1:
    st.subheader("전국 교권보호위원회 심의 건수")
    st.plotly_chart(px.line(cal.committee_trend(), x="학년도", y="교권보호위원회 심의 건수", markers=True),
                    use_container_width=True)
    st.caption(f"출처: {cal.source('kbw').get('title')}, {cal.source('center').get('title')}")
with c2:
    st.subheader("교육활동보호센터 이용 건수")
    cu = cal.center_usage()
    st.plotly_chart(px.bar(cu, x="연도", y="건수", color="유형"), use_container_width=True)
    st.caption(f"출처: {cal.source('center').get('title')}")

st.subheader("교육지원청별 교원 수 (사안 비중의 근거)")
ot = cal.office_table()
if ot.empty:
    st.write("집계표가 없습니다. `python -m collector.measured <xlsx>`로 만들 수 있습니다.")
else:
    st.plotly_chart(px.bar(ot, x="office", y="teachers", hover_data=["schools", "students"],
                           labels={"office": "교육지원청", "teachers": "교원 수"}), use_container_width=True)
    st.caption(f"출처: {cal.source('schools').get('title')}. 유치원·초·중·고·특수학교, 도교육청 직속 학교는 소재 시·군의 교육지원청에 넣었습니다.")

c3, c4 = st.columns(2)
with c3:
    st.subheader("경기 아동학대 판단 사례 (전체 아동)")
    ab = cal.child_abuse_gyeonggi()
    if not ab.empty:
        st.plotly_chart(px.line(ab.melt(id_vars="연도", var_name="유형", value_name="건수"),
                                x="연도", y="건수", color="유형", markers=True), use_container_width=True)
    st.caption(f"출처: {cal.source('abuse').get('title')}. 교원 대상 신고만 뽑은 통계가 아니어서 참고용입니다.")
with c4:
    st.subheader("아동학대 검거 및 조치 (전국)")
    po = cal.police_child_abuse()
    if not po.empty:
        st.plotly_chart(px.line(po.melt(id_vars="연도", var_name="구분", value_name="건·명"),
                                x="연도", y="건·명", color="구분", markers=True), use_container_width=True)
    st.caption(f"출처: {cal.source('police').get('title')}")

st.subheader("경기데이터드림 연결 (GG_DATA_KEY)")
from collector import gg_data  # noqa: E402


@st.cache_data(ttl=3600, show_spinner="경기데이터드림 확인 중…")
def _gg(name: str) -> tuple[dict, object]:
    """(키 상태, 표). 저장된 CSV(python -m collector.gg_data)가 있으면 그것을, 없으면 키로 바로 받는다."""
    status = gg_data.check_key()
    saved = gg_data.load_saved(name)
    if not saved.empty:
        return status, saved
    if not status["ok"]:
        return status, None
    try:
        return status, gg_data.fetch_table(name)
    except gg_data.GgDataError as e:
        return {**status, "reason": f"키는 정상, 자료 받기 실패: {e}"}, None


gg_status, police = _gg("police")
if gg_status["ok"]:
    st.success("경기데이터드림 키가 정상 작동합니다.")
else:
    st.warning(f"경기데이터드림 키 확인 실패: {gg_status['reason']}. "
               "`.env` 또는 Streamlit Secrets에 `GG_DATA_KEY`를 넣고, 로컬에서는 "
               "`python -m collector.gg_data --check`로 확인할 수 있습니다.")
if police is not None and not police.empty:
    po = gg_data.by_office(police, "지구대·파출소")
    if not ot.empty:
        po = po.merge(ot[["office", "teachers"]], on="office", how="left")
        po["교원 1천 명당 관서"] = (po["지구대·파출소"] / po["teachers"] * 1000).round(2)
    st.plotly_chart(px.bar(po, x="office", y="지구대·파출소", hover_data=[c for c in po.columns if c != "office"],
                           labels={"office": "교육지원청"}), use_container_width=True)
    st.caption(f"출처: 경기데이터드림 「{gg_data.SERVICES['police']['title']}」 ({len(police)}곳). "
               "교원 대상 아동학대 신고가 접수·조사되는 관서의 분포로, 교육지원청과 경찰 협조 부담을 가늠하는 참고값입니다. "
               "시뮬레이터의 처리시간에는 아직 넣지 않았습니다.")

st.subheader("국회 법률안 (ASSEMBLY_KEY)")
from collector import assembly  # noqa: E402
from collector.pipeline import load_sources  # noqa: E402


@st.cache_data(ttl=86400, show_spinner="열린국회정보에서 법률안을 받는 중…")
def _bills() -> tuple[dict, list]:
    status = assembly.check_key()
    if not status["ok"]:
        return status, []
    return status, [d.to_dict() for d in assembly.cached_bills(load_sources().get("bills"))]


as_status, bills = _bills()
if as_status["ok"]:
    st.success(f"열린국회정보 키가 정상 작동합니다. 교권 관련 법률안 {len(bills)}건을 근거 자료에 넣었습니다.")
else:
    st.warning(f"열린국회정보 키 확인 실패: {as_status['reason']}. `.env` 또는 Streamlit Secrets에 `ASSEMBLY_KEY`를 넣어 주세요.")
if bills:
    import pandas as pd  # noqa: E402
    bt = pd.DataFrame([{"제안일": b["meta"].get("propose_dt"), "법률안": b["title"].split(" [")[0],
                        "대표발의": b["meta"].get("proposer"), "단계": b["meta"].get("stage"), "링크": b["url"]}
                       for b in bills])
    st.dataframe(bt, hide_index=True, use_container_width=True,
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="의안정보")})
    st.caption("출처: 열린국회정보 「국회의원 발의법률안」, 「법률안 제안이유 및 주요내용」. 검색어는 `config/sources.yaml`의 `bills:`. "
               "제안이유 본문은 근거 자료 검색에서 찾을 수 있습니다.")
