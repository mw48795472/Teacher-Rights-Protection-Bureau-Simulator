import pandas as pd
import streamlit as st

from common import llm_badge, neis_status, retriever, schools
from rag.answer import answer

st.set_page_config(page_title="근거 자료", page_icon="🏫", layout="wide")
llm_badge()
st.title("근거 자료")
st.caption("시뮬레이터의 각 행동이 인용하는 조례·정책·기사·이론 자료입니다.")

q = st.text_input("질문", "전담관이 교육활동 침해 여부를 직접 판단할 수 있나요?")
k = st.slider("가져올 자료 수", 1, 10, 4)
if q:
    hits = retriever().search(q, k=k)
    text, used = answer(q, hits)
    st.markdown(text)
    if used:
        with st.expander("인용 자료"):
            for i, h in enumerate(hits, 1):
                st.markdown(f"**[{i}]** {h.citation}  \n{h.doc.text}")

st.subheader("전체 지식베이스")
rows = [{"제목": d.title, "유형": d.source_type, "신뢰도": d.reliability,
         "원문 수집": "예" if d.verified else "아니오 (팀 요약)", "URL": d.url} for d in retriever().docs]
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
             column_config={"URL": st.column_config.LinkColumn()})

st.subheader("데이터 출처")
sch = schools()
if sch.empty:
    st.markdown("- **학교 위치**: 없음. `data/schools/gyeonggi_schools.csv`에 전국초중등학교위치표준데이터를 넣으면 반영됩니다.")
else:
    lv = sch["level"].value_counts()
    date = sch["date"].dropna().max() if "date" in sch else ""
    prov = sch["provider"].dropna().iloc[0] if "provider" in sch and sch["provider"].notna().any() else ""
    st.markdown(
        f"- **학교 위치**: 공공데이터포털 [전국초중등학교위치표준데이터]"
        f"(https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=전국초중등학교위치표준데이터)"
        f"{f', 제공 {prov}' if prov else ''}{f', 기준일 {date}' if date else ''}. "
        f"경기도 운영 중인 학교 {len(sch):,}곳 (초 {lv.get('초등학교', 0):,} · 중 {lv.get('중학교', 0):,} · "
        f"고 {lv.get('고등학교', 0):,}). 사안 발생 비중에 씁니다.")
ns = neis_status()
if ns["ok"]:
    st.markdown(f"- **학교 기본정보**: [NEIS 교육정보 개방포털](https://open.neis.go.kr) 학교기본정보 (하루 1회 갱신). "
                f"학교명·관할 대조 결과 일치 {ns['일치']:,}곳, NEIS에만 {ns['NEIS에만']}곳, "
                f"위치 데이터에만 {ns['위치데이터에만']}곳.")
    if not ns["only_neis"].empty:
        with st.expander("NEIS에만 있는 학교 (위치 데이터 기준일 뒤 신설·개명 등)"):
            st.dataframe(ns["only_neis"][["name", "level", "office", "addr"]], hide_index=True, width="stretch")
else:
    st.markdown(f"- **학교 기본정보**: NEIS 미연결 ({ns['reason']}).")
st.markdown("- **교육지원청 위치**: 25개 교육지원청을 시청 부근 대략 좌표로 표시 (청사 주소 아님).\n"
            "- **법령·조례**: 국가법령정보센터 Open API (`LAW_OC`가 있을 때 원문 수집, 없으면 팀 요약).")
