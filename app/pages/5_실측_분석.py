import plotly.express as px
import streamlit as st

import fresh  # noqa: E402  새 배포 뒤 낡은 모듈을 먼저 다시 읽는다

fresh.ensure()
from common import data_label, llm_badge  # noqa: E402
from sim import trends as tr  # noqa: E402

st.set_page_config(page_title="실측 분석", page_icon="📊", layout="wide")
llm_badge()
st.title("실측 분석")
st.caption("저장소에 있는 공공 원자료만으로 계산합니다. 가정값이나 합성 데이터는 쓰지 않습니다. "
           "자료가 아직 없는 분석은 자리만 두고, 파일이 들어오면 자동으로 채워집니다.")
data_label("real", "이 화면의 모든 값은 공공 원자료 또는 보도된 공식 집계입니다. 보도 값은 신뢰도 C로 따로 표시합니다.")

t1, t2, t3, t4, t5, t6 = st.tabs(["① 추세·교권5법 전후", "② 교원 1천 명당", "③ 시도 비교 (2024)",
                                  "④ 아동학대 신고 흐름", "⑤ 교권보호단 출범 효과", "⑥ 시도교육청 재정"])

with t1:
    tot = tr.committee_totals()
    st.plotly_chart(px.bar(tot, x="학년도", y="건수", color="출처", text="건수",
                           title="교권보호위원회 심의 건수"), width="stretch")
    st.caption("2019~2023: 교육부 「교권보호위원회 개최 현황」·「교육활동 침해 현황」. 2024~2025: 한국교육개발원 교육정책포럼 수치(연합뉴스 2026.9.4. 보도). "
               "2024.3.부터 교육지원청 지역교권보호위원회로 이관되어 2023 이전과 바로 비교하기 어렵습니다. 2020년 급감은 원격수업 영향으로 해석됩니다.")
    ty = tr.types_by_year()
    st.plotly_chart(px.bar(ty, x="학년도", y="비율(%)", color="유형", title="침해 유형 구성 (2020~2023)",
                           hover_data=["건수"]), width="stretch")
    st.markdown("**2022 대 2023학년도 유형별 변화** (교권5법·교육활동 침해 고시가 2023.9.에 시행된 해)")
    st.dataframe(tr.law5_compare(), hide_index=True, width="stretch")
    st.info("한계: 원자료가 학년도(3월~이듬해 2월) 단위라 2023년 9월 전후를 나눌 수 없습니다. "
            "2023학년도의 '교육활동 방해'(1,147건, 22.7%)는 2023.9. 고시로 새로 생긴 유형이라, 늘어난 건수의 상당 부분이 "
            "새 유형으로 잡힌 사안입니다. 월별 자료는 교육부 정보공개청구로 받을 수 있습니다.")

with t2:
    tc = tr.sido_teachers()
    with st.expander("연결 상태 (KOSIS)"):
        from collector import kosis as _kosis
        _ks = st.cache_data(ttl=3600, show_spinner=False)(_kosis.status)() if tc.empty else {"ok": True, "reason": f"교원 수 {len(tc)}행 사용 중"}
        st.write(("✅ " if _ks["ok"] else "⚠️ ") + _ks["reason"] + (f" · {_ks['table']}" if _ks.get("table") else ""))
    if tc.empty:
        st.warning("시도별 교원 수 자료가 아직 없습니다. KESS(kess.kedi.re.kr)에서 시도별 교원 수를 받아 "
                   "`data/measured/sido_teachers.csv`(열: 시도, 연도, 교원수)로 넣거나, "
                   "Streamlit Secrets에 `KOSIS_KEY`를 넣고 `config/kosis.yaml`에 통계표 ID를 적으면 앱이 직접 받아 채웁니다.")
    else:
        s = tr.sido_2024()
        col = "1천 명당 (3개월)"
        st.plotly_chart(px.bar(s.sort_values(col, ascending=False), x="시도", y=col,
                               title="교원 1천 명당 지역교보위 심의 건수 (2024.3.28~6.30)"), width="stretch")
        st.dataframe(s, hide_index=True, width="stretch")
        _lv = [c for c in ("유치원", "초등학교", "중학교", "고등학교", "특수학교") if c in tc.columns]
        st.caption("출처: 심의 건수는 의원실 발표 보도, 교원 수는 "
                   + (f"KOSIS e-지방지표 {'+'.join(_lv)} 교원 수 합계." if _lv else "KESS·KOSIS."))

with t3:
    s = tr.sido_2024()
    st.plotly_chart(px.bar(s, x="시도", y="2024.3.28~6.30", text="2024.3.28~6.30",
                           title="시도별 지역교권보호위원회 심의 건수 (2024.3.28~6.30, 17개 시도)"),
                    width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        full = s.dropna(subset=["2024년"])
        st.plotly_chart(px.bar(full, x="시도", y="2024년", text="2024년", title="2024년 전체 (보도에 나온 시도만)"),
                        width="stretch")
    with c2:
        ia = tr.incheon_actor()
        st.plotly_chart(px.bar(ia.melt(id_vars="침해 주체", value_vars=["인천 비율(%)", "전국 비율(%)"],
                                       var_name="구분", value_name="비율(%)"),
                               x="침해 주체", y="비율(%)", color="구분", barmode="group",
                               title="침해 주체: 인천 대 전국 (2024)"), width="stretch")
    st.caption("출처: 2024.3.28~6.30은 교육부 제출 자료(정성국 의원실·한국교총 발표), 2024년 전체와 인천 주체는 "
               "17개 시·도교육청 제출 자료(백승아 의원실 발표)를 보도한 기사. 원자료가 공개되지 않아 신뢰도 C입니다. "
               "건수만으로는 시도 규모 차이를 반영하지 못하므로 ② 교원 1천 명당 값과 함께 보세요.")

with t4:
    fl = tr.abuse_flow()
    if not fl.empty:
        long = fl.melt(id_vars="연도", value_vars=["기소", "불기소", "보호사건"], var_name="처분", value_name="인원·건")
        st.plotly_chart(px.bar(long, x="연도", y="인원·건", color="처분",
                               title="아동학대 검거 후 처분 (전국, 경찰청 2016~2023)"), width="stretch")
    ab = tr.abuse_reports_national()
    if not ab.empty:
        st.plotly_chart(px.line(ab.melt(id_vars="연도", value_vars=["전국", "경기"], var_name="지역", value_name="건수"),
                                x="연도", y="건수", color="지역", markers=True,
                                title="아동학대 판단 사례 (보건복지부 2015~2024)"), width="stretch")
    st.markdown("**처분 구성 비교: 전체 아동학대 사건 대 교원 대상 신고**")
    cmp = tr.abuse_compare()
    st.dataframe(cmp, hide_index=True, width="stretch")
    st.plotly_chart(px.bar(cmp.melt(id_vars="구분", var_name="처분", value_name="비율(%)"), y="구분", x="비율(%)",
                           color="처분", orientation="h"), width="stretch")
    st.info("교원 대상 신고는 종결 148건 중 불기소·수사개시 전 종결이 약 76%로, 전체 아동학대 사건의 불기소 비율(약 17%)보다 "
            "훨씬 높습니다. 다만 단위(사건 대 인원)와 기간이 다르고 교원 대상 자료는 7개월치라, 방향을 보는 참고값입니다. "
            "보건복지부 자료는 전체 아동 대상이며 교원 대상 신고만 따로 뽑은 통계가 아닙니다.")

with t5:
    le = tr.launch_effect()
    if le.empty:
        st.warning("경기도교육청 정보공개청구 답변(사안별 접수일·종결일)이 아직 없습니다. 받은 파일을 "
                   "`data/measured/claims/gyeonggi_cases.csv`(열: 접수일, 종결일, 유형, 침해 주체, 교육지원청 …)로 넣으면 "
                   "교권보호단 출범(2026.8.) 전후 처리 기간을 비교합니다. 인천 자료가 오면 비교군으로 붙입니다.")
    else:
        st.dataframe(le, hide_index=True, width="stretch")
        st.caption("출처: 경기도교육청 정보공개청구 답변.")


@st.cache_data(ttl=86400, show_spinner="지방교육재정알리미에서 받는 중…")
def _budget():
    return tr.edufin_budget()


with t6:
    st.caption("시도교육청 결산 공시(지방교육재정알리미)입니다. 교권 관련 사업명이 있으면 그 행을, 없으면 시도별 재정 규모를 "
               "시도×연도 패널 분석의 통제변수로 씁니다.")
    bd, status = _budget()
    with st.expander("연결 상태 (지방교육재정알리미)"):
        from collector import edufin as _edufin
        _es = st.cache_data(ttl=3600, show_spinner=False)(_edufin.check)()
        st.write(("✅ " if _es["ok"] else "⚠️ ") + _es["reason"])
        if _es.get("columns"):
            st.caption("응답 칸: " + ", ".join(map(str, _es["columns"])))
    if status == "no_key":
        st.warning("지방교육재정알리미 인증키가 없습니다. Streamlit Secrets에 `EDUFIN_KEY`를 넣으면 이 칸이 채워집니다.")
    elif status == "ok":
        st.dataframe(bd, hide_index=True, width="stretch")
        st.caption("출처: 지방교육재정알리미 Open API (한국교육학술정보원). 사업명 키워드로 거른 값이라 "
                   "다른 이름으로 편성된 교권보호 예산은 빠질 수 있습니다.")
    elif status == "no_keyword":
        st.info("받은 결산 공시에는 교권보호 사업이 따로 나오지 않아 교권보호단 예산 규모는 알 수 없습니다. "
                "대신 시도교육청 재정 규모를 교권 지표의 비교 기준(통제변수)으로 씁니다.")
        fd, meta = tr.edufin_frame(bd)
        if fd.empty or not meta.get("nums"):
            st.caption("받은 칸에서 시도·금액 칸을 찾지 못했습니다. 받은 칸: " + ", ".join(map(str, bd.columns)))
        else:
            c1, c2, c3 = st.columns(3)
            value = c1.selectbox("금액 칸", meta["nums"])
            filters = {}
            if meta["cats"]:
                cat = c2.selectbox("구분 칸 (선택)", ["(전체 합계)"] + meta["cats"])
                if cat != "(전체 합계)":
                    filters[cat] = c3.selectbox("구분 값", sorted(fd[cat].astype(str).unique()))
            fis = tr.edufin_by_sido(fd, value, filters)
            if fis["연도"].notna().any():
                st.plotly_chart(px.line(fis.dropna(subset=["연도"]), x="연도", y=value, color="시도", markers=True,
                                        title=f"시도교육청별 {value} 추이"), width="stretch")
            else:
                st.plotly_chart(px.bar(fis.sort_values(value, ascending=False), x="시도", y=value,
                                       title=f"시도교육청별 {value}"), width="stretch")
            cv = tr.committee_vs_fiscal(fis, value)
            if not cv.empty:
                st.markdown("**교권보호위원회 심의 건수와 재정 규모 (2024)**")
                reg, rt = tr.fiscal_regression(cv, value)
                fig = px.scatter(cv, x=value, y="심의 건수 (2024.3.28~6.30)", text="시도",
                                 title="재정 규모가 큰 시도일수록 심의 건수도 많은가")
                if reg:
                    xs = cv[value].sort_values()
                    fig.add_scatter(x=xs, y=reg["intercept"] + reg["slope"] * xs / 1e12, mode="lines",
                                    name="회귀선", line=dict(dash="dash"))
                st.plotly_chart(fig, width="stretch")
                if reg:
                    st.markdown("**단순 회귀분석: 심의 건수 = a + b × 재정(조원)**")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("기울기 b (재정 1조원당 건)", f"{reg['slope']:.1f}", help=f"표준오차 {reg['se']:.1f}")
                    m2.metric("R²", f"{reg['r2']:.2f}")
                    m3.metric("p값", f"{reg['p']:.3f}")
                    m4.metric("순위상관 (스피어만)", f"{reg['spearman']:.2f}", help=f"p={reg['spearman_p']:.3f}")
                    sig = "통계적으로 유의합니다(p<0.05)" if reg["p"] < 0.05 else "통계적으로 유의하지 않습니다(p≥0.05)"
                    st.caption(f"재정이 1조원 많은 시도는 3개월 심의 건수가 평균 {reg['slope']:.1f}건 많고, 재정 규모가 "
                               f"시도 간 심의 건수 차이의 {reg['r2'] * 100:.0f}%를 설명합니다. 이 관계는 {sig}. "
                               f"다만 n={reg['n']}개 시도·한 시점 자료라 인과가 아니라 규모 효과를 본 것이고, 학생·교원 수가 "
                               "재정과 심의 건수를 함께 키우는 공통 원인일 수 있습니다. 잔차가 양수인 시도는 재정 규모로 "
                               "예상되는 것보다 심의 건수가 많은 곳입니다.")
                    st.dataframe(rt, hide_index=True, width="stretch")
                else:
                    st.dataframe(cv.sort_values("심의 건수 / 재정 1조", ascending=False), hide_index=True,
                                 width="stretch")
                st.caption("심의 건수는 보도 값(신뢰도 C), 재정은 지방교육재정알리미 결산 공시. "
                           "재정 규모 대비 심의 건수가 큰 시도는 같은 재정 여건에서 교권 사안 부담이 큰 곳입니다. "
                           "교권보호단 전용 예산은 정보공개청구로 받아야 합니다.")
        with st.expander(f"받은 공시 원자료 ({len(bd):,}행, 앞 200행)"):
            st.dataframe(bd.head(200), hide_index=True, width="stretch")
    else:
        st.warning(f"지방교육재정알리미에서 자료를 받지 못했습니다 ({status}). 위 '연결 상태'에 서버 응답 앞부분이 나옵니다.")
