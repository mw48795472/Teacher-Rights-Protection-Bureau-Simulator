"""시뮬레이션 결과를 읽고 해설 문장을 만든다 (규칙 기반, 키 없이 항상 동작).

숫자 비교 → 이론 개념으로 연결하는 문장만 만든다. 처리시간·확률은 가정값이므로
'절대 수치'보다 '구조 간 차이의 방향과 크기'를 읽도록 문장을 쓴다.
"""
from __future__ import annotations

import pandas as pd

BASE_PREF = "A_distributed"


def _pct(new: float, old: float) -> str:
    if old == 0:
        return "변화 없음" if new == 0 else "새로 생김"
    d = (new - old) / old * 100
    return f"{abs(d):.0f}% {'짧음' if d < 0 else '김'}"


def _x(a: float, b: float) -> str:
    return f"{a / b:.1f}배" if b else "-"


def overview(summary: pd.DataFrame, short: dict) -> list[str]:
    """구조별 평균표(summary, index=structure key)에서 핵심 비교."""
    keys = list(summary.index)
    if len(keys) < 2:
        return ["구조를 둘 이상 고르면 비교 해설이 나옵니다."]
    base = BASE_PREF if BASE_PREF in keys else keys[0]
    b = summary.loc[base]
    best = summary["closure_days"].idxmin()
    out = [f"**가장 빨리 종결한 구조: {short[best]}** (사안당 평균 {summary.at[best, 'closure_days']:.1f} 근무일)."]
    for k in keys:
        if k == base:
            continue
        r = summary.loc[k]
        out.append(
            f"**{short[k]} vs {short[base]}**: 첫 응답 {r.first_response_h:.1f}h vs {b.first_response_h:.1f}h, "
            f"종결 {_pct(r.closure_days, b.closure_days)}, 교사가 접촉한 기관 {r.contacts:.1f}곳 vs {b.contacts:.1f}곳.")
    if b.coordination == 0 and b.contacts > 1:
        integ = [k for k in keys if summary.at[k, "coordination"] > 0]
        if integ:
            k = integ[0]
            out.append(
                f"**조정 부담의 이동**: {short[base]}에서는 조직 간 조정 메시지가 0이고 그 대신 교사가 기관 "
                f"{b.contacts:.1f}곳을 직접 찾아 {b.repeats:.1f}번 같은 내용을 진술합니다. 통합 구조에서는 조직이 "
                f"사안당 조정 메시지 약 {summary.at[k, 'coordination']:.0f}건을 떠안고 교사 진술은 "
                f"{summary.at[k, 'repeats']:.1f}번으로 줄어듭니다. 분화만 있고 통합 장치가 없으면 통합 비용이 "
                "현장 교사에게 넘어간다는 Lawrence & Lorsch의 설명과 맞습니다.")
    if "B0_gyeonggi_launch" in keys and "B_gyeonggi" in keys:
        b0, b1 = summary.loc["B0_gyeonggi_launch"], summary.loc["B_gyeonggi"]
        out.append(
            f"**조례(공식화)의 효과**: 출범 초기(B0) 대비 조례 시행 후(B)는 업무 중복 {b0.duplicates:.2f}→"
            f"{b1.duplicates:.2f}건, 창구 착오 {b0.misroutes:.2f}→{b1.misroutes:.2f}건입니다. 연계절차(제17조)와 "
            "업무매뉴얼(제25조)이 같은 인력으로도 마찰을 줄인다는 뜻입니다.")
    if "C_incheon" in keys and "B_gyeonggi" in keys:
        c, b1 = summary.loc["C_incheon"], summary.loc["B_gyeonggi"]
        line = (f"**인천형(C) vs 경기(B)**: 담당자 공백·인수인계 사안당 {c.handoffs:.2f}건 vs {b1.handoffs:.2f}건, "
                f"종결 {c.closure_days:.1f}일 vs {b1.closure_days:.1f}일.")
        if c.handoffs < b1.handoffs:
            line += " 상주 인력 비중이 높을수록 일정 공백으로 인한 인수인계가 줄어듭니다."
        out.append(line)
    return out


def by_type(df: pd.DataFrame, axis: str, metric: str, label: str) -> list[str]:
    """사안 유형(Perrow 또는 Thompson)별로 구조 간 차이가 어디서 가장 큰지."""
    g = df.groupby([axis, "구조"])[metric].mean().unstack()
    if g.shape[1] < 2:
        return []
    gap = (g.max(axis=1) - g.min(axis=1)).sort_values()
    big, small = gap.index[-1], gap.index[0]
    out = [f"구조에 따른 {label} 차이는 **{big}** 사안에서 가장 크고({gap[big]:.1f}), **{small}** 사안에서 가장 작습니다({gap[small]:.1f})."]
    complex_ = {"perrow": ("비일상적", "공학적"), "interdependence": ("교호적",)}[axis]
    if big in complex_:
        out.append("필요한 지원이 여럿인(과업 다양성이 높은) 사안일수록 구조의 차이가 커집니다. 이런 사안은 창구를 "
                   "하나씩 안내하는 것만으로는 풀리지 않고 여러 전문가를 묶는 조정이 필요하다는 "
                   + ("Perrow의 기술 유형론" if axis == "perrow" else "Thompson의 교호적 상호의존") + "과 맞습니다.")
    else:
        out.append("단순한 사안에서 차이가 크게 나타났습니다. 이번 설정에서는 사안의 복잡성보다 대기·인력 같은 "
                   "다른 요인이 결과를 좌우하고 있을 수 있습니다.")
    return out


def surge(df: pd.DataFrame, surge_day: int, days: int = 7) -> list[str]:
    """급증 구간에 접수된 사안이 평소보다 얼마나 더 오래 걸리는지."""
    out = []
    for s, d in df.groupby("구조"):
        before = d[d["arrival_day"] < surge_day]["closure_days"].mean()
        during = d[(d["arrival_day"] >= surge_day) & (d["arrival_day"] < surge_day + days)]["closure_days"].mean()
        if pd.notna(before) and pd.notna(during) and before > 0:
            out.append((s, during / before, before, during))
    if not out:
        return []
    out.sort(key=lambda t: t[1])
    lines = [f"{s}: 평소 {b:.1f}일 → 급증 구간 {d:.1f}일 ({r:.2f}배)" for s, r, b, d in out]
    res = [f"**급증을 가장 잘 흡수한 구조: {out[0][0]}** ({out[0][1]:.2f}배). 가장 크게 흔들린 구조: {out[-1][0]} "
           f"({out[-1][1]:.2f}배).", " · ".join(lines),
           "배수가 클수록 고정된 인력·창구에 일이 몰려 대기가 쌓인다는 뜻입니다. 환경 변화에 맞춰 인력을 다시 "
           "묶는 유기적 구조일수록 배수가 작습니다 (Burns & Stalker)."]
    fastest = min(out, key=lambda t: t[2])
    if fastest[0] == out[-1][0]:
        res.append(f"평소 가장 빠른 {fastest[0]}이 급증에는 가장 취약했습니다. 평시 효율과 변화 대응력은 다른 지표입니다.")
    return res


def offices(per: pd.DataFrame, structure_short: str) -> list[str]:
    """교육지원청별 결과(per: 구조, office, 사안, 위원회_대기일, 종결일)."""
    p = per[per["구조"] == structure_short]
    if p.empty:
        return []
    big5 = p.sort_values("사안", ascending=False).head(5)
    share = big5["사안"].sum() / max(1, p["사안"].sum()) * 100
    w = p[p["위원회_대기일"] > 0].sort_values("위원회_대기일", ascending=False)  # 위원회까지 간 사안이 있는 관할만
    if w.empty:
        return [f"사안이 많은 5개 관할({', '.join(big5['office'])})이 전체 사안의 {share:.0f}%를 받습니다."]
    top = ", ".join(f"{r.office}({r.위원회_대기일:.1f}일, 사안 {r.사안}건)" for r in w.head(3).itertuples())
    low = ", ".join(f"{r.office}({r.위원회_대기일:.1f}일)" for r in w.tail(3).itertuples())
    corr = w["사안"].corr(w["위원회_대기일"]) if len(w) > 2 else float("nan")
    out = [f"**위원회 대기가 긴 관할**: {top}. 짧은 관할: {low}.",
           f"사안이 많은 5개 관할({', '.join(big5['office'])})이 전체 사안의 {share:.0f}%를 받습니다."]
    if pd.notna(corr):
        if corr > 0.5:
            out.append(f"사안 수와 대기일의 상관계수가 {corr:.2f}(높음)입니다. 학교가 많은 관할의 위원회가 정원에 걸려 "
                       "사안이 다음 회의로 밀리는 병목입니다. 위원회 정원이나 개최 횟수를 관할 규모에 맞출 필요가 있습니다.")
        else:
            out.append(f"사안 수와 대기일의 상관계수는 {corr:.2f}(약함)입니다. 지금 설정에서는 정원보다 회의 개최 간격과 "
                       "개최일이 대기를 좌우합니다. 사이드바에서 하루 사안 수를 올리면 큰 관할부터 병목이 생깁니다.")
    return out


def agent_runs(metrics: dict[str, dict]) -> list[str]:
    """에이전트 시뮬레이션 요약 지표 {구조 이름: metrics}에서 해설."""
    out = []
    for name, m in metrics.items():
        parts = [f"행동 {m['행동 수']}개 중 차단 {m['차단']}개, 조건부 허용 {m['조건부 허용']}개"]
        if m["권한 초과"]:
            parts.append(f"권한 초과 판정 {m['권한 초과']}회")
        if m["교육활동 침해 탐지"]:
            parts.append(f"교육활동 침해 탐지 {m['교육활동 침해 탐지']}회")
        if m["처리 주체 없는 후속 절차"]:
            parts.append(f"챙기는 주체가 없어 흘러간 후속 절차 {m['처리 주체 없는 후속 절차']}건")
        if m["피해 교원이 직접 한 행동"]:
            parts.append(f"피해 교원이 직접 움직인 차례 {m['피해 교원이 직접 한 행동']}번")
        out.append(f"**{name}**: " + ", ".join(parts) + ".")
        if m["근거 불충분"] and m["근거 불충분"] >= max(1, m["행동 수"] // 3):
            out.append(f"{name}에서 '근거 불충분' 판정이 {m['근거 불충분']}회로 많습니다. 법령 원문(LAW_OC 수집)이 "
                       "들어가면 판정이 더 분명해집니다.")
    blocked = [n for n, m in metrics.items() if m["권한 초과"]]
    if blocked:
        out.append(f"권한 초과 판정이 나온 구조: {', '.join(blocked)}. 공적 주체가 법령상 권한 밖의 행동"
                   "(직접 조사·판정, 위압적 제지)을 하려 하면 컴플라이언스가 차단하거나, 권한 안의 부분만 조건부로 "
                   "허용하고 나머지는 권한 있는 기관에 넘기게 합니다.")
    return out


def theory(p: pd.DataFrame, reg: pd.DataFrame, base: str, target: str, label: str, unit: str = "") -> list[str]:
    """이론별 분석(H2) 해설. p는 typeffects.paired() 결과(diff = 기준 - 비교), reg는 regression() 결과."""
    from .typeffects import gap_by
    if p.empty:
        return []
    out = []
    g = gap_by(p, "n_needs").set_index("n_needs")
    lo, hi = g.index.min(), g.index.max()
    out.append(f"**사안별 짝 비교**: {target}이 {base}보다 {label}을(를) 사안당 평균 {p['diff'].mean():.1f}{unit} "
               f"줄였습니다 (양수 = 줄임). 지원이 {lo}개인 사안 {g.at[lo, 'mean']:.1f}{unit} (n={g.at[lo, 'n']}) → "
               f"{hi}개인 사안 {g.at[hi, 'mean']:.1f}{unit} (n={g.at[hi, 'n']}).")
    r = reg.set_index("항") if not reg.empty else pd.DataFrame()

    def coef(term: str) -> str:
        if term not in r.index:
            return ""
        b, t = r.at[term, "계수"], r.at[term, "t"]
        sig = "뚜렷함" if pd.notna(t) and abs(t) >= 2 else "불확실함"
        return f"{b:+.2f}{unit} (t={t:.1f}, {sig})"

    if "n_needs" in r.index:
        out.append(f"**Thompson (상호의존)**: 분석가능성·위원회·심각도가 같을 때 지원이 1개 늘면 구조 차이가 "
                   f"{coef('n_needs')} 달라집니다. 양수이고 뚜렷하면 얽힌 사안일수록 통합 구조가 더 많이 줄인다는 뜻입니다.")
    if "low_analyz" in r.index:
        out.append(f"**Perrow (분석가능성)**: 지원 개수가 같을 때 해결 절차가 불명확한 사안의 구조 차이는 "
                   f"{coef('low_analyz')} 다릅니다. 이 효과는 '분산 구조에서는 교사가 앞 기관에 되돌아가고, 통합 "
                   "구조에서는 사례 회의로 흡수한다'는 가정에서 나옵니다.")
    if "committee" in r.index:
        out.append(f"**위원회 심의(교란 변수)**: 위원회를 거친 사안의 구조 차이는 {coef('committee')} 다릅니다. "
                   "지표가 '종결까지'면 이 항이 크게 나오는데, 사안의 복잡성이 아니라 위원회 개최 간격의 차이입니다.")
    b1 = r.at["n_needs", "계수"] if "n_needs" in r.index else 0
    t1 = r.at["n_needs", "t"] if "n_needs" in r.index else 0
    if b1 > 0 and pd.notna(t1) and t1 >= 2:
        out.append("**H2 판정 (이 설정)**: 지지. 다른 조건을 통제해도 지원이 많을수록 통합 구조의 이점이 커집니다.")
    elif b1 > 0:
        out.append("**H2 판정 (이 설정)**: 방향은 맞지만 사안 수가 적어 불확실합니다. 기간을 늘리거나 하루 사안 수를 "
                   "올려 다시 보세요.")
    else:
        out.append("**H2 판정 (이 설정)**: 지지 안 됨. 이 지표에서는 지원 개수가 늘어도 구조 차이가 커지지 않습니다.")
    return out
