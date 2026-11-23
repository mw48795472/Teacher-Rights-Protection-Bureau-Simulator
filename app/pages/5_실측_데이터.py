import plotly.express as px
import streamlit as st

from common import llm_badge  # noqa: F401  (경로·.env 설정)
from sim import calibration as cal

st.set_page_config(page_title="실측 데이터", page_icon="🏫", layout="wide")
llm_badge()
st.title("실측 데이터와 가정값")
st.caption("시뮬레이터 값 가운데 무엇이 공공데이터로 맞춰졌고 무엇이 아직 가정인지 보여 줍니다. "
           "원자료는 저장소 `data/measured/raw/`, 옮긴 숫자는 `config/measured.yaml`에 있습니다.")

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
