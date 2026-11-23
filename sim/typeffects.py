"""이론별 분석(H2): 사안 특성에 따라 구조 효과가 달라지는가.

모든 구조에 같은 사안 흐름이 들어가므로(공통 난수, 같은 id = 같은 사안) 구조 간 차이를
'사안별 짝 비교'로 잴 수 있다. 사안 하나하나에 대해 (기준 구조 값 - 비교 구조 값)을 구하면
사안 유형이 같더라도 생기는 우연한 차이가 지워진다.

주의할 교란 변수:
- 위원회 심의: 위원회를 거치는 사안만 위원회 개최 간격(A 60일, B 30일 등)만큼 기다린다.
  기본 가정에서 지원이 1~2개인 사안(단순 상담, 민·형사 소송)은 위원회로 가지 않으므로
  '종결까지' 지표로 유형을 비교하면 상호의존 효과와 위원회 간격 효과가 섞인다.
  → process_days(위원회 대기 제외)를 쓰거나 회귀에서 위원회 여부를 통제한다.
- 상호의존(Thompson) 유형은 지원 개수로 정해진다 (1개 집합적, 2개 순차적, 3개 이상 교호적).
  Perrow 과업다양성도 지원 3개 이상이다. 두 축은 같은 변수(지원 개수)를 다르게 자른 것이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AXES = {
    "n_needs": "필요한 지원 개수",
    "interdependence": "Thompson 상호의존 유형",
    "perrow": "Perrow 조직기술 유형",
}
ORDER = {
    "interdependence": ["집합적", "순차적", "교호적"],
    "perrow": ["일상적", "장인", "공학적", "비일상적"],
}


def cells(df: pd.DataFrame, axis: str, metric: str) -> pd.DataFrame:
    """유형 × 구조별 사안 수, 평균, 95% 신뢰구간 반폭."""
    g = df.groupby([axis, "구조"])[metric].agg(["size", "mean", "std"]).reset_index()
    g["ci"] = 1.96 * g["std"].fillna(0) / np.sqrt(g["size"])
    return g.rename(columns={"size": "n"})


def trend(df: pd.DataFrame, x: str, metric: str) -> pd.DataFrame:
    """구조별 단순 회귀선 metric = a + b·x (기울기 b와 표준오차)."""
    rows = []
    for s, d in df.groupby("구조"):
        d = d[[x, metric]].dropna().astype(float)
        if d[x].nunique() < 2:
            continue
        b, a = np.polyfit(d[x], d[metric], 1)
        resid = d[metric] - (a + b * d[x])
        se = np.sqrt((resid ** 2).sum() / max(1, len(d) - 2) / ((d[x] - d[x].mean()) ** 2).sum())
        rows.append({"구조": s, "절편": a, "기울기": b, "기울기_se": se, "n": len(d),
                     "x0": d[x].min(), "x1": d[x].max()})
    return pd.DataFrame(rows)


def paired(df: pd.DataFrame, metric: str, base: str, target: str) -> pd.DataFrame:
    """같은 사안의 (기준 - 비교) 차이. 양수면 비교 구조가 그만큼 줄였다는 뜻."""
    keep = ["id", "n_needs", "interdependence", "perrow", "analyzable", "variety_high", "committee", "severity", "type"]
    a = df[df["structure"] == base].set_index("id")
    b = df[df["structure"] == target].set_index("id")
    ids = a.index.intersection(b.index)
    out = a.loc[ids].reset_index()[keep].copy()
    out["base"] = a.loc[ids, metric].to_numpy()
    out["target"] = b.loc[ids, metric].to_numpy()
    out["diff"] = out["base"] - out["target"]
    return out


def gap_by(p: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    """paired() 결과를 유형별로 묶어 평균 차이와 95% 신뢰구간."""
    g = p.groupby(by)["diff"].agg(["size", "mean", "std"]).reset_index()
    g["ci"] = 1.96 * g["std"].fillna(0) / np.sqrt(g["size"])
    g["lo"], g["hi"] = g["mean"] - g["ci"], g["mean"] + g["ci"]
    return g.rename(columns={"size": "n"})


REG_TERMS = {
    "n_needs": "지원 1개 늘 때 (상호의존·과업다양성)",
    "low_analyz": "분석가능성 낮음 (Perrow)",
    "committee": "위원회 심의를 거침",
    "severity": "심각도 1단계 높을 때",
}


def regression(p: pd.DataFrame) -> pd.DataFrame:
    """사안별 구조 차이(diff)를 사안 특성으로 설명하는 최소제곱 회귀.

    diff = b0 + b1·지원개수 + b2·분석가능성낮음 + b3·위원회 + b4·심각도
    계수는 '다른 특성이 같을 때 그 특성이 구조 효과를 얼마나 키우는가'로 읽는다.
    변동이 없는 항(예: 모든 사안이 위원회를 거침)은 뺀다."""
    X = pd.DataFrame({"n_needs": p["n_needs"].astype(float),
                      "low_analyz": (~p["analyzable"].astype(bool)).astype(float),
                      "committee": p["committee"].astype(float),
                      "severity": p["severity"].astype(float)})
    X = X.loc[:, X.nunique() > 1]
    y = p["diff"].astype(float).to_numpy()
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    if len(y) <= A.shape[1]:
        return pd.DataFrame(columns=["항", "설명", "계수", "se", "t"])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    sigma2 = (resid ** 2).sum() / (len(y) - A.shape[1])
    cov = sigma2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.diag(cov))
    names = ["const"] + list(X.columns)
    out = pd.DataFrame({"항": names, "계수": beta, "se": se})
    out["t"] = out["계수"] / out["se"].replace(0, np.nan)
    out["설명"] = out["항"].map(REG_TERMS | {"const": "기본 (절편)"})
    return out[["항", "설명", "계수", "se", "t"]]


def confound(df: pd.DataFrame, axis: str) -> pd.DataFrame:
    """유형별 위원회 심의 비율 (구조와 무관하게 같음)."""
    d = df.drop_duplicates("id")
    return d.groupby(axis)["committee"].mean().rename("위원회_비율").reset_index()


def jitter(n: int, seed: int = 0, width: float = 0.18) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-width, width, n)
