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

# 화면 순서: ① 추세 ② 시도 비교 ③ 아동학대 ④ 학교폭력(t7) ⑤ 재정(t6) ⑥ 출범 효과(t5)
t1, t2, t4, t7, t6, t5 = st.tabs(["① 추세·교권5법 전후", "② 시도 비교·교원 1천 명당 (2024)",
                                  "③ 아동학대 신고 흐름", "④ 학교폭력·청소년 비행", "⑤ 시도교육청 재정",
                                  "⑥ 교권보호단 출범 효과"])

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
    s = tr.sido_2024()
    tc = tr.sido_teachers()
    st.plotly_chart(px.bar(s, x="시도", y="2024.3.28~6.30", text="2024.3.28~6.30",
                           title="시도별 지역교권보호위원회 심의 건수 (2024.3.28~6.30, 17개 시도)"),
                    width="stretch")
    col = "1천 명당 (3개월)"
    if col in s:
        st.plotly_chart(px.bar(s.sort_values(col, ascending=False), x="시도", y=col, text=col,
                               title="교원 1천 명당 심의 건수 (2024.3.28~6.30): 시도 규모 차이를 뺀 값"),
                        width="stretch")
    else:
        st.warning("시도별 교원 수 자료가 아직 없어 교원 1천 명당 값은 계산하지 못했습니다. 아래 연결 상태를 확인해 주세요.")
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
    st.markdown("**시도별 표** (건수와 교원 1천 명당 값)")
    st.dataframe(s, hide_index=True, width="stretch")
    _lv = [c for c in ("유치원", "초등학교", "중학교", "고등학교", "특수학교") if c in tc.columns]
    _src = str(tc["출처"].dropna().iloc[0]) if "출처" in tc and tc["출처"].notna().any() else ""
    _tsrc = ("" if tc.empty else "교원 수는 "
             + (f"{'+'.join(_lv)} 교원 수 합계 ({_src})" if _lv and _src else
                f"KOSIS {'+'.join(_lv)} 교원 수 합계" if _lv else "KESS·KOSIS")
             + "이며 정규·기간제 교원 합(강사 제외)입니다. ")
    st.caption("출처: 2024.3.28~6.30은 교육부 제출 자료(정성국 의원실·한국교총 발표), 2024년 전체와 인천 주체는 "
               "17개 시·도교육청 제출 자료(백승아 의원실 발표)를 보도한 기사. 원자료가 공개되지 않아 신뢰도 C입니다. " + _tsrc
               + "건수만으로는 시도 규모 차이를 반영하지 못하므로 교원 1천 명당 값과 함께 보세요.")
    with st.expander("연결 상태 (KOSIS 교원 수)"):
        from collector import kosis as _kosis
        _ks = st.cache_data(ttl=3600, show_spinner=False)(_kosis.status)() if tc.empty else {"ok": True, "reason": f"교원 수 {len(tc)}행 사용 중"}
        st.write(("✅ " if _ks["ok"] else "⚠️ ") + _ks["reason"] + (f" · {_ks['table']}" if _ks.get("table") else ""))
        if tc.empty:
            st.caption("KESS(kess.kedi.re.kr)에서 시도별 교원 수를 받아 `data/measured/sido_teachers.csv`(열: 시도, 연도, 교원수)로 "
                       "넣거나, Streamlit Secrets에 `KOSIS_KEY`를 넣으면 `config/kosis.yaml`의 표로 앱이 직접 받아 채웁니다.")

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


with t7:
    st.caption("교보위 사안의 약 89%는 학생이 침해 주체입니다(2024 인천 보도). 학교폭력·청소년 비행이 많은 시도일수록 "
               "교권 침해 심의도 많은지 시도×연도 패널로 봅니다.")
    data_label("real", "학교폭력 심의는 학교알리미 공시, 피해응답률은 교육부·시도교육청 실태조사, 소년범죄는 공식 범죄통계입니다. "
                       "교보위 심의 건수는 보도 값(신뢰도 C)입니다.")
    sv = tr.school_violence_sido()
    if sv.empty:
        st.info("학교폭력 공시 파일(data/measured/school_violence_sido.csv)이 아직 없습니다.")
    else:
        st.plotly_chart(px.line(sv, x="학년도", y="학폭 심의 / 학생 1천 명", color="시도", markers=True,
                                title="시도별 학교폭력 심의 건수 (학생 1천 명당)").update_xaxes(dtick=1), width="stretch")
        st.caption("학교알리미 '학교폭력 심의 결과' 공시(전국 초·중·고 약 1만 2천 곳)를 시도별로 더했습니다. 4월 공시는 전 학년도 실적이라 "
                   "공시연도에서 1을 뺀 학년도로 표시합니다. 공시 원자료는 학교알리미 화면에만 있어 공개 집계(school-violence-map)에서 받았습니다.")
        if (sv["학생수 기준"] == "2026 공시").all():
            st.caption("학생 수는 2026 공시 기준이라 연도별 학생 수 변화는 반영하지 못합니다. Streamlit Secrets에 `SCHOOLINFO_KEY`가 "
                       "있으면 학교알리미에서 연도별 학생 수를 받아 바꿉니다(아래 '연결 상태').")
        else:
            st.caption("학생 수: " + ", ".join(sorted(sv["학생수 기준"].unique())) + ". 해당 연도 초·중·고 학생 수(4.1. 기준)로 나눴습니다.")
    from collector import schoolinfo as _si
    _sf = _si.OUT / _si.SIDO_FILE
    with st.expander("학생 수 출처 (KESS 파일 / 학교알리미 Open API)"):
        if _sf.exists():
            st.write(f"✅ 저장소의 시도별 학생 수 파일 사용 중 ({_sf.relative_to(_si.ROOT)}). 학교알리미 API는 부르지 않습니다.")
        else:
            _ss = st.cache_data(ttl=3600, show_spinner=False)(_si.check)()
            st.write(("✅ " if _ss["ok"] else "⚠️ ") + _ss["reason"])
            if _ss.get("columns"):
                st.caption("응답 칸: " + ", ".join(map(str, _ss["columns"])))
            if _si.schoolinfo_key():
                _st = _si.students(fetch=False)
                if not _st.empty:
                    st.write(f"✅ 연도별 학생 수 {len(_st)}행 사용 중 (공시연도 {', '.join(map(str, sorted(_st['공시연도'].unique())))})")
                elif _si._AUTO["note"]:
                    st.write("⚠️ 학생 수 받기: " + _si._AUTO["note"])
                    if "접속하지 못함" in _si._AUTO["note"]:
                        st.caption("학교알리미는 해외에서 접속을 막는 경우가 많아 Streamlit Cloud 서버에서는 받지 못할 수 있습니다. "
                                   "국내 PC에서 `python -m collector.schoolinfo`를 한 번 돌리거나 KESS 시도별 학생수를 "
                                   "`data/measured/schoolinfo/students_by_sido.csv`로 커밋하면 앱이 그 파일을 씁니다.")
        st.caption("학교알리미 Open API에는 학교폭력 심의 결과 항목이 없어, 이 키는 연도별 학생 수(분모)에만 씁니다.")
    vr = tr.victim_rate()
    if not vr.empty:
        st.plotly_chart(px.line(vr.sort_values("연도"), x="연도", y="피해응답률", color="시도", markers=True,
                                title="학교폭력 실태조사 피해응답률 (1차 전수조사, %)").update_xaxes(dtick=1), width="stretch")
        st.caption("시도교육청 보도자료와 지역 언론 보도에서 옮긴 시도별 값입니다(교육부 발표에는 전국값만 있음). 빈 칸은 해당 연도 "
                   "보도에서 값을 찾지 못한 경우이고, 전년 대비 증감만 보도된 값은 계산값입니다(출처 표의 비고). 2차 표본조사 값은 섞지 않았습니다. "
                   "전북 2023은 전국 1차에 불참하고 자체 조사한 값이라 비교에 주의하세요.")
        with st.expander("피해응답률 출처 표"):
            st.dataframe(vr, hide_index=True, width="stretch")
    jc = tr.juvenile_crime()
    if not jc.empty:
        st.plotly_chart(px.line(jc.sort_values("연도"), x="연도", y="값", color="시도", line_dash="지표", markers=True,
                                title="시도별 촉법소년 (보도 값)").update_xaxes(dtick=1), width="stretch")
        st.caption(f"경찰청 자료를 인용한 보도(의원실 국감 자료·정보공개)에서 옮긴 값이라 {jc['시도'].nunique()}개 시도만 있습니다(신뢰도 C). "
                   "17개 시도가 다 모이지 않아 회귀분석에는 아직 쓰지 않습니다. 경찰청 시도별 소년범 검거 표는 정보공개청구로 받을 수 있습니다.")

    cvd = tr.committee_vs_delinquency(2024)
    xs = [c for c in ["학폭 심의 / 학생 1천 명", "자체해결 포함 / 학생 1천 명", "피해응답률(%)", "학폭심의건수"]
          + [c for c in cvd.columns if "소년" in c] if c in cvd and cvd[c].notna().sum() >= 8]
    ys = [c for c in [tr.COMMITTEE_RATE, tr.COMMITTEE_Y] if c in cvd]
    if xs and ys:
        st.markdown("**교권 침해 심의와 학교폭력·비행 지표 (2024, 17개 시도)**")
        c1, c2 = st.columns(2)
        x = c1.selectbox("설명 변수 (x)", xs, key="dq_x")
        y = c2.selectbox("교권 지표 (y)", ys, key="dq_y")
        reg, rt = tr.simple_regression(cvd, x, y)
        d = cvd.dropna(subset=[x, y])
        fig = px.scatter(d, x=x, y=y, text="시도", title=f"{x}이(가) 높은 시도일수록 교권 침해 심의도 많은가")
        fig.update_traces(textposition="top center")
        if reg:
            xl = d[x].sort_values()
            fig.add_scatter(x=xl, y=reg["intercept"] + reg["slope"] * xl, mode="lines", name="회귀선",
                            line=dict(dash="dash"))
        st.plotly_chart(fig, width="stretch")
        if reg:
            st.markdown(f"**단순 회귀분석: {y} = a + b × {x}**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("기울기 b", f"{reg['slope']:.3f}", help=f"표준오차 {reg['se']:.3f}")
            m2.metric("R²", f"{reg['r2']:.2f}")
            m3.metric("p값", f"{reg['p']:.3f}")
            m4.metric("순위상관 (스피어만)", f"{reg['spearman']:.2f}", help=f"p={reg['spearman_p']:.3f}")
            sig = "통계적으로 유의합니다(p<0.05)" if reg["p"] < 0.05 else (
                "10% 수준에서만 약하게 유의합니다(0.05≤p<0.10)" if reg["p"] < 0.10 else "통계적으로 유의하지 않습니다(p≥0.10)")
            st.caption(f"{x}이(가) 1 높은 시도는 {y}이(가) 평균 {reg['slope']:.3f} 높고, 시도 간 차이의 "
                       f"{reg['r2'] * 100:.0f}%를 설명합니다. 이 관계는 {sig}. 한계: n={reg['n']}개 시도·한 시점이라 검정력이 낮고, "
                       "교보위 값은 2024.3.28~6.30 약 3개월 보도 값입니다. 건수끼리 비교하면 학생·교원 수가 많은 시도가 둘 다 커서 "
                       "상관이 부풀려지므로, 인구 대비 비율(1천 명당)끼리 비교한 결과를 우선 보세요. 상관이지 인과가 아닙니다.")
            st.caption("단순 회귀라 VIF = 1 (다중공선성 없음). 변수를 여러 개 넣은 VIF는 아래 다중 회귀에 있습니다.")
            st.dataframe(rt, hide_index=True, width="stretch")
        else:
            st.dataframe(d, hide_index=True, width="stretch")

        st.markdown("**다중 회귀분석과 VIF (다중공선성)**")
        st.caption("단순 회귀는 설명 변수가 하나라 VIF가 항상 1입니다. 여러 변수를 함께 넣어 서로의 영향을 통제한 계수와, "
                   "변수끼리 얼마나 겹치는지(VIF)를 봅니다.")
        mx = [c for c in ["학폭 심의 / 학생 1천 명", "자체해결 포함 / 학생 1천 명", "피해응답률(%)", "교원 1명당 학생 수"]
              + [c for c in cvd.columns if c.startswith("재정 / 학생")] + [c for c in cvd.columns if "소년" in c and "1천" in c]
              if c in cvd and cvd[c].notna().sum() >= 8]
        default = [c for c in mx if c in ("학폭 심의 / 학생 1천 명", "피해응답률(%)", "교원 1명당 학생 수")
                   or c.startswith("재정 / 학생")]
        chosen = st.multiselect("설명 변수 (여러 개)", mx, default=default, key="dq_multi")
        my = tr.COMMITTEE_RATE if tr.COMMITTEE_RATE in cvd else ys[0]
        mreg, mtab = tr.multiple_regression(cvd, chosen, my)
        if mreg.get("singular"):
            st.warning("고른 변수끼리 완전히 겹쳐(한 변수가 다른 변수들의 합 등) 계수를 구할 수 없습니다. 변수를 줄여 주세요.")
        elif not mreg:
            st.info("변수를 하나 이상 고르고, 관측치(시도 수)가 변수 수 + 2 이상이어야 합니다.")
        else:
            st.markdown(f"**{my} = a + " + " + ".join(f"b{i + 1}·{c}" for i, c in enumerate(chosen)) + "**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("관측치 n", f"{mreg['n']}", help="결측이 있는 시도는 빠집니다")
            m2.metric("R²", f"{mreg['r2']:.2f}")
            m3.metric("수정 R²", f"{mreg['adj_r2']:.2f}", help="변수 수를 감안한 R²")
            m4.metric("모형 F검정 p값", f"{mreg['f_p']:.3f}")
            st.dataframe(mtab, hide_index=True, width="stretch")
            mv = mreg["max_vif"]
            if mv > 10:
                st.warning(f"최대 VIF {mv:.1f}: 10을 넘어 다중공선성이 심합니다. VIF가 큰 변수 중 하나를 빼고 다시 보세요.")
            elif mv > 5:
                st.info(f"최대 VIF {mv:.1f}: 5~10이라 다중공선성을 주의해서 해석하세요.")
            else:
                st.success(f"최대 VIF {mv:.1f}: 5 미만이라 변수끼리 겹침은 크지 않습니다.")
            st.caption(f"VIF = 1 / (1 − R²ⱼ), R²ⱼ는 그 변수를 나머지 설명 변수로 회귀한 결정계수입니다. 보통 10을 넘으면 심각, "
                       f"5를 넘으면 주의로 봅니다. 표준화 계수는 변수 단위를 맞춰 상대적 크기를 비교한 값입니다. "
                       f"한계: n={mreg['n']}개 시도에 변수 {mreg['k']}개라 자유도가 {mreg['n'] - mreg['k'] - 1}뿐이어서 계수가 불안정하고, "
                       "변수를 하나 넣고 뺄 때마다 결과가 크게 바뀔 수 있습니다. 탐색용으로만 보세요.")
            if not any(c.startswith("재정 / 학생") for c in mx):
                st.caption("재정 규모 변수는 ⑤ 시도교육청 재정 탭이 지방교육재정알리미 자료를 받아 둔 경우에만 나타납니다.")
        st.info("시도별 교보위 심의 건수가 연도별로 들어오면(정보공개청구 또는 교육부 발표) 같은 패널에서 시도 고정효과 회귀로 "
                "'같은 시도 안에서 학폭이 늘어난 해에 교권 침해도 늘었는가'를 볼 수 있습니다. 지금은 2024 한 시점만 있습니다.")
    pn = tr.delinquency_panel()
    if not pn.empty:
        with st.expander(f"시도×연도 패널 표 ({len(pn)}행)"):
            st.dataframe(pn, hide_index=True, width="stretch")
