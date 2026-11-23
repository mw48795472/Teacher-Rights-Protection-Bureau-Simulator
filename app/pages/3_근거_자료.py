import pandas as pd
import streamlit as st

from common import llm_badge, retriever
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
