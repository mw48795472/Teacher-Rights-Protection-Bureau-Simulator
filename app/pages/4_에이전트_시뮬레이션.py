import json

import pandas as pd
import streamlit as st

from common import llm_badge, retriever, scenarios
from agents.llm import llm_enabled, model_name
from agents.roles import STRUCTURES
from agents.runner import run_agents

st.set_page_config(page_title="에이전트 시뮬레이션", page_icon="🏫", layout="wide")
llm_badge()
st.title("에이전트 시뮬레이션")
st.caption("행위자 에이전트가 행동을 제안하면, 규제 컴플라이언스 에이전트가 법령·조례를 검색해 "
           "실행 전에 허용·조건부 허용·차단을 판정합니다.")

if llm_enabled():
    st.success(f"Claude 에이전트 모드 ({model_name()}). 한 번 실행에 행동 수 × 2회 API 호출이 듭니다.")
else:
    st.warning("ANTHROPIC_API_KEY가 없어 **오프라인 예시 모드**로 돕니다. 행위자는 정해진 예시 스크립트를 따르고, "
               "컴플라이언스는 몇 가지 규칙으로만 판정합니다. 실제 에이전트 판단을 보려면 키를 넣어 주세요.")

n_unverified = sum(not d.verified for d in retriever().docs if d.source_type in ("ordinance", "law"))
if n_unverified:
    st.info(f"조례 조문 {n_unverified}개가 팀 요약 상태입니다. 교권5법 원문도 아직 없으면 판정이 '근거 불충분'으로 "
            "나오기 쉽습니다. LAW_OC를 넣고 `python -m collector.pipeline`을 돌리면 원문으로 판정합니다.")

sc = scenarios()
c1, c2, c3 = st.columns([2, 2, 1])
pick = c1.selectbox("시나리오", range(len(sc)), format_func=lambda i: sc[i]["name"])
keys = c2.multiselect("조직 구조", list(STRUCTURES), default=["integrated", "drama"],
                      format_func=lambda k: STRUCTURES[k].name)
max_turns = c3.slider("최대 행동 수", 6, 30, 20)
spec = sc[pick]
st.caption(spec.get("description", ""))

COLOR = {"허용": "green", "조건부 허용": "orange", "차단": "red"}

if st.button("실행", type="primary", disabled=not keys):
    st.session_state["agent_runs"] = {}
    for k in keys:
        box = st.status(f"{STRUCTURES[k].name} 실행 중...", expanded=False)

        def on_turn(t, box=box):
            v = t.review.verdict
            box.write(f"{t.n}. {t.actor} [{t.review.action.intent}] → {v.decision}")

        st.session_state["agent_runs"][k] = run_agents(spec, k, retriever(), max_turns, on_turn)
        box.update(label=f"{STRUCTURES[k].name} 완료", state="complete")

runs = st.session_state.get("agent_runs", {})
if not runs:
    st.stop()

st.subheader("요약")
summary = {STRUCTURES[k].name: {m: ("예" if v is True else "아니오" if v is False else v) for m, v in r.metrics.items()}
           for k, r in runs.items()}
st.dataframe(pd.DataFrame(summary).astype(str), width="stretch")

docs = {d.id: d for d in retriever().docs}
cols = st.columns(len(runs))
for col, (k, run) in zip(cols, runs.items()):
    with col:
        st.subheader(STRUCTURES[k].name)
        st.caption(STRUCTURES[k].description)
        for t in run.turns:
            a, v = t.review.action, t.review.verdict
            color = COLOR[v.decision]
            with st.container(border=True):
                st.markdown(f"**{t.n}. {t.actor}** · `{a.intent}`  \n{a.description}")
                st.markdown(f":{color}[**{v.decision}**] · {v.category}")
                if v.decision != "허용" or v.category != "적법":
                    st.caption(v.reason)
                if v.condition:
                    st.caption(f"조건: {v.condition}")
                if v.alternative_intent:
                    st.caption(f"대안: {v.alternative_actor or t.actor} → {v.alternative_intent}")
                if t.unhandled:
                    st.caption(f":red[챙기는 주체 없는 후속 절차: {', '.join(t.unhandled)}]")
                if v.cited_ids:
                    with st.expander("근거 조문"):
                        for cid in v.cited_ids:
                            d = docs.get(cid)
                            if d:
                                tag = "" if d.verified else " (팀 요약, 원문 확인 필요)"
                                st.markdown(f"**{d.title}**{tag}  \n{d.text}")
        st.download_button("로그 JSON 내려받기", json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
                           file_name=f"agent_run_{k}.json", mime="application/json", key=f"dl-{k}")
