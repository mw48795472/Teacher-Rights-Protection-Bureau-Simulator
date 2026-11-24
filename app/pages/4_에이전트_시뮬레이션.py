import json

import pandas as pd
import streamlit as st

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다 (common·sim 을 불러오기 전에)

fresh.ensure()
from common import data_label, llm_badge, retriever, scenario_kind, scenarios
from agents.llm import llm_enabled, model_name
from agents.roles import STRUCTURES
from agents import digest, relmap
from agents.drama import adapt, build_script, script_text
from agents.runner import run_agents
from sim import insights

st.set_page_config(page_title="에이전트 시뮬레이션", page_icon="🏫", layout="wide")
llm_badge()
st.title("에이전트 시뮬레이션")
st.markdown("같은 사건을 세 가지 조직에 넣고, 인물들이 **각자 성격대로** 움직이게 해 봤어요. "
            "그때마다 컴플라이언스 에이전트가 법령·조례를 펼쳐 보고 *이게 실제로 가능한 일인지* 판정합니다.")
st.caption("궁금한 건 두 가지예요. 드라마처럼 밀어붙이면 통할까? (H6) · 전담관이 있으면 선생님이 덜 뛰어다닐까? (H1)")

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
keys = c2.multiselect("조직 구조", list(STRUCTURES), default=["integrated", "distributed", "drama"],
                      format_func=lambda k: STRUCTURES[k].name)
max_turns = c3.slider("최대 행동 수", 6, 40, 26)
spec = sc[pick]
st.caption(spec.get("description", ""))
data_label("agent", scenario_kind(spec) + " 인물의 대사·행동은 에이전트가 지어낸 가상 장면이고, 허용·차단 판정만 실제 법령·조례를 인용합니다.")

if st.button("실행", type="primary", disabled=not keys):
    # 구조끼리는 서로 독립이라 동시에 돌린다 (Claude 모드에서 대기 시간이 구조 수만큼 늘지 않게)
    from concurrent.futures import ThreadPoolExecutor
    with st.spinner(f"{len(keys)}개 구조를 동시에 실행 중..."), ThreadPoolExecutor(len(keys)) as ex:
        futs = {k: ex.submit(run_agents, spec, k, retriever(), max_turns) for k in keys}
        st.session_state["agent_runs"] = {k: f.result() for k, f in futs.items()}

runs = st.session_state.get("agent_runs", {})

# ── 인물관계도 ──
st.subheader("🗺️ 한눈에 보는 인물관계도")
map_keys = list(runs) or keys
if runs:
    st.caption("동그라미 위 숫자는 이번 실행에서 그 인물이 움직인 횟수예요. 흐린 인물은 한 번도 나서지 않았어요. 점선 동그라미의 학생들은 사건 속 인물로, 에이전트로 움직이지는 않아요.")
else:
    st.caption("실행하면 인물마다 몇 번 움직였는지 함께 표시돼요.")
st.markdown(relmap.legend_html(), unsafe_allow_html=True)
if map_keys:
    for tab, k in zip(st.tabs([STRUCTURES[k].name for k in map_keys]), map_keys):
        with tab:
            st.markdown(f"**{relmap.note(k)}**")
            st.markdown(relmap.svg(k, runs.get(k)), unsafe_allow_html=True)
            if k in runs:
                st.caption(digest.bottom_line(runs[k]))

if not runs:
    st.stop()

# ── 이론과의 대응 ──
st.subheader("🔍 이론이 예측한 대로 됐을까?")
data_label("agent", "가상 장면을 판정한 횟수예요. 실제 사건 통계가 아닙니다.")
rows = digest.theory_rows(runs)
if rows and all(r["판정"] == "부합" for r in rows):
    st.success(digest.takeaway(rows), icon="💡")
else:
    st.info(digest.takeaway(rows), icon="💡")
if rows:
    rcols = st.columns(len(rows))
    for col, r in zip(rcols, rows):
        with col, st.container(border=True):
            st.markdown(f"**{r['q']}**")
            st.markdown(f"{r['say']}")
            st.markdown(f"**{digest.VERDICT_TEXT.get(r['판정'], r['판정'])}**")
            st.caption(f"{r['가설']} · {r['이론']}  \n예측: {r['예측']}")

# ── 자세히 보기: 켰을 때만, 고른 구조 하나만 그린다 (요소 수를 줄여 화면을 가볍게) ──
st.divider()
if not st.toggle("📜 자세히 보기 (대본·판정 로그·수치)", value=False):
    st.stop()
d1, d2 = st.columns([2, 3])
dk = d1.selectbox("구조", list(runs), format_func=lambda k: STRUCTURES[k].name)
view = d2.radio("보기", ["판정 로그", "대본", "수치 표"], horizontal=True)
run = runs[dk]
docs = {d.id: d for d in retriever().docs}

if view == "판정 로그":
    rows = []
    for t in run.turns:
        a, v = t.review.action, t.review.verdict
        rows.append({"#": t.n, "인물": t.actor, "행동": a.intent, "판정": v.decision, "분류": v.category,
                     "이유": "" if v.decision == "허용" and v.category == "적법" else v.reason,
                     "근거": ", ".join(docs[c].title for c in v.cited_ids if c in docs)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.download_button("로그 JSON 내려받기", json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
                       file_name=f"agent_run_{dk}.json", mime="application/json")
elif view == "대본":
    sc_ = build_script(run, spec["name"])
    text = script_text(sc_)
    data_label("agent", "대본 전체가 가상 장면입니다. 실존 인물·실제 사건 기록이 아닙니다.")
    st.code(text, language=None, wrap_lines=True)
    b1, b2 = st.columns(2)
    b1.download_button("대본 내려받기 (.txt)", text, file_name=f"drama_{dk}.txt", width="stretch")
    if b2.button("Claude로 각색하기", disabled=not llm_enabled(), width="stretch",
                 help=None if llm_enabled() else "ANTHROPIC_API_KEY가 있어야 합니다"):
        with st.spinner("각색 중..."):
            out, ok = adapt(text)
        st.session_state[f"adapted-{dk}"] = out if ok else "각색에 실패했습니다. 잠시 뒤 다시 시도해 주세요."
    if st.session_state.get(f"adapted-{dk}"):
        st.markdown(st.session_state[f"adapted-{dk}"])
else:
    summary = {STRUCTURES[k].name: {m: ("예" if v is True else "아니오" if v is False else v) for m, v in r.metrics.items()}
               for k, r in runs.items()}
    st.dataframe(pd.DataFrame(summary).astype(str), width="stretch")
    st.markdown("\n".join(f"- {x}" for x in insights.agent_runs({STRUCTURES[k].name: r.metrics for k, r in runs.items()})))
