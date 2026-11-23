import pandas as pd
import streamlit as st
import yaml

from common import ROOT, llm_badge, neis_status, retriever, schools
from rag.answer import answer

st.set_page_config(page_title="근거 자료", page_icon="🏫", layout="wide")
llm_badge()
st.title("근거 자료")
st.caption("시뮬레이터의 각 행동이 인용하는 조례·정책·기사·이론 자료입니다.")

st.subheader("주요 정책 자료 및 매뉴얼")
RES = yaml.safe_load((ROOT / "config" / "resources.yaml").read_text(encoding="utf-8"))
RES_DIR = ROOT / "data" / "resources"


def resource_card(item: dict, icon: str, i: int):
    with st.container(border=True):
        st.markdown(f"{icon} **{item['title']}**" + (f"  \n<small>{item['org']}</small>" if item.get("org") else ""),
                    unsafe_allow_html=True)
        st.caption(item["desc"])
        f = RES_DIR / item["file"] if item.get("file") else None
        b1, b2 = st.columns(2)
        if item.get("url"):
            b1.link_button("원문 보기", item["url"], width="stretch")
        if f and f.exists():
            b2.download_button("파일 내려받기", f.read_bytes(), file_name=f.name, key=f"res-{icon}-{i}",
                               width="stretch")
        elif f and not item.get("url"):
            st.caption(":orange[자료 필요: 공식 파일을 받으면 넣을 자리입니다.]")


for (key, icon, label) in (("manuals", "📘", "매뉴얼·안내"), ("laws", "⚖️", "법령 정보"), ("forms", "📝", "공식 서식")):
    st.markdown(f"#### {icon} {label}")
    items = RES.get(key, [])
    cols = st.columns(3)
    for i, item in enumerate(items):
        with cols[i % 3]:
            resource_card(item, icon, i)
st.caption("링크는 국가법령정보센터와 경기교권보호지원센터 공식 페이지입니다. 서식·매뉴얼 파일은 "
           "`data/resources/`에 넣으면 내려받기 버튼이 생깁니다.")

st.subheader("근거 자료 검색")

# 지식베이스(조례·교육부 자료·보도·해외 사례)로 답이 나오는 질문들. 누르면 검색 칸에 들어가 바로 검색된다.
EXAMPLES = {
    "전담관·교권보호단": [
        "전담관이 교육활동 침해 여부를 직접 판단할 수 있나요?",
        "교권보호전담관은 어떤 업무를 하나요?",
        "교권보호단은 기존 교육활동보호센터와 어떻게 연계하나요?",
    ],
    "절차·조치": [
        "교원이 아동학대로 신고되면 교육감 의견은 어떻게 제출하나요?",
        "지역교권보호위원회는 어떤 절차로 심의하나요?",
        "수업을 방해하는 학생을 분리할 수 있나요?",
    ],
    "민원·현장 대응": [
        "악성 민원에 교육청은 어떻게 대응하나요?",
        "중대 사안이 생기면 누가 현장에 출동하나요?",
        "프랑스는 교사 보호를 어떻게 조직하나요?",
    ],
}
st.session_state.setdefault("evidence_q", EXAMPLES["전담관·교권보호단"][0])


def _ask(question: str) -> None:
    st.session_state["evidence_q"] = question


st.caption("예시 질문을 누르면 바로 검색합니다.")
for col, (group, qs) in zip(st.columns(len(EXAMPLES)), EXAMPLES.items()):
    with col:
        st.markdown(f"**{group}**")
        for i, eq in enumerate(qs):
            st.button(eq, key=f"ex-{group}-{i}", on_click=_ask, args=(eq,), width="stretch")

q = st.text_input("질문", key="evidence_q")
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

# ── 전체 데이터 출처와 API 키 상태 ──
import os  # noqa: E402

from collector import assembly, gg_data  # noqa: E402
from collector.pipeline import load_sources  # noqa: E402
from sim.calibration import data_sources_table  # noqa: E402

with st.expander("전체 데이터 출처 표"):
    src = data_sources_table()
    if not src.empty:
        src["링크"] = src["링크"].where(src["링크"].str.startswith("http"), None)
        st.dataframe(src, hide_index=True, width="stretch",
                     column_config={"링크": st.column_config.LinkColumn("링크", display_text="열기")})
        st.caption("목록은 `config/data_sources.yaml`에 있습니다.")


@st.cache_data(ttl=3600, show_spinner="API 키 확인 중…")
def _key_status() -> tuple[list[dict], list[dict]]:
    gg, asm = gg_data.check_key(), assembly.check_key()
    bills = [d.to_dict() for d in assembly.cached_bills(load_sources().get("bills"))] if asm["ok"] else []

    def row(name, key, ok, reason):
        return {"서비스": name, "키": key, "상태": "정상" if ok else "미연결", "비고": reason}
    rows = [row("국가법령정보센터", "LAW_OC", bool(os.environ.get("LAW_OC")), "설정됨" if os.environ.get("LAW_OC") else "없음 (팀 요약 사용)"),
            row("NEIS 교육정보 개방포털", "NEIS_KEY", ns["ok"], "대조 완료" if ns["ok"] else ns["reason"]),
            row("경기데이터드림", "GG_DATA_KEY", gg["ok"], gg["reason"]),
            row("열린국회정보", "ASSEMBLY_KEY", asm["ok"], f"법률안 {len(bills)}건" if asm["ok"] else asm["reason"]),
            row("Claude API", "ANTHROPIC_API_KEY", bool(os.environ.get("ANTHROPIC_API_KEY")),
                "설정됨" if os.environ.get("ANTHROPIC_API_KEY") else "없음 (규칙 기반 요약)")]
    return rows, bills


with st.expander("API 키 연결 상태"):
    keys, bills = _key_status()
    st.dataframe(pd.DataFrame(keys), hide_index=True, width="stretch")
    st.caption("키는 `.env` 또는 Streamlit Secrets에 넣습니다. 키 값은 화면에 나오지 않습니다.")
    if bills:
        st.markdown("**근거 자료에 넣은 국회 법률안**")
        st.dataframe(pd.DataFrame([{"제안일": b["meta"].get("propose_dt"), "법률안": b["title"].split(" [")[0],
                                    "대표발의": b["meta"].get("proposer"), "단계": b["meta"].get("stage"),
                                    "링크": b["url"]} for b in bills]),
                     hide_index=True, width="stretch",
                     column_config={"링크": st.column_config.LinkColumn("링크", display_text="의안정보")})
