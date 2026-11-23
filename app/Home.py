import pandas as pd
import streamlit as st

from common import llm_badge, retriever, simulate, structures

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
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def html(s: str):
    st.markdown(f'<div class="h-wrap">{s}</div>', unsafe_allow_html=True)


def section(n: str, title: str, sub: str = "") -> str:
    return (f'<div class="h-sec"><span class="n">{n}</span><span class="t">{title}</span>'
            f'<span class="s">{sub}</span></div>')


# 히어로: 제목 + 연구 질문
html('<div class="h-hero"><div class="tag">조직이론 팀 프로젝트 · 발표용 데모</div>'
     "<h1>교권보호국 시뮬레이터</h1>"
     '<p class="lead">경기도교육청 교권보호단 재조직을 조직이론으로 실험합니다.</p>'
     '<p class="h-q">교권보호 업무를 왜 교육감 직속·전담관 체계로 다시 짰고, 어떤 조건에서 효과가 있는가?</p>'
     "<ul><li><b>조직환경</b>: 사안이 몰릴 때 구조별로 얼마나 버티는가 (개방체계·상황이론, Burns &amp; Stalker)</li>"
     "<li><b>분업과 조정</b>: 교사가 하던 조정을 조직이 맡으면 무엇이 달라지는가 (Gulick·Thompson·Perrow)</li>"
     "</ul></div>")

S = structures()

# 01 비교하는 구조
cards = "".join(
    f'<div class="h-card"><span class="badge">{s.get("short", k)}</span><h4>{s.get("tagline", s["name"])}</h4>'
    f'<ul>{"".join(f"<li>{x}</li>" for x in s.get("points", []))}</ul></div>'
    for k, s in S.items())
html(section("01", "비교하는 네 가지 구조") + f'<div class="h-grid">{cards}</div>')

# 02 핵심 결과: 기본 설정 시뮬레이션에서 바로 계산
try:
    a, _ = simulate("A_distributed", 60, 3.0, 7, None, 1.0)
    b, _ = simulate("B_gyeonggi", 60, 3.0, 7, None, 1.0)
except Exception:
    a = b = None
if a is not None:
    stats = []
    for label, col, unit in [("종결까지", "closure_days", "근무일"), ("첫 응답까지", "first_response_h", "시간"),
                             ("교사가 찾아간 기관", "contacts", "곳"), ("같은 내용 반복 진술", "repeats", "번")]:
        va, vb = a[col].mean(), b[col].mean()
        d = (vb - va) / va * 100 if va else 0
        stats.append(f'<div class="h-card h-stat"><div class="label">{label}</div>'
                     f'<div class="val">{vb:.1f}{unit}</div><div class="from">분산 구조 {va:.1f}{unit}</div>'
                     f'<span class="chg{" up" if d > 0 else ""}">{d:+.0f}%</span></div>')
    html(section("02", "핵심 결과", "기본 설정 · 분산 구조 → 교권보호단") + f'<div class="h-grid sm">{"".join(stats)}</div>'
         '<div class="h-note">가정값 위의 사고실험입니다. 절대 수치보다 차이의 방향과 크기로 읽어 주세요. '
         "자세한 비교는 시뮬레이션 페이지에서 볼 수 있습니다.</div>")

# 03 실효성 조건
conds = "".join(
    f'<div class="h-card h-cond"><div class="num">{n}</div><div><h4>{t}</h4><p>{d}</p></div></div>'
    for n, t, d in [("1", "역할 구분", "기존 센터와의 연계절차 (조례 제17조)"),
                    ("2", "안정적 전담 인력", "상근 수와 비상근 응답성"),
                    ("3", "제도화", "업무매뉴얼 (조례 제25조)")])
html(section("03", "실효성 조건 세 가지", "시뮬레이터에서 켜고 끌 수 있음") + f'<div class="h-grid">{conds}</div>')

# 04 둘러보기 (페이지 링크)
pages = [("📊", "시뮬레이션", "시뮬레이션", "구조·조건별 수백 건 비교, 관할 지도, 분석"),
         ("🧭", "사안 추적", "사안_추적", "1호 사안이 누구를 거쳐 가는지"),
         ("🤖", "에이전트 시뮬레이션", "에이전트_시뮬레이션", "행동마다 법령·조례로 허용·차단 판정"),
         ("📚", "근거 자료", "근거_자료", "법령·매뉴얼·서식과 데이터 출처"),
         ("📈", "실측 데이터", "실측_데이터", "공공데이터 실측값과 팀 가정값 비교")]
links = "".join(f'<a class="h-card h-link" href="{p}" target="_self"><h4>{i} {t}</h4><p>{d}</p>'
                f'<div class="go">열기 →</div></a>' for i, t, p, d in pages)
html(section("04", "둘러보기") + f'<div class="h-grid sm">{links}</div>')

html(section("05", "자세히"))
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
