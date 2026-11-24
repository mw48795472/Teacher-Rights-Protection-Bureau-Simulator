"""구조별 '인물관계도' (드라마 인물관계도처럼 주체와 관계를 한 장의 SVG로).

선생님을 가운데 두고, 누가 누구를 돕고(초록), 누가 갈등을 만들고(빨강), 누가 위에서 이끄는지(보라),
선생님이 직접 찾아다녀야 하는 곳(주황 점선), 법에 막히는 행동(빨강 점선 ✕)을 화살표로 그린다.
실행 결과가 있으면 인물마다 몇 번 움직였는지 적고, 한 번도 안 나온 인물은 흐리게 한다.
"""
from __future__ import annotations

from html import escape

from .runner import AgentRun

# 무리별 색과 이모지
GROUP = {"me": "#2a6fdb", "opp": "#d64541", "school": "#7f8c8d", "bureau": "#8b5cf6", "org": "#16a085",
         "agent": "#e67e22"}
NODE = {  # 역할 → (무리, 이모지, 짧은 이름)
    "피해 교원": ("me", "👩‍🏫", "선생님"), "학부모": ("opp", "😠", "학부모"), "학교장": ("school", "🏫", "교장"),
    "교권보호 119": ("bureau", "📞", "교권보호 119"), "상근 전담관": ("bureau", "🧑‍💼", "상근 전담관"),
    "비상근 전담관(법률)": ("bureau", "⚖️", "변호사 전담관"), "비상근 전담관(상담)": ("bureau", "💬", "상담 전담관"),
    "교육감": ("bureau", "🏛️", "교육감(단장)"), "지역교권보호위원회": ("org", "🗂️", "교권보호위원회"),
    "수사기관": ("org", "🚓", "경찰·수사기관"), "지역교권보호지원센터": ("org", "🏢", "지원센터"),
    "교육지원청 담당자": ("org", "📑", "교육지원청"), "교권보호국 요원": ("agent", "🕶️", "교권보호국 요원"),
}
EDGE = {  # 종류 → (색, 점선, 굵기)
    "conflict": ("#d64541", "", 2.6), "help": ("#1f8a4c", "", 2.4), "lead": ("#8b5cf6", "", 2.2),
    "trip": ("#e67e22", "7 5", 2.2), "blocked": ("#d64541", "4 4", 2.0), "plain": ("#95a5a6", "", 1.6),
}

# 구조별 배치와 관계 (x, y는 640×440 캔버스)
LAYOUT = {
    "integrated": {
        "pos": {"학부모": (70, 220), "피해 교원": (225, 220), "학교장": (225, 385), "교권보호 119": (225, 60),
                "상근 전담관": (405, 220), "교육감": (405, 60), "비상근 전담관(법률)": (570, 130),
                "비상근 전담관(상담)": (570, 310), "지역교권보호위원회": (405, 380), "수사기관": (570, 45),
                "교육지원청 담당자": (570, 390)},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "교권보호 119", "help", "한 번만 신고"),
                  ("교권보호 119", "상근 전담관", "help", "배정"), ("상근 전담관", "피해 교원", "help", "1:1 끝까지"),
                  ("교육감", "상근 전담관", "lead", "단장"), ("상근 전담관", "비상근 전담관(법률)", "help", "연결"),
                  ("상근 전담관", "비상근 전담관(상담)", "help", "연결"),
                  ("상근 전담관", "지역교권보호위원회", "help", "심의 요청"), ("교육감", "수사기관", "lead", "고발"),
                  ("학교장", "피해 교원", "plain", "분리조치"), ("교육지원청 담당자", "지역교권보호위원회", "plain", "조사")],
        "note": "전담관 한 명이 가운데서 전문가와 기관을 묶어 줘요.",
    },
    "distributed": {
        "pos": {"학부모": (70, 220), "피해 교원": (250, 220), "학교장": (455, 55), "지역교권보호지원센터": (565, 175),
                "교육지원청 담당자": (565, 300), "지역교권보호위원회": (430, 395), "수사기관": (250, 395)},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "학교장", "trip", "① 찾아감"),
                  ("피해 교원", "지역교권보호지원센터", "trip", "② 처음부터 설명"),
                  ("피해 교원", "교육지원청 담당자", "trip", "③ 또 설명"),
                  ("피해 교원", "지역교권보호위원회", "trip", "④ 직접 신청"), ("학부모", "수사기관", "plain", "신고·소송")],
        "note": "기관끼리는 서로 연결이 없어서, 선생님이 혼자 여기저기 찾아다녀요.",
    },
    "drama": {
        "pos": {"학부모": (80, 210), "피해 교원": (250, 370), "교권보호국 요원": (285, 120), "학교장": (80, 395),
                "교육감": (480, 60), "수사기관": (580, 210), "지역교권보호위원회": (470, 360)},
        "edges": [("학부모", "피해 교원", "conflict", "민원·폭언"), ("피해 교원", "교권보호국 요원", "help", "출동 요청"),
                  ("교권보호국 요원", "학부모", "blocked", "강제 제지 ✕"),
                  ("교권보호국 요원", "지역교권보호위원회", "blocked", "직접 판정 ✕"),
                  ("교육감", "수사기관", "lead", "고발 (대신 가능)"), ("교육감", "교권보호국 요원", "lead", "지휘"),
                  ("학교장", "피해 교원", "plain", "분리조치")],
        "note": "요원이 직접 밀어붙이는 길(✕)은 법에 막히고, 교육감 고발 같은 공식 경로만 남아요.",
    },
}
LEGEND = [("help", "도움·연결"), ("conflict", "갈등"), ("lead", "지휘·공식 권한"), ("trip", "선생님이 직접 찾아감"),
          ("blocked", "법에 막힘")]
R = 28


def _shorten(p, q):
    """두 동그라미 가장자리까지 줄인다. 아래쪽으로 나가는 끝은 이름표를 피해 더 띄운다."""
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    d = max((dx * dx + dy * dy) ** .5, 1)
    ux, uy = dx / d, dy / d
    r1 = R + (26 if uy > .45 else 6)    # p 아래 이름표 쪽으로 나감
    r2 = R + (26 if uy < -.45 else 8)   # q 아래쪽에서 들어옴
    return (x1 + ux * r1, y1 + uy * r1), (x2 - ux * r2, y2 - uy * r2)


def svg(structure: str, run: AgentRun | None = None) -> str:
    L = LAYOUT[structure]
    pos = L["pos"]
    counts = {}
    if run:
        for t in run.turns:
            counts[t.actor] = counts.get(t.actor, 0) + 1
    out = ['<svg viewBox="0 0 640 450" width="100%" xmlns="http://www.w3.org/2000/svg" '
           'style="font-family: inherit; max-width: 760px; display: block; margin: 0 auto;">', "<defs>"]
    for k, (c, _, _) in EDGE.items():
        out.append(f'<marker id="ar-{structure}-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
                   f'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    out.append("</defs>")
    labels = []
    for a, b, kind, label in L["edges"]:
        if a not in pos or b not in pos:
            continue
        c, dash, w = EDGE[kind]
        (x1, y1), (x2, y2) = _shorten(pos[a], pos[b])
        # 살짝 휜 곡선 (인물관계도 느낌)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        nx, ny = -(y2 - y1) * .12, (x2 - x1) * .12
        cx, cy = mx + nx, my + ny
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(f'<path d="M{x1:.0f},{y1:.0f} Q{cx:.0f},{cy:.0f} {x2:.0f},{y2:.0f}" fill="none" stroke="{c}" '
                   f'stroke-width="{w}"{dash_attr} marker-end="url(#ar-{structure}-{kind})" opacity=".9"/>')
        lx, ly = (mx + cx) / 2, (my + cy) / 2
        tw = len(label) * 11 + 12
        labels.append(f'<rect x="{lx - tw / 2:.0f}" y="{ly - 10:.0f}" width="{tw}" height="20" rx="10" '
                      f'fill="#ffffff" fill-opacity=".92" stroke="{c}" stroke-width="1"/>'
                      f'<text x="{lx:.0f}" y="{ly + 4:.0f}" text-anchor="middle" font-size="11.5" font-weight="600" '
                      f'fill="{c}">{escape(label)}</text>')
    for role, (x, y) in pos.items():
        g, emoji, name = NODE[role]
        c = GROUP[g]
        faded = run is not None and role not in counts
        op = ".35" if faded else "1"
        big = role == "피해 교원"
        r = R + 6 if big else R
        out.append(f'<g opacity="{op}"><circle cx="{x}" cy="{y}" r="{r}" fill="{c}" fill-opacity=".14" stroke="{c}" '
                   f'stroke-width="{3 if big else 2}"/>'
                   f'<text x="{x}" y="{y + 8}" text-anchor="middle" font-size="{24 if big else 21}">{emoji}</text>'
                   f'<text x="{x}" y="{y + r + 15}" text-anchor="middle" font-size="12.5" font-weight="700" '
                   f'fill="currentColor">{escape(name)}</text>')
        if run is not None and counts.get(role):
            out.append(f'<circle cx="{x + r - 4}" cy="{y - r + 4}" r="10" fill="{c}"/>'
                       f'<text x="{x + r - 4}" y="{y - r + 8}" text-anchor="middle" font-size="11" font-weight="700" '
                       f'fill="#fff">{counts[role]}</text>')
        out.append("</g>")
    out += labels
    out.append("</svg>")
    return "".join(out)


def legend_html() -> str:
    items = []
    for k, name in LEGEND:
        c, dash, _ = EDGE[k]
        style = f"border-top: 2.5px {'dashed' if dash else 'solid'} {c};"
        items.append(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;">'
                     f'<span style="display:inline-block;width:26px;{style}"></span>{name}</span>')
    return f'<div style="font-size:.82rem;opacity:.8;margin:4px 0 2px;">{"".join(items)}</div>'


def note(structure: str) -> str:
    return LAYOUT[structure]["note"]
