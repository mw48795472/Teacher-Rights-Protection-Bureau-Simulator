import pandas as pd
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
st.caption("시뮬레이션의 A·B0·B·C는 아래 네 가지 조직 방식을 뜻합니다. 같은 사안 흐름을 네 구조에 똑같이 넣어 비교합니다.")
S = structures()
for k, s in S.items():
    with st.container(border=True):
        st.markdown(f"**{s['name']}**")
        st.markdown(s.get("definition", s["description"]))
        st.caption(f"이론: {s['theory']}")


def _row(s: dict) -> dict:
    p = s["params"]
    integ = s["kind"] == "integrated"
    yn = lambda v: "있음" if v else "없음"
    return {
        "구조": s.get("short", s["name"]),
        "접수 창구": "통합 접수 창구 한 곳 (경기: 교권보호 119)" if integ else "센터·법률·행정 창구를 교사가 각각",
        "사안 조정자": "상근 전담관 (주 담당)" if integ else "없음 (교사가 직접)",
        "상근 전담관": f"{p['regular_officers']}명" if integ else "-",
        "비상근 전문가": f"{p['nonregular_officers']}명" if integ else "-",
        "비상근 즉시 응답": f"{p['nonregular_availability']:.0%}" if integ else "-",
        "교육감 직속": yn(p.get("escalation")),
        "연계절차 (제17조)": yn(p.get("linkage_procedure")),
        "업무매뉴얼 (제25조)": yn(p.get("manual")),
        "위원회 개최 간격": f"{p['committee_interval_days']}근무일",
    }


st.markdown("**한눈에 비교**")
st.dataframe(pd.DataFrame([_row(s) for s in S.values()]).set_index("구조").T, width="stretch")
st.caption("인원·응답 비율·개최 간격 중 출처가 없는 값은 가정값이며 시뮬레이션 사이드바에서 바꿀 수 있습니다.")

with st.expander("용어 정리"):
    st.markdown(
        """
| 용어 | 뜻 |
|---|---|
| 교권보호단 | 경기도교육청이 2026년 교육감 직속으로 만든 교권보호 조직. 교육감이 단장 |
| 교권보호 119 | 교권보호단의 접수 창구. 사안을 받아 긴급성·전문성에 따라 분류하고 전담관에게 배정 |
| 상근 전담관 | 교육전문직. 사안의 주 담당으로 피해 교원과 1:1로 연결되어 상담부터 사후 관리까지 맡음 |
| 비상근 전담관 | 변호사·상담 전문가 등 외부 전문가. 본업이 있어 필요할 때 사안에 합류 |
| 지역교권보호지원센터 | 기존부터 있던 상담·법률 안내 기관 |
| 지역교권보호위원회 | 교육활동 침해 여부를 심의하고 침해 학생·보호자 조치를 의결. 전담관에게는 이 권한이 없음 (조례 제15조) |
| 교육지원청 | 시·군 단위 교육행정 기관. 경기도에는 25곳이 있고 관할 학교를 지도·감독 |
| 1호 사안 | 교육감이 1호 사안으로 지정하고 학부모를 형사 고발한 부천 사안 (경인일보 8.10 보도) |
| 연계절차 (조례 제17조) | 교권보호단과 기존 센터·기관 사이의 업무 연계 절차. 없으면 같은 사안을 두 기관이 따로 접수 |
| 업무매뉴얼 (조례 제25조) | 접수·배정 기준을 통일한 매뉴얼. 없으면 분류 착오가 늘어남 |
| 드라마식 교권보호국 | 에이전트 시뮬레이션에만 나오는 가상 모델. 요원이 현장을 직접 제압하는 방식이 현실 법 체계에서 어디서 막히는지 보기 위한 비교군 |
"""
    )

st.subheader("메뉴")
st.markdown(
    """
- **시뮬레이션**: 구조와 조건을 고르고 수백 건의 사안을 돌려 지표를 비교합니다. Claude가 결과를 이론·조문 근거로 설명합니다.
- **사안 추적**: 1호 사안 같은 시나리오 1건이 구조마다 누구를 거쳐 처리되는지 따라갑니다.
- **에이전트 시뮬레이션**: 행위자 에이전트의 행동을 규제 컴플라이언스 에이전트가 법령·조례로 심사해 허용·차단합니다.
- **근거 자료**: 시뮬레이터가 인용하는 조례·정책·이론 자료를 검색합니다.
"""
)

n = len(retriever().docs)
unverified = sum(not d.verified for d in retriever().docs)
st.warning(f"지식베이스 문서 {n}개 중 {unverified}개는 팀 요약입니다. `python -m collector.pipeline`으로 원문을 수집하면 대체됩니다. "
           "처리시간·확률 대부분은 가정값이므로 결과는 이론의 논리를 보여주는 사고실험으로 다뤄 주세요.")
