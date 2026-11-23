import pandas as pd
import streamlit as st

from common import llm_badge, retriever, simulate, structures

st.set_page_config(page_title="교권보호국 시뮬레이터", page_icon="🏫", layout="wide")
llm_badge()

st.markdown(
    """
<style>
.slide, .card {word-break:keep-all;}
.slide {border:1px solid rgba(128,128,128,.25); border-radius:14px; padding:22px 26px; margin:6px 0 14px;
        background: rgba(128,128,128,.04);}
.kicker {font-size:.8rem; letter-spacing:.08em; opacity:.6; font-weight:600;}
.slide h2 {font-size:1.55rem; margin:.25rem 0 .6rem; line-height:1.35;}
.slide ul {margin:0; padding-left:1.1rem;} .slide li {margin:.2rem 0; font-size:1.02rem;}
.hero h1 {font-size:2.3rem; margin:.2rem 0 .4rem;} .hero p {font-size:1.1rem; opacity:.8; margin:0;}
.card {border:1px solid rgba(128,128,128,.25); border-radius:12px; padding:16px 18px; height:100%;}
.card .badge {display:inline-block; font-size:.75rem; font-weight:700; padding:2px 8px; border-radius:999px;
              background:rgba(42,111,219,.12); color:#2a6fdb;}
.card h4 {margin:.5rem 0 .4rem; font-size:1.05rem; line-height:1.35;}
.card ul {margin:0; padding-left:1rem;} .card li {font-size:.92rem; margin:.15rem 0;}
.cond {text-align:center;} .cond .num {font-size:2rem; font-weight:800; opacity:.35;}
</style>
""",
    unsafe_allow_html=True,
)


def slide(kicker: str, headline: str, bullets: list[str]):
    items = "".join(f"<li>{b}</li>" for b in bullets)
    st.markdown(f'<div class="slide"><div class="kicker">{kicker}</div><h2>{headline}</h2><ul>{items}</ul></div>',
                unsafe_allow_html=True)


st.markdown('<div class="slide hero"><div class="kicker">조직이론 팀 프로젝트 · 발표용 데모</div>'
            "<h1>교권보호국 시뮬레이터</h1>"
            "<p>경기도교육청 교권보호단 재조직을 조직이론으로 실험합니다.</p></div>", unsafe_allow_html=True)

slide("01 · 질문", "교권보호 업무를 왜 교육감 직속·전담관 체계로 다시 짰고, 어떤 조건에서 효과가 있는가?", [
    "<b>조직환경</b>: 사안이 몰릴 때 구조별로 얼마나 버티는가 (개방체계·상황이론, Burns &amp; Stalker)",
    "<b>분업과 조정</b>: 교사가 하던 조정을 조직이 맡으면 무엇이 달라지는가 (Gulick·Thompson·Perrow)",
])

# 03 핵심 결과: 기본 설정 시뮬레이션에서 바로 계산
S = structures()
try:
    a, _ = simulate("A_distributed", 60, 3.0, 7, None, 1.0)
    b, _ = simulate("B_gyeonggi", 60, 3.0, 7, None, 1.0)
    have = True
except Exception:
    have = False

st.markdown('<div class="kicker" style="margin-top:8px">02 · 비교하는 네 가지 구조</div>', unsafe_allow_html=True)
cols = st.columns(len(S))
for col, (k, s) in zip(cols, S.items()):
    with col:
        pts = "".join(f"<li>{x}</li>" for x in s.get("points", []))
        st.markdown(f'<div class="card"><span class="badge">{s.get("short", k)}</span>'
                    f'<h4>{s.get("tagline", s["name"])}</h4><ul>{pts}</ul></div>', unsafe_allow_html=True)

st.markdown('<div class="kicker" style="margin-top:22px">03 · 핵심 결과 (기본 설정, 분산 구조 → 교권보호단)</div>',
            unsafe_allow_html=True)
if have:
    m = [("종결까지", "closure_days", "근무일"), ("첫 응답까지", "first_response_h", "시간"),
         ("교사가 찾아간 기관", "contacts", "곳"), ("같은 내용 반복 진술", "repeats", "번")]
    mc = st.columns(4)
    for c, (label, col, unit) in zip(mc, m):
        va, vb = a[col].mean(), b[col].mean()
        c.metric(label, f"{vb:.1f}{unit}", f"{(vb - va) / va * 100:+.0f}% (분산 {va:.1f}{unit})" if va else None,
                 delta_color="inverse", border=True)
    st.caption("가정값 위의 사고실험입니다. 절대 수치보다 차이의 방향과 크기로 읽어 주세요. 자세한 비교는 시뮬레이션 페이지에서.")

st.markdown('<div class="kicker" style="margin-top:18px">04 · 실효성 조건 세 가지 (시뮬레이터에서 켜고 끔)</div>',
            unsafe_allow_html=True)
cc = st.columns(3)
for c, (n, t, d) in zip(cc, [("①", "역할 구분", "기존 센터와의 연계절차<br>(조례 제17조)"),
                             ("②", "안정적 전담 인력", "상근 수, 비상근 응답성"),
                             ("③", "제도화", "업무매뉴얼<br>(조례 제25조)")]):
    c.markdown(f'<div class="card cond"><div class="num">{n}</div><h4>{t}</h4><div>{d}</div></div>',
               unsafe_allow_html=True)

st.markdown('<div class="kicker" style="margin-top:22px">05 · 둘러보기</div>', unsafe_allow_html=True)
nc = st.columns(4)
for c, (icon, t, d) in zip(nc, [("📊", "시뮬레이션", "구조·조건별 수백 건 비교, 지도, 분석"),
                                ("🧭", "사안 추적", "1호 사안이 누구를 거쳐 가는지"),
                                ("🤖", "에이전트 시뮬레이션", "행동마다 법령·조례로 허용·차단 판정"),
                                ("📚", "근거 자료", "법령·매뉴얼·조례와 데이터 출처")]):
    c.markdown(f'<div class="card"><h4>{icon} {t}</h4><div style="font-size:.92rem">{d}</div></div>',
               unsafe_allow_html=True)

st.write("")
with st.expander("구조별 자세한 정의"):
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


with st.expander("한눈에 비교 (설정값)"):
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

n = len(retriever().docs)
unverified = sum(not d.verified for d in retriever().docs)
st.caption(f"지식베이스 문서 {n}개 중 {unverified}개는 팀 요약입니다. 처리시간·확률 대부분은 가정값이므로 "
           "결과는 이론의 논리를 보여주는 사고실험으로 다뤄 주세요.")
