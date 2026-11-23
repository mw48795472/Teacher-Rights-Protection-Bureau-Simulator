import json

import pandas as pd
import streamlit as st

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다 (common·sim 을 불러오기 전에)

fresh.ensure()
from common import data_label, llm_badge, retriever, scenario_kind, scenarios
from agents.llm import llm_enabled, model_name
from agents.roles import STRUCTURES
from agents.drama import adapt, build_script, script_text
from agents.runner import run_agents
from sim import insights

st.set_page_config(page_title="에이전트 시뮬레이션", page_icon="🏫", layout="wide")
llm_badge()
st.title("에이전트 시뮬레이션")
st.caption("검증하는 가설: H6 법적 권한과 공식 구조. 드라마식 강제 개입은 권한 초과로 막히고 조정 중심 구조만 제도 안에서 작동하는가.")
st.caption("한 편의 드라마를 쓰듯 돌아갑니다. 인물(행위자 에이전트)이 성향대로 다음 장면을 만들면, 규제 컴플라이언스 "
           "에이전트가 법령·조례를 찾아 그 장면이 현실에서 가능한지 허용·조건부 허용·차단으로 판정합니다. "
           "결과는 대본과 판정 로그로 볼 수 있습니다.")

if llm_enabled():
    st.success(f"Claude 에이전트 모드 ({model_name()}). 한 번 실행에 행동 수 × 2회 API 호출이 듭니다.")
else:
    st.warning("ANTHROPIC_API_KEY가 없어 **오프라인 예시 모드**로 돕니다. 행위자는 정해진 예시 스크립트를 따르고, "
               "컴플라이언스는 몇 가지 규칙으로만 판정합니다. 실제 에이전트 판단을 보려면 키를 넣어 주세요.")

n_unchecked = sum(d.needs_check for d in retriever().docs if d.source_type in ("ordinance", "law"))
if n_unchecked:
    st.info(f"법령·조례 조문 {n_unchecked}개가 원문도 원문 링크도 없는 팀 요약입니다. 이 조문에 기댄 판정은 '근거 불충분'으로 "
            "나오기 쉽습니다. LAW_OC를 넣고 `python -m collector.pipeline`을 돌리면 원문으로 판정합니다.")

sc = scenarios()
c1, c2, c3 = st.columns([2, 2, 1])
pick = c1.selectbox("시나리오", range(len(sc)), format_func=lambda i: sc[i]["name"])
keys = c2.multiselect("조직 구조", list(STRUCTURES), default=["integrated", "drama"],
                      format_func=lambda k: STRUCTURES[k].name)
max_turns = c3.slider("최대 행동 수", 6, 40, 26)
spec = sc[pick]
st.caption(spec.get("description", ""))
data_label("agent", scenario_kind(spec) + " 인물의 대사·행동은 에이전트가 지어낸 가상 장면이고, 허용·차단 판정만 실제 법령·조례를 인용합니다.")

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
data_label("agent", "아래 수치는 가상 장면을 판정한 횟수입니다. 실제 사건 통계가 아닙니다.")
summary = {STRUCTURES[k].name: {m: ("예" if v is True else "아니오" if v is False else v) for m, v in r.metrics.items()}
           for k, r in runs.items()}
st.dataframe(pd.DataFrame(summary).astype(str), width="stretch")
with st.container(border=True):
    st.markdown("**📊 분석**")
    st.markdown("\n".join(f"- {x}" for x in insights.agent_runs({STRUCTURES[k].name: r.metrics for k, r in runs.items()})))

docs = {d.id: d for d in retriever().docs}
st.markdown("""<style>
.sc {border-left: 3px solid rgba(128,128,128,.3); padding: 6px 0 6px 14px; margin: 10px 0; word-break: keep-all;}
.sc .hd {font-weight: 700; font-size: .92rem;} .sc .hd span {opacity: .55; font-weight: 500; margin-left: 6px;}
.sc .dir {font-style: italic; opacity: .7; font-size: .9rem; margin: .2rem 0;}
.sc .ln {font-size: 1rem; margin: .2rem 0;} .sc .ln b {margin-right: 6px;}
.sc .ex {font-size: .7rem; opacity: .45; margin-left: 4px;}
.sc .cap {display: inline-block; font-size: .82rem; font-weight: 600; padding: 2px 10px; border-radius: 6px; margin-top: .25rem;}
.cap-red {background: rgba(214,69,65,.13); color: #c0392b;} .cap-amber {background: rgba(230,145,20,.15); color: #b26a00;}
.sc.block {border-left-color: #d64541;}
.act {font-size: 1.1rem; font-weight: 800; margin: 22px 0 4px; color: #2a6fdb;}
</style>""", unsafe_allow_html=True)


def show_script(k: str, run):
    sc = build_script(run, spec["name"])
    st.markdown(f"### 🎬 {sc.title}")
    st.caption(sc.logline)
    with st.expander("등장인물", expanded=False):
        for n, p in sc.cast:
            st.markdown(f"**{n}** · {p}")
    for act, scenes in sc.acts:
        st.markdown(f'<div class="act">{act}</div>', unsafe_allow_html=True)
        for x in scenes:
            cls = "cap-red" if x.decision == "차단" else "cap-amber"
            cap = f'<div class="cap {cls}">[자막] {x.caption}</div>' if x.caption else ""
            if x.unhandled:
                cap += f'<div class="cap cap-red">[자막] 아무도 챙기지 않은 절차: {", ".join(x.unhandled)}</div>'
            ex = '<span class="ex">연출용 예시 대사</span>' if x.example_line else ""
            st.markdown(
                f'<div class="sc{" block" if x.decision == "차단" else ""}"><div class="hd">S#{x.no}. {x.place}'
                f'<span>{x.actor}</span></div><div class="dir">({x.direction})</div>'
                f'<div class="ln"><b>{x.actor}</b>{x.line}{ex}</div>{cap}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"**에필로그**  \n{sc.ending}")
    text = script_text(sc)
    b1, b2 = st.columns(2)
    b1.download_button("대본 내려받기 (.txt)", text, file_name=f"drama_{k}.txt", key=f"dlt-{k}", width="stretch")
    if b2.button("Claude로 각색하기", key=f"adapt-{k}", disabled=not llm_enabled(), width="stretch",
                 help=None if llm_enabled() else "ANTHROPIC_API_KEY가 있어야 합니다"):
        with st.spinner("각색 중..."):
            out, ok = adapt(text)
        st.session_state[f"adapted-{k}"] = out if ok else "각색에 실패했습니다. 잠시 뒤 다시 시도해 주세요."
    if st.session_state.get(f"adapted-{k}"):
        with st.container(border=True):
            st.markdown("**Claude 각색본** (사건 흐름과 판정은 실행 기록 그대로)")
            st.markdown(st.session_state[f"adapted-{k}"])


tab_drama, tab_log = st.tabs(["🎬 드라마 대본", "⚖️ 판정 로그"])
with tab_drama:
    data_label("agent", "대본 전체가 가상 장면입니다. 실존 인물·실제 사건 기록이 아닙니다.")
    st.caption("실행 기록을 장면(S#)으로 엮은 대본입니다. 인물이 한 행동과 막힌 행동은 기록 그대로이고, 법적 판정은 자막으로 "
               "나옵니다. 오프라인 예시 모드의 대사는 연출용 예시입니다.")
    eps = st.tabs([STRUCTURES[k].name for k in runs])
    for ep, (k, run) in zip(eps, runs.items()):
        with ep:
            show_script(k, run)

with tab_log:
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
                                    tag = f" ({d.source_tag})" if d.source_tag else ""
                                    link = f"  \n[원문 보기]({d.url})" if d.has_link else ""
                                    st.markdown(f"**{d.title}**{tag}  \n{d.text}{link}")
            st.download_button("로그 JSON 내려받기", json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
                               file_name=f"agent_run_{k}.json", mime="application/json", key=f"dl-{k}")
