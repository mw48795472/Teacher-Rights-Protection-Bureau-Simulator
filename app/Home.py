import pandas as pd
import streamlit as st
import yaml

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다 (common·sim 을 불러오기 전에)

fresh.ensure()
from common import ROOT, llm_badge, retriever, simulate, structures
from sim import hypotheses as H

st.set_page_config(page_title="교권보호국 시뮬레이터", page_icon="🏫", layout="wide")
llm_badge()

CSS = """
<style>
.block-container {max-width: 1100px;}
.h-wrap, .h-wrap * {word-break: keep-all;}
.h-hero {padding: 28px 30px; border-radius: 16px; margin: 4px 0 28px;
         background: linear-gradient(135deg, rgba(42,111,219,.10), rgba(42,111,219,.02));
         border: 1px solid rgba(42,111,219,.18);}
.h-hero .tag {font-size: .8rem; font-weight: 600; letter-spacing: .06em; opacity: .65;}
.h-hero h1 {font-size: 2.2rem; line-height: 1.25; margin: .35rem 0 .5rem; padding: 0;}
.h-hero .lead {font-size: 1.05rem; opacity: .8; margin: 0 0 1.1rem;}
.h-q {font-size: 1.15rem; font-weight: 700; line-height: 1.5; margin: 0 0 .6rem;}
.h-hero ul {margin: 0; padding-left: 1.1rem;} .h-hero li {margin: .2rem 0; font-size: .98rem;}
.h-sec {display: flex; align-items: baseline; gap: 10px; margin: 30px 0 12px;
        border-bottom: 1px solid rgba(128,128,128,.2); padding-bottom: 6px;}
.h-sec .n {font-size: .85rem; font-weight: 700; color: #2a6fdb;}
.h-sec .t {font-size: 1.2rem; font-weight: 700;}
.h-sec .s {font-size: .85rem; opacity: .6; margin-left: auto;}
.h-grid {display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));}
.h-grid.sm {grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));}
.h-card {border: 1px solid rgba(128,128,128,.22); border-radius: 12px; padding: 16px 18px;
         background: rgba(128,128,128,.03); display: flex; flex-direction: column;}
.h-card .badge {align-self: flex-start; font-size: .75rem; font-weight: 700; padding: 2px 9px;
                border-radius: 999px; background: rgba(42,111,219,.12); color: #2a6fdb;}
.h-card h4 {font-size: 1.02rem; line-height: 1.4; margin: .55rem 0 .45rem; padding: 0;}
.h-card ul {margin: 0; padding-left: 1rem;} .h-card li {font-size: .9rem; margin: .15rem 0; opacity: .9;}
.h-card p {font-size: .9rem; margin: 0; opacity: .85;}
.h-stat .label {font-size: .88rem; opacity: .7;}
.h-stat .val {font-size: 1.9rem; font-weight: 700; line-height: 1.2; margin: .3rem 0 .2rem;}
.h-stat .from {font-size: .85rem; opacity: .7;}
.h-stat .chg {display: inline-block; font-size: .8rem; font-weight: 700; padding: 1px 8px; border-radius: 999px;
              background: rgba(33,150,83,.13); color: #1f8a4c; margin-top: .4rem; align-self: flex-start;}
.h-stat .chg.up {background: rgba(214,69,65,.13); color: #c0392b;}
.h-cond {flex-direction: row; gap: 14px; align-items: flex-start;}
.h-cond .num {font-size: 1.6rem; font-weight: 800; color: #2a6fdb; opacity: .6; line-height: 1;}
.h-cond h4 {margin-top: 0;}
a.h-link {text-decoration: none; color: inherit; transition: border-color .15s, transform .15s;}
a.h-link:hover {border-color: #2a6fdb; transform: translateY(-2px);}
a.h-link .go {margin-top: auto; padding-top: .6rem; font-size: .85rem; font-weight: 600; color: #2a6fdb;}
.h-note {font-size: .85rem; opacity: .6; margin-top: 8px;}
.h-hero .ans {margin-top: 1rem; padding: 12px 16px; border-radius: 10px; background: rgba(255,255,255,.55);
              border-left: 4px solid #2a6fdb; font-size: .98rem; line-height: 1.6;}
@media (prefers-color-scheme: dark) {.h-hero .ans {background: rgba(0,0,0,.2);}}
.h-hero .ans b {color: #2a6fdb;}
.h-grid.wide {grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));}
.h-concept h3 {font-size: 1.15rem; margin: 0 0 .15rem; padding: 0;}
.h-concept .asks {font-size: .88rem; opacity: .65; margin-bottom: .7rem;}
.h-th {padding: 10px 0; border-top: 1px dashed rgba(128,128,128,.25);}
.h-th .nm {font-weight: 700; font-size: .98rem;} .h-th .who {font-size: .82rem; opacity: .6; margin-left: 6px;}
.h-th .cl {font-size: .9rem; margin: .25rem 0 .2rem;}
.h-th .ap {font-size: .88rem; opacity: .8;} .h-th .ap:before {content: "→ "; color: #2a6fdb; font-weight: 700;}
.h-hyp {font-size: .72rem; font-weight: 700; padding: 1px 7px; border-radius: 999px; margin-left: 6px;
        border: 1px solid rgba(42,111,219,.4); color: #2a6fdb; vertical-align: 1px;}
.h-h .top {display: flex; align-items: center; gap: 8px; margin-bottom: .45rem;}
.h-h .id {font-weight: 800; color: #2a6fdb; font-size: 1.05rem;}
.h-h .th {font-size: .8rem; opacity: .65;}
.h-h .v {margin-left: auto; font-size: .78rem; font-weight: 700; padding: 2px 9px; border-radius: 999px;}
.v-ok {background: rgba(33,150,83,.14); color: #1f8a4c;} .v-part {background: rgba(230,145,20,.16); color: #b26a00;}
.v-no {background: rgba(214,69,65,.14); color: #c0392b;} .v-na {background: rgba(128,128,128,.15);}
.h-h .claim {font-size: .95rem; font-weight: 600; line-height: 1.5; margin: 0 0 .5rem;}
.h-h .meta {font-size: .82rem; opacity: .65; margin-bottom: .35rem;}
.h-h .ev {font-size: .88rem; padding: 7px 10px; border-radius: 8px; background: rgba(128,128,128,.07);}
.h-h .note {font-size: .84rem; opacity: .8; margin-top: .45rem;}
.h-h .go {margin-top: auto; padding-top: .55rem; font-size: .84rem; font-weight: 600; color: #2a6fdb; text-decoration: none;}
.h-flow {display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0 0 4px; font-size: .85rem;}
.h-flow span {padding: 3px 10px; border-radius: 999px; background: rgba(42,111,219,.10); color: #2a6fdb; font-weight: 600;}
.h-flow i {opacity: .5; font-style: normal;}
.h-limits li {font-size: .9rem; margin: .25rem 0; opacity: .85;}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)
T = yaml.safe_load((ROOT / "config" / "theory.yaml").read_text(encoding="utf-8"))
S = structures()
LINK = {"시뮬레이션": "시뮬레이션", "에이전트 시뮬레이션": "에이전트_시뮬레이션"}


def html(s: str):
    st.markdown(f'<div class="h-wrap">{s}</div>', unsafe_allow_html=True)


def section(n: str, title: str, sub: str = "") -> str:
    return (f'<div class="h-sec"><span class="n">{n}</span><span class="t">{title}</span>'
            f'<span class="s">{sub}</span></div>')


# ── 연구 질문과 답 ──
html('<div class="h-hero"><div class="tag">조직이론 팀 프로젝트 · 경기도교육청 교권보호단 사례</div>'
     "<h1>교권보호국 시뮬레이터</h1>"
     f'<p class="h-q">{T["question"]}</p></div>')

# ── 01 이론 틀 ──
panels = []
for c in T["concepts"]:
    items = "".join(
        f'<div class="h-th"><span class="nm">{t["name"]}</span><span class="who">{t["who"]}</span>'
        + (f'<span class="h-hyp">{t["hyp"]}</span>' if t.get("hyp") else "")
        + f'<div class="cl">{t["claim"]}</div><div class="ap">{t["apply"]}</div></div>'
        for t in c["theories"])
    panels.append(f'<div class="h-card h-concept"><h3>개념 {c["num"]} {c["title"]}</h3>'
                  f'<div class="asks">{c["asks"]}</div>{items}</div>')
html(section("01", "이론 틀: 수업 개념 두 가지", "→ 이론마다 검증할 가설 번호") +
     f'<div class="h-grid wide">{"".join(panels)}</div>')

# ── 02 가설과 검증 (기본 설정 시뮬레이션으로 바로 판정) ──
SURGE_DAY = 20
try:
    base = {k: simulate(k, 60, 3.0, 7, None, 1.0)[0] for k in S}
    surge = {k: simulate(k, 60, 3.0, 7, SURGE_DAY, 2.0)[0] for k in ("A_distributed", "B_gyeonggi")}
    verdicts = {
        "H1": H.h1(base["A_distributed"], base["B_gyeonggi"]),
        "H2": H.h2(base["A_distributed"], base["B_gyeonggi"]),
        "H3": H.h3(surge["A_distributed"], surge["B_gyeonggi"], SURGE_DAY),
        "H4": H.h4(base["B0_gyeonggi_launch"], base["B_gyeonggi"]),
        "H5": H.h5(base["B_gyeonggi"], base["C_incheon"]),
    }
except Exception:
    base, verdicts = None, {}
verdicts.setdefault("H6", ("페이지에서 실행", "행동마다 법령·조례 근거로 허용·조건부 허용·차단을 판정합니다. "
                           "드라마식 '물리적 제지'와 '직접 사실조사'가 권한 초과로 막히는지 확인합니다."))
NOTES = {  # 지지되지 않거나 부분 지지일 때 읽는 법
    "H3": "교권보호단도 상근 전담관 수가 고정이라 급증 때 주 담당 대기가 쌓입니다. 분산 구조는 원래 위원회 대기가 "
          "길어 급증 영향이 묻힙니다. 유기적 구조의 이점은 인력을 사안에 다시 묶을 수 있을 때 나타난다는 해석이 "
          "가능합니다 (시뮬레이션 사이드바에서 상근 인원을 바꿔 확인).",
    "H5": "인수인계는 줄지만 인천형은 전문가 풀이 작아(가정) 대기가 길어집니다. 인력의 안정성과 규모 사이의 "
          "상충으로, 적합성은 구조 하나가 아니라 인력 구성과 함께 정해진다는 Van de Ven의 주장과 맞닿아 있습니다.",
}
CLS = {H.SUPPORT: "v-ok", H.PARTIAL: "v-part", H.NOT: "v-no"}
cards = []
for h in T["hypotheses"]:
    v, ev = verdicts.get(h["id"], ("계산 실패", ""))
    note = NOTES.get(h["id"]) if v in (H.PARTIAL, H.NOT) else ""
    page = h["page"].split(" (")[0]
    cards.append(
        f'<div class="h-card h-h"><div class="top"><span class="id">{h["id"]}</span>'
        f'<span class="th">개념 {h["concept"]} · {h["theory"]}</span>'
        f'<span class="v {CLS.get(v, "v-na")}">{v}</span></div>'
        f'<p class="claim">{h["claim"]}</p><div class="meta">비교: {h["compare"]}</div>'
        f'<div class="ev">{ev}</div>' + (f'<div class="note">{note}</div>' if note else "")
        + f'<a class="go" href="{LINK.get(page, page)}" target="_self">{h["page"]}에서 보기 →</a></div>')
html(section("02", "가설과 검증", "기본 설정 · 60일 · 하루 3건 · 시드 7") +
     f'<div class="h-grid wide">{"".join(cards)}</div>'
     '<div class="h-note">판정은 기본 설정 시뮬레이션 결과를 규칙으로 읽은 것입니다. 가정값 위의 사고실험이므로 '
     "구조 간 차이의 방향으로 읽어 주세요.</div>")

# ── 03 실험 조건: 네 가지 구조 ──
cards = "".join(
    f'<div class="h-card"><span class="badge">{s.get("short", k)}</span><h4>{s.get("tagline", s["name"])}</h4>'
    f'<ul>{"".join(f"<li>{x}</li>" for x in s.get("points", []))}</ul></div>'
    for k, s in S.items())
html(section("03", "실험 조건: 비교하는 네 가지 구조", "같은 사안 흐름을 네 구조에 똑같이 넣음") +
     f'<div class="h-grid">{cards}</div>')

# ── 04 결론: 실효성 조건과 한계 ──
conds = "".join(
    f'<div class="h-card h-cond"><div class="num">{n}</div><div><h4>{t}</h4><p>{d}</p></div></div>'
    for n, t, d in [("1", "역할 구분", "기존 센터와의 연계절차 (조례 제17조) · H4"),
                    ("2", "안정적 전담 인력", "상근 수와 비상근 응답성 · H5"),
                    ("3", "제도화", "업무매뉴얼 (조례 제25조)과 성과평가 · H4")])
limits = "".join(f"<li>{x}</li>" for x in T["limits"])
html(section("04", "결론: 실효성 조건과 한계", "시뮬레이터에서 조건을 켜고 끌 수 있음") +
     f'<div class="h-grid">{conds}</div>'
     f'<div class="h-card" style="margin-top:12px"><h4>한계</h4><ul class="h-limits">{limits}</ul></div>')

# ── 05 둘러보기 ──
pages = [("📊", "시뮬레이션", "시뮬레이션", "H1~H5: 구조·조건별 수백 건 비교, 관할 지도, 분석"),
         ("🧭", "사안 추적", "사안_추적", "1호 사안이 위원회 절차(서식 1~15)를 거치는 과정"),
         ("🤖", "에이전트 시뮬레이션", "에이전트_시뮬레이션", "H6: 행동마다 법령·조례로 허용·차단 판정"),
         ("📚", "근거 자료", "근거_자료", "법령·매뉴얼·서식, 데이터 출처와 API 상태")]
links = "".join(f'<a class="h-card h-link" href="{p}" target="_self"><h4>{i} {t}</h4><p>{d}</p>'
                f'<div class="go">열기 →</div></a>' for i, t, p, d in pages)
html(section("05", "둘러보기") + f'<div class="h-grid sm">{links}</div>')

html(section("06", "자세히"))
tab_def, tab_cmp, tab_terms = st.tabs(["구조별 정의", "설정값 비교", "용어 정리"])
with tab_def:
    for k, s in S.items():
        st.markdown(f"**{s['name']}**  \n{s.get('definition', s['description'])}")
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


with tab_cmp:
    st.dataframe(pd.DataFrame([_row(s) for s in S.values()]).set_index("구조").T, width="stretch")
    st.caption("인원·응답 비율·개최 간격 중 출처가 없는 값은 가정값이며 시뮬레이션 사이드바에서 바꿀 수 있습니다.")

with tab_terms:
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

n = len(retriever().docs)
unverified = sum(not d.verified for d in retriever().docs)
st.write("")
st.caption(f"지식베이스 문서 {n}개 중 {unverified}개는 팀 요약입니다. 처리시간·확률 대부분은 가정값이므로 "
           "결과는 이론의 논리를 보여주는 사고실험으로 다뤄 주세요.")
