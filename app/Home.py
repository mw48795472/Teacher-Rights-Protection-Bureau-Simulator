import streamlit as st

from common import llm_badge, retriever, structures

st.set_page_config(page_title="교권보호국 시뮬레이터", page_icon="🏫", layout="wide")
llm_badge()

st.title("교권보호국 시뮬레이터")
st.caption("경기도교육청 교권보호단 조직 개편을 조직이론으로 실험해 보는 발표용 데모")

st.markdown(
    """
**발표 질문**: 경기도교육청은 왜 교권보호 업무를 교육감 직속·전담관 중심 체계로 재조직했으며,
이 체계는 어떤 조건에서 실제 교권 침해에 효과적으로 대응할 수 있는가?

| 수업 개념 | 시뮬레이터에서 보는 것 |
|---|---|
| ① 조직환경 (개방체계·상황이론) | 언론 보도 같은 환경 압력으로 사안이 몰릴 때 구조별로 버티는 정도, 사안 특성(Perrow)과 구조의 적합성 |
| ② 분업과 조정 (Gulick·Thompson·Perrow) | 교사가 직접 하던 조정을 조직이 맡을 때 접촉 기관 수·반복 진술·조정 메시지가 어떻게 바뀌는가 |

**결론에서 제시한 실효성 조건 세 가지를 변수로 켜고 끕니다.**
① 기존 조직과의 역할 구분(조례 제17조 연계절차) ② 안정적인 전담 인력(상근 수, 비상근 응답성) ③ 제도화(조례 제25조 업무매뉴얼)
"""
)

st.subheader("비교할 조직 구조")
cols = st.columns(len(structures()))
for col, (k, s) in zip(cols, structures().items()):
    with col:
        st.markdown(f"**{s['name']}**")
        st.caption(s["description"])
        st.markdown(f"<small>이론: {s['theory']}</small>", unsafe_allow_html=True)

st.subheader("메뉴")
st.markdown(
    """
- **시뮬레이션**: 구조와 조건을 고르고 수백 건의 사안을 돌려 지표를 비교합니다. Claude가 결과를 이론·조문 근거로 설명합니다.
- **사안 추적**: 1호 사안 같은 시나리오 1건이 구조마다 누구를 거쳐 처리되는지 따라갑니다.
- **근거 자료**: 시뮬레이터가 인용하는 조례·정책·이론 자료를 검색합니다.
"""
)

n = len(retriever().docs)
unverified = sum(not d.verified for d in retriever().docs)
st.warning(f"지식베이스 문서 {n}개 중 {unverified}개는 팀 요약입니다. `python -m collector.pipeline`으로 원문을 수집하면 대체됩니다. "
           "처리시간·확률 대부분은 가정값이므로 결과는 이론의 논리를 보여주는 사고실험으로 다뤄 주세요.")
